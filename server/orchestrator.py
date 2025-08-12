# server/orchestrator.py

import logging
import asyncio
import random
import torch
import io
import datetime
import time
from typing import TYPE_CHECKING, List, Dict, Any, Set

from utils.log_manager import ContextAdapter
from model_manager.model_manager import ModelManager

# Import the secure aggregation module
from sam.sam import aggregate_model_weights_securely
# Import the new ADRM and PPM modules
from adrm.adrm import ADRM
from ppm.ppm import PPM


if TYPE_CHECKING:
    from client_manager import ClientManager
    from scpm.scpm import ServerControlPlaneManager

def serialize_model_state(state_dict: Dict[str, Any]) -> bytes:
    """
    Serializes a PyTorch model state dictionary into a byte stream.
    """
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()

def deserialize_model_state(data: bytes) -> Dict[str, Any]:
    """
    Deserializes a byte stream back into a PyTorch model state dictionary.
    """
    buffer = io.BytesIO(data)
    return torch.load(buffer, map_location='cpu')  # Added map_location for safety

def validate_state_dict(state_dict: Dict[str, Any], expected_keys: Set[str]) -> bool:
    """
    Validates that a state dictionary contains all expected keys.
    """
    if not isinstance(state_dict, dict):
        return False
    
    received_keys = set(state_dict.keys())
    missing_keys = expected_keys - received_keys
    extra_keys = received_keys - expected_keys
    
    if missing_keys:
        logging.getLogger(__name__).warning(f"Missing keys in state dict: {missing_keys}")
        return False
    
    if extra_keys:
        logging.getLogger(__name__).warning(f"Extra keys in state dict: {extra_keys}")
    
    return True

