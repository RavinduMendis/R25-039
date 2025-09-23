# orchestrator.py

import asyncio
import logging
import torch
import io
import datetime
import time
from typing import TYPE_CHECKING, List, Dict, Any, Set, Optional
from enum import Enum
from collections import defaultdict

from log_manager.log_manager import ContextAdapter

from sam.sam import aggregate_model_weights_securely
from adrm.adrm_engine import ADRMEngine
from ppm.ppm import PPM
from sam.sss import SecretSharing
from ppm.he import HomomorphicEncryption

if TYPE_CHECKING:
    from client_manager import ClientManager
    from scpm.scpm import ServerControlPlaneManager
    from model_manager.model_manager import ModelManager


class OrchestratorState(Enum):
    """Defines the possible states of the Orchestrator."""
    IDLE = "IDLE"
    PAUSED_INSUFFICIENT_CLIENTS = "PAUSED_INSUFFICIENT_CLIENTS"
    CLIENT_SELECTION = "CLIENT_SELECTION"
    WAITING_FOR_UPDATES = "WAITING_FOR_UPDATES"
    AGGREGATING = "AGGREGATING"
    EVALUATING = "EVALUATING"
    FINISHED = "FINISHED"
    STANDBY = "STANDBY"


def serialize_model_state(state_dict: Dict[str, Any]) -> bytes:
    """Serializes a PyTorch model state dictionary into a byte stream."""
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()


def deserialize_model_state(data: bytes) -> Dict[str, Any]:
    """Deserializes a byte stream back into a PyTorch model state dictionary."""
    buffer = io.BytesIO(data)
    return torch.load(buffer, map_location='cpu')


def validate_state_dict(state_dict: Dict[str, Any], expected_keys: Set[str]) -> bool:
    """Validates that a state dictionary contains all expected keys and no extra keys."""
    if not isinstance(state_dict, dict): return False
    received_keys = set(state_dict.keys())
    missing_keys = expected_keys - received_keys
    extra_keys = received_keys - expected_keys
    if missing_keys: logging.warning(f"State dict is missing expected keys: {missing_keys}")
    if extra_keys: logging.warning(f"State dict contains unexpected keys: {extra_keys}")
    return not missing_keys and not extra_keys


