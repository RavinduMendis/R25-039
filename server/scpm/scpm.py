# server/scpm/scpm.py

import logging
import datetime
import asyncio
import os
import json
import time
from typing import TYPE_CHECKING, List, Any, Dict

from scpm.handlers.grpc_handler import GrpcHandler
from scpm.handlers.api_handler import ApiHandler
from utils.log_manager import ContextAdapter
from utils.log_manager import LOG_DIR

if TYPE_CHECKING:
    from server.client_manager import ClientManager
    from server.orchestrator import Orchestrator
    from server.model_manager.model_manager import ModelManager

class ServerControlPlaneManager:
    def __init__(self, client_manager: 'ClientManager'):
        self.client_manager = client_manager
        self.orchestrator: 'Orchestrator' = None
        self.start_time = datetime.datetime.now()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        self.logger.info("ServerControlPlaneManager initialized.")

        self.communication_handlers: List[Any] = []
        
        self._current_round = 0
        self._connected_clients_count = 0
        self._updates_in_queue = 0
        self._last_aggregation_time = 0.0 # Changed to float for consistency
        self._round_duration = 0.0 # Added new attribute for round duration
        self._model_metrics = []
        self._is_ready = False
        self.new_model_available = False # ADDED: Flag for model availability

        self.is_tls_enabled = False
        self.is_client_auth_enabled = False
        self.last_security_event = "System initialized."

    def set_orchestrator(self, orchestrator: 'Orchestrator'):
        self.orchestrator = orchestrator
        self.logger.info("Orchestrator instance set.")
        self._setup_communication_handlers()

    def _setup_communication_handlers(self):
        self.logger.info("Setting up communication handlers...")

        if not self.orchestrator:
            self.logger.critical("Orchestrator instance is not set. Cannot initialize handlers.")
            raise RuntimeError("Orchestrator dependency is missing.")

        self.grpc_handler = GrpcHandler(self.client_manager, self, self.orchestrator)
        self.communication_handlers.append(self.grpc_handler)
        self.logger.info("gRPC Handler added.")

        self.api_handler = ApiHandler(
            client_manager=self.client_manager,
            scpm=self,
            model_manager=self.orchestrator.model_manager,
            orchestrator=self.orchestrator
        )
        self.communication_handlers.append(self.api_handler)
        self.logger.info("API Handler added for dashboard access.")

        self.logger.info(f"Total {len(self.communication_handlers)} communication handlers configured.")

    async def start_communication_listeners(self) -> List[asyncio.Task]:
        self.logger.info("Starting all communication listeners...")
        tasks = [asyncio.create_task(handler.start_listener()) for handler in self.communication_handlers]
        self._is_ready = True
        self.logger.info("All communication listeners have been started as background tasks.")
        return tasks

    async def stop_communication_listeners(self):
        self.logger.info("Stopping all communication listeners...")
        tasks = [handler.stop_listener() for handler in self.communication_handlers]
        await asyncio.gather(*tasks)
        self._is_ready = False
        self.logger.info("All communication listeners have been stopped.")

    def get_server_status(self) -> Dict[str, Any]:
        uptime = datetime.datetime.now() - self.start_time
        uptime_seconds = int(uptime.total_seconds())

        status_data = {
            "status": "running" if self._is_ready else "initializing",
            "uptime_seconds": uptime_seconds,
            "connected_clients": self.client_manager.get_connected_clients_count(),
            "last_heartbeat_timestamp": int(time.time()),
            "modules": {
                "client_manager": self.client_manager.get_status(),
                "model_manager": self.get_mm_status(),
                "secure_aggregation_module": self.get_sam_status(),
                "attack_detection_response_module": self.get_adrm_status(),
                "privacy_preservation_module": self.get_ppm_status(),
                "server_communication and enforcement module": self.get_scpm_status(),
            },
            "log_file_size_kb": self._get_log_file_size_kb()
        }
        return status_data

    def _get_log_file_size_kb(self) -> int:
        try:
            log_path = os.path.join(LOG_DIR, "server.log")
            if os.path.exists(log_path):
                size_bytes = os.path.getsize(log_path)
                return size_bytes // 1024
            else:
                return 0
        except Exception as e:
            self.logger.error(f"Error getting log file size: {e}", exc_info=True)
            return 0


    def update_current_round(self, round_number: int):
        self._current_round = round_number
        self.logger.info(f"Dashboard status updated: Current round is {round_number}.")

    def update_client_count(self, count: int):
        self._connected_clients_count = count
        self.logger.info(f"Dashboard status updated: Connected clients count is {count}.")

    def update_updates_in_queue(self, count: int):
        self._updates_in_queue = count
        self.logger.info(f"Dashboard status updated: {count} updates in queue.")

    def update_last_aggregation_time(self, timestamp: float):
        """Updates the last aggregation timestamp for dashboard display."""
        self._last_aggregation_time = timestamp
        self.logger.info(f"Last aggregation time updated: {datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")

    def update_round_duration(self, duration: float):
        """Updates the last round duration for dashboard display."""
        self._round_duration = duration
        self.logger.info(f"Round duration updated: {duration:.2f} seconds")

    def get_training_overview(self) -> Dict[str, Any]:
        """Returns comprehensive training overview for the dashboard."""
        # Get stats from orchestrator if available
        orchestrator_stats = {}
        if hasattr(self, 'orchestrator') and self.orchestrator:
            orchestrator_stats = self.orchestrator.get_training_stats()
        
        return {
            "connected_clients": self.client_manager.get_connected_clients_count() if self.client_manager else 0,
            "updates_in_queue": self._updates_in_queue if hasattr(self, '_updates_in_queue') else 0,
            "server_status": "running",
            "last_aggregation_time": self._last_aggregation_time,
            "round_duration": self._round_duration,
            **orchestrator_stats  # Include all orchestrator stats
        }

    def add_model_metrics(self, metrics: Dict[str, Any]):
        metrics_with_timestamp = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "round": self._current_round,
            "metrics": metrics
        }
        self._model_metrics.append(metrics_with_timestamp)
        self.logger.info(f"Dashboard status updated: Added new model metrics for round {self._current_round}.")
    
    def get_all_clients(self) -> Dict[str, Any]:
        return self.client_manager.get_client_statuses()

    def is_server_ready(self) -> bool:
        return self._is_ready

    def get_current_round(self) -> int:
        return self._current_round

    def get_updates_in_queue(self) -> int:
        return self._updates_in_queue

    def get_last_aggregation_time(self) -> str:
        if self._last_aggregation_time:
            return datetime.datetime.fromtimestamp(self._last_aggregation_time).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

    def get_model_metrics(self) -> List[Dict[str, Any]]:
        return self._model_metrics

    def get_client_health_data(self) -> Dict[str, Any]:
        return self.client_manager.get_client_statuses()
        
    def get_server_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        log_path = os.path.join(LOG_DIR, "server.log")
        logs = []
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                all_lines = f.readlines()
                last_lines = all_lines[-limit:]
                for line in last_lines:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Could not parse log line as JSON: {line.strip()}. Error: {e}")
        return logs

    def get_mm_status(self) -> Dict[str, Any]:
        if self.orchestrator and self.orchestrator.model_manager:
            return {
                "model_version": self.orchestrator.model_manager.global_model_version,
                "last_model_update": self.get_last_aggregation_time(),
                "training_progress": f"{self.orchestrator.current_round_number}/{self.orchestrator.training_rounds}",
                "active_tasks": "N/A"
            }
        return {"status": "error", "message": "Model Manager not initialized."}

    def get_sam_status(self) -> Dict[str, Any]:
        return {
            "aggregation_protocol": "SecAgg",
            "security_level": "High",
            "updates_in_queue": self.orchestrator.update_queue.qsize(),
            "failed_sessions": 0,
            "last_aggregation_time": self.get_last_aggregation_time()
        }

    def get_adrm_status(self):
        if not self.orchestrator or not self.orchestrator.adrm:
            return {"status": "ADRM not initialized"}
    
        return self.orchestrator.adrm.get_adrm_status()

    def get_ppm_status(self) -> Dict[str, Any]:
        if self.orchestrator and self.orchestrator.ppm:
            return self.orchestrator.ppm.get_status()
        return {"status": "error", "message": "PPM not initialized."}

    def get_scpm_status(self) -> Dict[str, Any]:
        return {
            "module_name": "SCPM",
            "status": "active",
            "tls_enabled": self.is_tls_enabled,
            "client_authentication_enabled": self.is_client_auth_enabled,
            "last_security_event": self.last_security_event,
            "active_protocols": ["TLS v1.3", "JWT Authentication"],
            "description": "Manages communication protocols and server state."
        }

    def trigger_model_update(self, round_number: int):
        self._current_round = round_number
        self.new_model_available = True
        self.logger.info(f"Triggering model update for round {self._current_round}. New model is available.")

    def get_model_update_status_and_reset(self) -> bool:
        """
        Returns True if a new model is available and immediately resets the flag.
        This is for client heartbeats to check and receive the model only once.
        """
        status = self.new_model_available
        if status:
            self.new_model_available = False
        return status