class Orchestrator:
    def __init__(self, training_config: Dict[str, Any], client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        
        self.model_manager = ModelManager(training_config)

        self.training_config = training_config
        self.training_rounds = self.training_config.get('max_rounds', 10)
        self.clients_per_round = self.training_config.get('clients_per_round', 2)
        self.current_round_number = 0
        self.round_start_time: float = 0.0
        self.last_aggregation_time: float = 0.0  # Track last aggregation timestamp
        self.round_duration: float = 0.0  # Track how long the round took

        self.update_queue: asyncio.Queue = asyncio.Queue()

        self.adrm = ADRM()
        self.ppm = PPM()
        self.logger.info("Orchestrator initialized with ADRM and PPM modules.")

        # New attribute to keep track of selected clients for the current round
        self.selected_clients_for_round: Set[str] = set()
        
        # Cache the expected model keys for validation
        self.expected_model_keys = set(self.model_manager.get_global_model_state().keys())
        self.logger.info(f"Expected model keys: {self.expected_model_keys}")

    async def _training_loop(self):
        """
        The main federated learning training loop.
        """
        self.logger.info(f"Starting federated learning training for {self.training_rounds} rounds.")

        while self.current_round_number < self.training_rounds:
            self.current_round_number += 1
            self.round_start_time = time.time()
            self.logger.info(f"--- Starting round {self.current_round_number} ---")

            # Reset the round's client list and select new clients
            # Store the selected clients in the new instance variable
            self.selected_clients_for_round = self.client_manager.select_clients_for_round(self.clients_per_round)

            # Check if any clients were selected before proceeding
            if self.selected_clients_for_round:
                self.logger.info(f"Selected {len(self.selected_clients_for_round)} clients for this round.")
                self.scpm.trigger_model_update(self.current_round_number)
                self.logger.info(f"Waiting for updates from {len(self.selected_clients_for_round)} clients.")
            else:
                self.logger.warning("Not enough eligible clients to start a round.")
                await asyncio.sleep(5)  # Wait before retrying
                continue # Skip to the next iteration of the while loop

            client_updates = []
            updates_received_count = 0
            
            timeout = self.training_config.get('round_timeout', 60)
            end_time = asyncio.get_event_loop().time() + timeout

            while updates_received_count < len(self.selected_clients_for_round):
                try:
                    remaining_time = end_time - asyncio.get_event_loop().time()
                    if remaining_time <= 0:
                        self.logger.warning(f"Round {self.current_round_number} timed out. Received {updates_received_count}/{len(self.selected_clients_for_round)} updates.")
                        break

                    client_id, update_data = await asyncio.wait_for(self.update_queue.get(), timeout=remaining_time)
                    self.logger.info(f"Processing update from client {client_id}")

                    # Handle both bytes and dict formats for backward compatibility
                    if isinstance(update_data, bytes):
                        self.logger.info(f"Received bytes data from client {client_id}, deserializing...")
                        try:
                            update_data = deserialize_model_state(update_data)
                        except Exception as e:
                            self.logger.error(f"Failed to deserialize update from client {client_id}: {e}")
                            self.update_queue.task_done()
                            continue
                    
                    # Validate the update data structure
                    if not isinstance(update_data, dict):
                        self.logger.error(f"Invalid update format from client {client_id}. Expected dict, got {type(update_data)}")
                        self.update_queue.task_done()
                        continue
                    
                    # Validate that the state dict has expected keys
                    if not validate_state_dict(update_data, self.expected_model_keys):
                        self.logger.error(f"Invalid state dict from client {client_id}. Missing or extra keys.")
                        self.update_queue.task_done()
                        continue

                    # The update_data received from the queue is now a dictionary
                    client_updates.append(update_data)
                    updates_received_count += 1
                    self.update_queue.task_done()
                    
                except asyncio.TimeoutError:
                    self.logger.warning(f"Waiting for client updates timed out for round {self.current_round_number}.")
                    break
                except Exception as e:
                    self.logger.error(f"Error processing update: {e}", exc_info=True)
                    self.update_queue.task_done()

            if client_updates:
                self.logger.info(f"Aggregating {len(client_updates)} client updates.")
                try:
                    # Debug logging before aggregation
                    self.logger.debug(f"Client updates structure: {[list(update.keys()) for update in client_updates]}")
                    
                    # Ensure all updates have the same structure
                    first_update_keys = set(client_updates[0].keys())
                    for i, update in enumerate(client_updates[1:], 1):
                        if set(update.keys()) != first_update_keys:
                            self.logger.error(f"Client update {i} has different keys than first update")
                            raise ValueError(f"Inconsistent update structures in round {self.current_round_number}")
                    
                    # Corrected the call to aggregate_model_weights_securely
                    # It now only takes the list of client updates as an argument
                    aggregation_start_time = time.time()
                    new_global_model_state = aggregate_model_weights_securely(client_updates)
                    aggregation_end_time = time.time()
                    
                    # Validate the aggregated result
                    if not validate_state_dict(new_global_model_state, self.expected_model_keys):
                        self.logger.error("Aggregated model state is invalid. Skipping this round.")
                        raise ValueError("Invalid aggregated model state")
                    
                    self.logger.debug(f"Aggregated model keys: {list(new_global_model_state.keys())}")
                    
                    self.model_manager.update_global_model(new_global_model_state)
                    self.model_manager.evaluate_model()
                    
                    # Update timing information
                    self.last_aggregation_time = aggregation_end_time
                    self.round_duration = aggregation_end_time - self.round_start_time
                    
                    # Notify SCPM with timing information
                    self.scpm.update_last_aggregation_time(self.last_aggregation_time)
                    self.scpm.update_round_duration(self.round_duration)
                    
                    self.client_manager.reset_round_clients()
                    self.scpm.trigger_model_update(self.current_round_number)
                    
                    self.logger.info(f"Round {self.current_round_number} completed in {self.round_duration:.2f}s. "
                                   f"Aggregation took {aggregation_end_time - aggregation_start_time:.2f}s. "
                                   f"Global model updated and clients notified.")

                except Exception as e:
                    self.logger.error(f"An error occurred in the training loop: {e}", exc_info=True)
                    self.client_manager.reset_round_clients()
                    # Add recovery mechanism
                    self.logger.info("Attempting to continue with previous global model...")

            else:
                self.logger.warning(f"No client updates received for round {self.current_round_number}. Skipping aggregation.")
                self.client_manager.reset_round_clients()

            await asyncio.sleep(5)
            self.logger.info("=" * 50)

    async def start_training(self):
        """
        Starts the main training loop as a background task.
        """
        self.logger.info("Starting orchestrator training task.")
        asyncio.create_task(self._training_loop())

    def prepare_model_for_client(self, client_id: str) -> bytes:
        """
        Prepares and returns the global model for a specific client,
        applying privacy mechanisms like DP and HE.
        """
        try:
            global_model_state = self.model_manager.get_global_model_state()
            
            # Validate the global model state before processing
            if not validate_state_dict(global_model_state, self.expected_model_keys):
                self.logger.error("Global model state is invalid")
                raise ValueError("Invalid global model state")
            
            dp_applied_model_state = self.ppm.apply_differential_privacy(global_model_state)
            encrypted_model_state = self.ppm.apply_homomorphic_encryption(dp_applied_model_state)
            
            # Validate after privacy mechanisms
            if not validate_state_dict(encrypted_model_state, self.expected_model_keys):
                self.logger.error("Model state corrupted after privacy mechanisms")
                raise ValueError("Privacy mechanisms corrupted model state")
            
            return serialize_model_state(encrypted_model_state)
        except Exception as e:
            self.logger.error(f"Error preparing model for client {client_id}: {e}")
            # Fallback: return original model without privacy mechanisms
            global_model_state = self.model_manager.get_global_model_state()
            return serialize_model_state(global_model_state)

    async def receive_client_update(self, client_id: str, update_data: bytes):
        """
        Receives a client update and adds it to the update queue for aggregation.
        """
        self.logger.info(f"Received model update from client {client_id} in receive_client_update method. Adding to queue.")
        
        # Check if client is part of current round
        if client_id not in self.selected_clients_for_round:
            self.logger.warning(f"Received update from client {client_id} who is not part of current round. Ignoring.")
            return
        
        # Deserialize the byte data into a state dictionary before adding it to the queue
        try:
            self.logger.debug(f"Deserializing {len(update_data)} bytes from client {client_id}")
            update_state_dict = deserialize_model_state(update_data)
            self.logger.debug(f"Successfully deserialized update from client {client_id}, keys: {list(update_state_dict.keys()) if isinstance(update_state_dict, dict) else 'Not a dict'}")
        except Exception as e:
            self.logger.error(f"Failed to deserialize update from client {client_id}: {e}")
            return
        
        if not isinstance(update_state_dict, dict):
            self.logger.error(f"Received invalid update data from client {client_id}. Expected a dictionary, got {type(update_state_dict)}.")
            return

        # Validate the structure of the received update
        if not validate_state_dict(update_state_dict, self.expected_model_keys):
            self.logger.error(f"Invalid state dict structure from client {client_id}")
            return

        if self.adrm.detect_suspicious_update(client_id, update_state_dict):
            self.logger.warning(f"ADRM detected a suspicious update from client {client_id}. Update will be discarded.")
            client_info = self.client_manager.get_client_info(client_id)
            self.logger.info(f"Client Details of Anomalous Update: {client_info}")
            self.adrm.blocked_clients.append(client_id)
            return

        self.logger.info(f"Adding deserialized update from client {client_id} to queue as dict")
        await self.update_queue.put((client_id, update_state_dict))
        
    def get_current_round_number(self) -> int:
        """Returns the current round number."""
        return self.current_round_number

    def get_last_aggregation_time(self) -> float:
        """Returns the timestamp of the last aggregation."""
        return self.last_aggregation_time
    
    def get_last_aggregation_datetime(self) -> str:
        """Returns the last aggregation time as a formatted datetime string."""
        if self.last_aggregation_time == 0.0:
            return "No aggregation yet"
        return datetime.datetime.fromtimestamp(self.last_aggregation_time).strftime("%Y-%m-%d %H:%M:%S")
    
    def get_round_duration(self) -> float:
        """Returns the duration of the last completed round in seconds."""
        return self.round_duration
    
    def get_training_stats(self) -> Dict[str, Any]:
        """Returns comprehensive training statistics."""
        return {
            "current_round": self.current_round_number,
            "total_rounds": self.training_rounds,
            "last_aggregation_time": self.get_last_aggregation_datetime(),
            "last_aggregation_timestamp": self.last_aggregation_time,
            "round_duration_seconds": self.round_duration,
            "selected_clients_count": len(self.selected_clients_for_round),
            "selected_clients": list(self.selected_clients_for_round),
            "queue_size": self.update_queue.qsize()
        }

    # NEW METHOD: Checks if a client is part of the current training round
    def is_client_in_current_round(self, client_id: str) -> bool:
        """
        Checks if the specified client has been selected for the current training round.
        """
        return client_id in self.selected_clients_for_round