class Orchestrator:
    """Manages the overall federated learning training process."""
    def __init__(self,
                client_manager: 'ClientManager',
                model_manager: 'ModelManager',
                adrm_engine: ADRMEngine,
                ppm: PPM,
                cfg: Dict[str, Any]):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        self.cfg = cfg or {}
        self.aggregation_method = self.cfg.get("federated_learning", {}).get("aggregation_method", "fedadam")
        self.scpm: 'ServerControlPlaneManager' = None
        self.client_manager = client_manager
        self.model_manager = model_manager
        self.total_rounds = self.cfg.get("federated_learning", {}).get("training_rounds", 100)
        self.clients_per_round = self.cfg.get("federated_learning", {}).get("clients_per_round", 3)
        self.min_clients_for_round = self.cfg.get("federated_learning", {}).get("min_clients_for_round", 3)
        self.round_timeout = self.cfg.get("federated_learning", {}).get("round_timeout_seconds", 300)
        self.current_round_number = 0
        self.is_training_in_progress = False
        self.current_round_clients: Set[str] = set()
        self.model_updates: Dict[str, Any] = {}
        self.model_shares: Dict[str, Dict[int, bytes]] = {}
        self.round_start_time = 0.0
        self.round_duration = 0.0
        self.last_aggregation_time = 0.0
        self.state = OrchestratorState.IDLE
        self.aggregation_task = None
        self.round_check_interval = self.cfg.get("status_check_interval_seconds", 10)
        self.round_check_task = None
        self.failed_updates_log: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        self.adrm_engine = adrm_engine
        self.ppm = ppm
        self.he_handler = HomomorphicEncryption()
        self.sss_handler = SecretSharing(
            num_shares=self.cfg.get("federated_learning", {}).get("sss_servers", 3),
            threshold=self.cfg.get("federated_learning", {}).get("sss_threshold", 2)
        )
        self.round_lock = asyncio.Lock()
        
        self.logger.info(f"Orchestrator initialized. aggregation_method={self.aggregation_method}")
    
    def set_scpm(self, scpm: 'ServerControlPlaneManager'):
        self.scpm = scpm
        self.logger.info("ServerControlPlaneManager reference set.")

    def prepare_model_for_client(self, client_id: str) -> Optional[bytes]:
        """Prepares the global model for a client if conditions are met."""
        if self.state != OrchestratorState.WAITING_FOR_UPDATES:
            self.logger.warning(f"Denied model request from {client_id}. Orchestrator state is '{self.state.value}'.")
            return None
        if client_id not in self.current_round_clients:
            self.logger.warning(f"Denied model request from {client_id}. Not selected for round {self.current_round_number}.")
            return None
        self.logger.info(f"Preparing global model for client {client_id} for round {self.current_round_number}.")
        global_model_state = self.model_manager.get_global_model_state()
        return serialize_model_state(global_model_state)

    async def start_training(self):
        if self.is_training_in_progress: self.logger.warning("Training is already in progress."); return
        self.is_training_in_progress = True
        self.state = OrchestratorState.IDLE
        self.logger.info("Orchestrator starting training loop.")
        self.round_check_task = asyncio.create_task(self._periodic_round_check())

    async def _periodic_round_check(self):
        while self.is_training_in_progress:
            if self.current_round_number >= self.total_rounds:
                self.logger.info(f"All {self.total_rounds} training rounds completed. Entering standby mode.")
                self.state = OrchestratorState.STANDBY
            
            if self.state in [OrchestratorState.IDLE, OrchestratorState.PAUSED_INSUFFICIENT_CLIENTS]:
                eligible_clients_count = await self.client_manager.get_eligible_clients_count()
                if eligible_clients_count >= self.clients_per_round:
                    self.logger.info(f"Sufficient clients ({eligible_clients_count}) available. Triggering new round.")
                    async with self.round_lock:
                        if self.state in [OrchestratorState.IDLE, OrchestratorState.PAUSED_INSUFFICIENT_CLIENTS]:
                            await self.trigger_new_round()
                else:
                    if self.state != OrchestratorState.PAUSED_INSUFFICIENT_CLIENTS:
                        self.logger.info(f"Training paused: {eligible_clients_count}/{self.clients_per_round} clients available.")
                        self.state = OrchestratorState.PAUSED_INSUFFICIENT_CLIENTS
            
            elif self.state == OrchestratorState.WAITING_FOR_UPDATES:
                elapsed_time = time.time() - self.round_start_time
                if elapsed_time > self.round_timeout:
                    self.logger.warning(f"Round {self.current_round_number} timed out after {elapsed_time:.2f} seconds.")
                    async with self.round_lock:
                        if self.state == OrchestratorState.WAITING_FOR_UPDATES:
                            if len(self.model_updates) >= self.min_clients_for_round:
                                self.logger.info(f"Timeout reached, but minimum updates ({len(self.model_updates)}/{self.min_clients_for_round}) received. Proceeding to aggregation.")
                                if self.aggregation_task is None or self.aggregation_task.done():
                                    self.aggregation_task = asyncio.create_task(self._run_aggregation_with_lock())
                            else:
                                self.logger.warning(f"Cancelling round {self.current_round_number} due to timeout. Not enough updates received.")
                                self.model_updates = {}
                                self.model_shares = {}
                                self.current_round_clients = set()
                                self.state = OrchestratorState.IDLE

            elif self.state == OrchestratorState.STANDBY: self.logger.debug("Orchestrator in standby.")
            await asyncio.sleep(self.round_check_interval)

    async def trigger_new_round(self):
        if self.state not in [OrchestratorState.IDLE, OrchestratorState.PAUSED_INSUFFICIENT_CLIENTS]:
            self.logger.warning(f"Cannot start a new round from state: {self.state.value}"); return
        self.state = OrchestratorState.CLIENT_SELECTION
        self.current_round_number += 1
        self.logger.info(f"--- Starting training round {self.current_round_number}/{self.total_rounds} ---")
        self.round_start_time = time.time()
        self.model_updates = {}
        self.model_shares = {}
        await self.client_manager.reset_round_clients()
        selected_clients_list = await self.client_manager.select_clients_for_round(self.clients_per_round)
        self.current_round_clients = set(selected_clients_list)
        if not self.current_round_clients:
            self.logger.warning("No clients selected. Pausing."); self.state = OrchestratorState.PAUSED_INSUFFICIENT_CLIENTS; return
        self.logger.info(f"Selected {len(self.current_round_clients)} clients for round {self.current_round_number}: {list(self.current_round_clients)}.")
        if self.scpm: self.scpm.trigger_model_update(self.current_round_number); self.logger.info("Model update triggered for clients.")
        self.state = OrchestratorState.WAITING_FOR_UPDATES

    async def _handle_received_update(self, client_id: str, model_update_dict: Dict, privacy_method: str):
        """
        Internal handler to process a successfully deserialized/decrypted update.
        """
        is_valid_update = self.adrm_engine.process_update(client_id, model_update_dict)
        if not is_valid_update:
            self.logger.warning(f"Update from {client_id} was flagged by ADRM (Stage 1) and dropped.")
            return

        self.logger.info(f"Received valid {privacy_method} update from client {client_id}.")
        model_update_dict["privacy_method"] = privacy_method
        self.model_updates[client_id] = model_update_dict

        should_aggregate = (len(self.model_updates) >= len(self.current_round_clients) or
                           len(self.model_updates) >= self.min_clients_for_round)
        
        if should_aggregate:
            self.logger.info(f"Sufficient updates received ({len(self.model_updates)}). Minimum is {self.min_clients_for_round}. Triggering aggregation.")
            if self.aggregation_task is None or self.aggregation_task.done():
                self.aggregation_task = asyncio.create_task(self._run_aggregation_with_lock())
        else:
            self.logger.info(f"Collected {len(self.model_updates)}/{self.min_clients_for_round} (min) updates. Waiting for more.")

    async def receive_he_update(self, client_id: str, model_update_bytes: bytes):
        """Receives and processes a Homomorphically Encrypted (HE) model update."""
        self.logger.info(f"Received HE update from {client_id}.")
        if self.state != OrchestratorState.WAITING_FOR_UPDATES:
            self.logger.warning(f"Orchestrator not ready for HE update from {client_id}. State: {self.state.value}")
            return

        try:
            model_update_dict = self.he_handler.decrypt_model_state(model_update_bytes)
            current_model_keys = set(self.model_manager.get_global_model_state().keys())
            if not validate_state_dict(model_update_dict, current_model_keys):
                self.logger.warning(f"Invalid HE model structure from {client_id}.")
                return
            
            await self._handle_received_update(client_id, model_update_dict, "HE")
        except Exception as e:
            self.logger.error(f"Failed to process HE update from {client_id}: {e}")

    async def receive_normal_update(self, client_id: str, model_update_bytes: bytes):
        """Receives and processes a Normal (plaintext) model update."""
        self.logger.info(f"Received Normal update from {client_id}.")
        if self.state != OrchestratorState.WAITING_FOR_UPDATES:
            self.logger.warning(f"Orchestrator not ready for Normal update from {client_id}. State: {self.state.value}")
            return
            
        try:
            model_update_dict = deserialize_model_state(model_update_bytes)
            current_model_keys = set(self.model_manager.get_global_model_state().keys())
            if not validate_state_dict(model_update_dict, current_model_keys):
                self.logger.warning(f"Invalid Normal model structure from {client_id}.")
                return

            await self._handle_received_update(client_id, model_update_dict, "Normal")
        except Exception as e:
            self.logger.error(f"Failed to process Normal update from {client_id}: {e}")

    async def receive_sss_share(self, client_id: str, share_index: int, share_data: bytes, total_shares: int):
        self.logger.debug(f"Processing SSS share {share_index+1}/{total_shares} from {client_id}.")
        if self.state != OrchestratorState.WAITING_FOR_UPDATES: return
        if client_id not in self.model_shares: self.model_shares[client_id] = {}
        
        if client_id in self.model_updates:
            self.logger.debug(f"Ignoring share from {client_id}; their model has already been reconstructed.")
            return
            
        self.model_shares[client_id][share_index] = share_data

        if len(self.model_shares[client_id]) >= self.sss_handler.threshold:
            self.logger.info(f"Sufficient shares ({len(self.model_shares[client_id])}/{self.sss_handler.threshold}) received from {client_id}. Attempting reconstruction.")
            try:
                all_shares = list(self.model_shares[client_id].values())
                reconstructed_update = self.sss_handler.reconstruct_model(all_shares)
                
                current_model_keys = set(self.model_manager.get_global_model_state().keys())
                if not validate_state_dict(reconstructed_update, current_model_keys):
                    self.logger.warning(f"Invalid SSS model structure from {client_id}.")
                    return
                
                await self._handle_received_update(client_id, reconstructed_update, "SSS")
            except Exception as e:
                self.logger.exception(f"Failed to reconstruct SSS update from {client_id}: {e}")
            finally:
                if client_id in self.model_shares: 
                    del self.model_shares[client_id]

    async def _run_aggregation_with_lock(self):
        """A wrapper for the aggregation process that acquires the lock."""
        async with self.round_lock:
            if self.state == OrchestratorState.WAITING_FOR_UPDATES:
                await self._aggregate_updates()
            else:
                self.logger.warning(f"Aggregation was triggered but aborted because state changed to '{self.state.value}'.")


    async def _aggregate_updates(self):
        if self.state != OrchestratorState.WAITING_FOR_UPDATES: 
            self.logger.warning(f"Attempted to aggregate from invalid state: {self.state.value}. Aborting."); 
            return
        
        self.state = OrchestratorState.AGGREGATING
        self.logger.info("============== AGGREGATION PROCESS STARTED ==============")

        try:
            if len(self.model_updates) < self.min_clients_for_round:
                self.logger.warning(f"Aggregation aborted. Only {len(self.model_updates)}/{self.min_clients_for_round} (min) updates available.")
                self.state = OrchestratorState.IDLE
                return

            self.logger.info("AGGREGATION STEP 1.1: Starting ADRM Stage 2 (Cross-Client) check.")
            outlier_ids = self.adrm_engine.detect_outliers_in_group(self.model_updates)
            self.logger.info("AGGREGATION STEP 1.2: ADRM Stage 2 check finished.")
            for client_id in outlier_ids:
                if client_id in self.model_updates:
                    del self.model_updates[client_id]
            
            if not self.model_updates:
                self.logger.warning("Aggregation aborted. All updates were flagged as outliers.")
                self.state = OrchestratorState.IDLE
                return

            self.logger.info("AGGREGATION STEP 2.1: Starting Privacy Audit.")
            client_ids = list(self.model_updates.keys())
            raw_updates = [self.model_updates[cid] for cid in client_ids]
            privacy_methods = {self.model_updates[cid].get("privacy_method", "Normal") for cid in client_ids}
            
            if len(privacy_methods) > 1:
                self.logger.error(f"Aggregation failed: Inconsistent privacy methods. Found: {privacy_methods}")
                self.state = OrchestratorState.IDLE
                return
            
            current_privacy_method = list(privacy_methods)[0]
            if not self.ppm.verify_audit(current_privacy_method):
                self.logger.error(f"Aggregation failed: Privacy audit failed for method '{current_privacy_method}'.")
                self.state = OrchestratorState.IDLE
                return
            self.logger.info("AGGREGATION STEP 2.2: Privacy Audit finished.")

            if current_privacy_method == "HE":
                final_aggregation_method = "homomorphic_aggregation"
            else:
                final_aggregation_method = self.aggregation_method

            self.logger.info(f"Privacy method '{current_privacy_method}' detected. Using aggregation method: '{final_aggregation_method}'.")

            self.logger.info(f"AGGREGATION STEP 3.1: Calling SAM to aggregate {len(raw_updates)} updates using '{final_aggregation_method}'.")
            aggregated_model = aggregate_model_weights_securely(raw_updates, self.model_manager.get_global_model_state(), method=final_aggregation_method)
            self.logger.info("AGGREGATION STEP 3.2: SAM aggregation finished. Updating global model.")
            self.model_manager.update_global_model(aggregated_model)
            self.logger.info("AGGREGATION STEP 3.3: Global model updated.")

            self.last_aggregation_time = time.time()
            self.round_duration = self.last_aggregation_time - self.round_start_time
            self.logger.info(f"AGGREGATION STEP 4.1: Aggregation for round {self.current_round_number} complete. Duration: {self.round_duration:.2f}s")
            
            metrics = self.model_manager.evaluate_model()

            # <<< FIX: Call the function to record the aggregation event >>>
            self.model_manager.record_aggregation_event(self.current_round_number, metrics)
            
            self.model_manager.add_metrics_to_history(self.current_round_number, metrics, final_aggregation_method)
            
            if self.scpm:
                self.scpm.update_round_info(self.get_training_stats())
            self.logger.info("AGGREGATION STEP 4.2: Post-aggregation tasks complete.")

        finally:
            self.model_updates = {}
            if self.current_round_number >= self.total_rounds:
                self.state = OrchestratorState.FINISHED
            else:
                self.state = OrchestratorState.IDLE
            self.logger.info(f"============== AGGREGATION PROCESS FINISHED | NEW STATE: {self.state.value} ==============")

    async def stop_training(self):
        self.logger.info("Stopping training loop.")
        self.is_training_in_progress = False
        if self.round_check_task and not self.round_check_task.done():
            self.round_check_task.cancel()
            try: await self.round_check_task
            except asyncio.CancelledError: pass
        self.state = OrchestratorState.STANDBY
        self.logger.info("Orchestrator stopped; in STANDBY state.")
        
    def get_orchestrator_progress(self) -> Dict[str, Any]:
        return {
            "is_training_in_progress": self.is_training_in_progress, 
            "current_state": self.state.value, 
            "current_round_number": self.current_round_number, 
            "total_rounds": self.total_rounds, 
            "clients_per_round": self.clients_per_round, 
            "updates_received": len(self.model_updates),
            "selected_clients_count": len(self.current_round_clients), 
            "round_start_time": self.round_start_time, 
            "round_timeout": self.round_timeout
        }
        
    def get_training_stats(self) -> Dict[str, Any]:
        return {
            "current_round": self.current_round_number, 
            "total_rounds": self.total_rounds, 
            "last_aggregation_time": datetime.datetime.fromtimestamp(self.last_aggregation_time).strftime("%Y-%m-%d %H:%M:%S") if self.last_aggregation_time > 0 else "N/A", 
            "last_aggregation_timestamp": self.last_aggregation_time, 
            "round_duration_seconds": self.round_duration, 
            "selected_clients_count": len(self.current_round_clients), 
            "selected_clients": list(self.current_round_clients), 
            "updates_received": len(self.model_updates), 
            "current_state": self.state.value
        }
        
    def is_client_in_current_round(self, client_id: str) -> bool:
        return client_id in self.current_round_clients

    def get_queue_size(self) -> int:
        return len(self.model_updates)

    def get_failed_updates_log(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.failed_updates_log