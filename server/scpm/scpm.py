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
from log_manager.log_manager import ContextAdapter
from log_manager.log_manager import LOG_DIR
from log_manager.decorators import handle_exceptions

if TYPE_CHECKING:
    from server.client_manager import ClientManager
    from server.orchestrator import Orchestrator
    from server.model_manager.model_manager import ModelManager

class ServerControlPlaneManager:
    """
    The Server Control Plane Manager (SCPM) is a central component responsible for
    orchestrating server-side communication, managing the lifecycle of communication
    handlers (gRPC, API), and providing a consolidated status view of the entire
    federated learning system.

    It acts as the primary interface for external dashboards and internal modules
    to retrieve real-time metrics and security-related information.
    """

    def __init__(self, client_manager: 'ClientManager', model_manager: 'ModelManager'):
        """
        Initializes the SCPM with ClientManager and ModelManager instances.

        Args:
            client_manager (ClientManager): An instance of the ClientManager to
                                            manage connected clients.
            model_manager (ModelManager): An instance of the ModelManager to
                                          handle model-related operations.
        """
        self.client_manager = client_manager
        self.model_manager = model_manager
        self.orchestrator: 'Orchestrator' = None
        self.start_time = datetime.datetime.now()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        self.logger.info("ServerControlPlaneManager initialized.")

        self.communication_handlers: List[Any] = []
        
        self._current_round = 0
        self._connected_clients_count = 0
        self._updates_in_queue = 0
        self._last_aggregation_time = 0.0
        self._round_duration = 0.0
        self._is_ready = False
        self.new_model_available = False
        self.is_tls_enabled = False
        self.is_client_auth_enabled = False
        self.last_security_event = "System initialized."
        self.dashboard_data_queue = asyncio.Queue()
        self.communication_tasks: List[asyncio.Task] = []
        
    def set_orchestrator(self, orchestrator: 'Orchestrator'):
        """
        Sets the orchestrator instance and links it to handlers.
        This method must be called after the orchestrator is created to resolve
        circular dependencies.

        Args:
            orchestrator (Orchestrator): The orchestrator instance.
        """
        self.orchestrator = orchestrator
        self.logger.info("Orchestrator instance set.")
        self._setup_communication_handlers()
    
    def _setup_communication_handlers(self):
        """Initializes and configures communication handlers."""
        self.logger.info("Setting up communication handlers...")

        if not self.orchestrator:
            self.logger.critical("Orchestrator instance is not set. Cannot initialize handlers.")
            raise RuntimeError("Orchestrator dependency is missing.")

        if not self.model_manager:
            self.logger.critical("ModelManager instance is not set. Cannot initialize handlers.")
            raise RuntimeError("ModelManager dependency is missing.")
        
        # Instantiate and add gRPC handler
        self.grpc_handler = GrpcHandler(self.client_manager, self, self.orchestrator)
        self.communication_handlers.append(self.grpc_handler)
        self.logger.info("gRPC Handler added.")

        # Instantiate and add API handler, passing all necessary dependencies.
        self.api_handler = ApiHandler(
            client_manager=self.client_manager,
            scpm=self,
            model_manager=self.model_manager,
            orchestrator=self.orchestrator
        )
        self.communication_handlers.append(self.api_handler)
        self.logger.info("API Handler added for dashboard access.")

        self.logger.info(f"Total {len(self.communication_handlers)} communication handlers configured.")

    async def start_communication_listeners(self) -> List[asyncio.Task]:
        """
        Starts all communication handlers as asynchronous tasks.
        
        Returns:
            List[asyncio.Task]: A list of the created tasks.
        """
        self.logger.info("Starting all communication listeners...")
        self.communication_tasks = [asyncio.create_task(handler.start_listener()) for handler in self.communication_handlers]
        self._is_ready = True
        self.logger.info("All communication listeners have been started as background tasks.")
        return self.communication_tasks

    async def stop_communication_listeners(self):
        """Stops all active communication handlers gracefully."""
        self.logger.info("Stopping all communication listeners...")
        tasks = [handler.stop_listener() for handler in self.communication_handlers]
        await asyncio.gather(*tasks)
        self._is_ready = False
        self.logger.info("All communication listeners have been stopped.")

    @handle_exceptions("Error updating round info")
    def update_round_info(self, training_stats: Dict[str, Any]):
        """
        Receives training stats from the Orchestrator and updates the internal state.
        This method is a core part of the server's state management.
        """
        # Update internal state with new information from the Orchestrator
        self.update_current_round(training_stats.get("current_round", 0))
        self.update_round_duration(training_stats.get("round_duration_seconds", 0.0))
        
        # We assume the Orchestrator provides these stats after aggregation,
        # so we update the last aggregation time and queue size
        self.update_last_aggregation_time(time.time())
        self.update_updates_in_queue(training_stats.get("queue_size", 0))
        self.update_client_count(training_stats.get("selected_clients_count", 0))
        
        self.logger.info(f"Received updated training stats for round {self._current_round}")
        
        # Put the new stats in a queue for real-time dashboard updates
        # This is a non-blocking operation
        try:
            self.dashboard_data_queue.put_nowait(self.get_full_status())
        except asyncio.QueueFull:
            self.logger.warning("Dashboard data queue is full, dropping update.")

    async def get_dashboard_update(self):
        """Waits for and returns the next dashboard update from the queue."""
        return await self.dashboard_data_queue.get()

    def get_full_status(self) -> Dict[str, Any]:
        """
        Returns a comprehensive, real-time status of the entire server,
        consolidating information from all modules for the dashboard.
        """
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
                "server_control_plane_manager": self.get_scpm_status(),
            },
            "training_overview": self.get_training_overview(),
            "log_file_size_kb": self._get_log_file_size_kb()
        }
        return status_data

    def get_server_status(self) -> Dict[str, Any]:
        """
        A dedicated method to return the full server status, used specifically
        by the API handler.
        """
        return self.get_full_status()

    def _get_log_file_size_kb(self) -> int:
        """Returns the size of the main server log file in kilobytes."""
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
        """Updates the internal state with the current training round number."""
        self._current_round = round_number
        self.logger.info(f"Dashboard status updated: Current round is {round_number}.")

    def update_client_count(self, count: int):
        """Updates the internal state with the number of connected clients."""
        self._connected_clients_count = count
        self.logger.info(f"Dashboard status updated: Connected clients count is {count}.")

    def update_updates_in_queue(self, count: int):
        """Updates the internal state with the number of updates waiting for aggregation."""
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
        """
        Returns a summary of the federated training process.
        This method is a core part of the dashboard API.
        """
        if self.orchestrator:
            return self.orchestrator.get_training_stats()
        
        return {
            "current_round": 0, "total_rounds": 0, "last_aggregation_time": "N/A",
            "round_duration_seconds": 0.0, "selected_clients_count": 0,
            "selected_clients": [], "queue_size": 0, "status": "Orchestrator not initialized."
        }
    
    def get_all_clients(self) -> Dict[str, Any]:
        """Returns the health status of all connected clients."""
        return self.client_manager.get_client_statuses()

    def is_server_ready(self) -> bool:
        """Returns True if the server is ready to accept client connections."""
        return self._is_ready

    def get_current_round(self) -> int:
        """Returns the current federated learning round number."""
        return self._current_round

    def get_updates_in_queue(self) -> int:
        """Returns the number of updates currently in the aggregation queue."""
        return self._updates_in_queue

    def get_last_aggregation_time(self) -> str:
        """Returns the timestamp of the last aggregation in a readable format."""
        if self._last_aggregation_time:
            return datetime.datetime.fromtimestamp(self._last_aggregation_time).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

    def get_model_metrics(self) -> List[Dict[str, Any]]:
        """
        Returns a list of all historical model evaluation metrics by fetching
        them directly from the ModelManager.
        """
        if self.model_manager:
            return self.model_manager.get_metrics_history()
        self.logger.warning("ModelManager not available to fetch metrics history.")
        return []

    def get_client_health_data(self) -> Dict[str, Any]:
        """Returns a detailed status of all connected clients, including reputation."""
        return self.client_manager.get_client_statuses()
        
    def get_server_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Reads the latest logs from the server log file and returns them as a list
        of dictionaries.
        """
        log_path = os.path.join(LOG_DIR, "server_logs.json")
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
        """Returns the status of the ModelManager module."""
        if self.model_manager and self.orchestrator: 
            status = {
                "model_version": self.model_manager.global_model_version,
                "last_model_update": self.get_last_aggregation_time(),
                "training_progress": f"{self.orchestrator.current_round_number}/{self.orchestrator.total_rounds}",
                "status": "ready" if not self.model_manager.has_model_converged() else "converged",
                "converged": self.model_manager.has_model_converged(),
                "aggregation_summary": self.model_manager.get_aggregation_summary()
            }
            return status
        return {"status": "error", "message": "Model Manager not initialized."}

    def get_sam_status(self) -> Dict[str, Any]:
        """Returns the status of the Secure Aggregation Module (SAM)."""
        if self.orchestrator:
            return {
                "aggregation_protocol": "SecAgg", "security_level": "High",
                "updates_in_queue": self.orchestrator.get_queue_size(),
                "failed_sessions": 0, "last_aggregation_time": self.get_last_aggregation_time(),
                "status": "active" if self.orchestrator.state != "FINISHED" else "inactive"
            }
        return {"status": "error", "message": "Orchestrator not initialized."}

    def get_adrm_status(self) -> Dict[str, Any]:
        """Returns the status of the new ML-based ADRM."""
        if self.orchestrator and hasattr(self.orchestrator, 'adrm_engine'):
            engine = self.orchestrator.adrm_engine
            model_manager = engine.model_manager
            response_system = engine.response_system
            
            # Report status based on the new ML model manager attributes
            status = {
                "status": "running_ml_mode",
                "blocked_clients_count": len(response_system.blocked_clients),
                "champion_is_trained": model_manager.champion_model.is_trained,
                "challenger_is_trained": model_manager.challenger_model.is_trained,
                "challenger_training_buffer_size": len(engine.training_data_buffer),
                "performance": model_manager.performance_log
            }
            return status
        return {"status": "error", "message": "ADRM not initialized."}
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Returns the status of the Orchestrator module."""
        if self.orchestrator:
            return {
                **self.orchestrator.get_orchestrator_progress(),
                "failed_updates_log": self.orchestrator.get_failed_updates_log()
            }
        return {"status": "error", "message": "Orchestrator not initialized."}

    def get_ppm_status(self) -> Dict[str, Any]:
        """Returns the status of the Privacy Preservation Module (PPM)."""
        if self.orchestrator and self.orchestrator.ppm:
            return self.orchestrator.ppm.get_status()
        return {"status": "error", "message": "PPM not initialized."}

    def get_scpm_status(self) -> Dict[str, Any]:
        """Returns the status of the SCPM itself."""
        return {
            "module_name": "SCPM",
            "status": "active" if self.is_server_ready() else "initializing",
            "tls_enabled": self.is_tls_enabled,
            "client_authentication_enabled": self.is_client_auth_enabled,
            "last_security_event": self.last_security_event,
            "active_protocols": self.get_active_protocols(),
            "description": "Manages communication protocols and server state."
        }
    
    def get_active_protocols(self) -> List[str]:
        """Returns a list of active communication protocols based on handlers."""
        protocols = []
        for handler in self.communication_handlers:
            if isinstance(handler, GrpcHandler):
                protocols.append("gRPC")
            elif isinstance(handler, ApiHandler):
                protocols.append("REST API")
        return protocols

    def trigger_model_update(self, round_number: int):
        """
        Sets a flag to indicate that a new model is available for clients.
        This is typically called by the Orchestrator after aggregation.
        """
        self._current_round = round_number
        self.new_model_available = True
        self.logger.info(f"Triggering model update for round {self._current_round}. New model is available.")

    def get_model_update_status_and_reset(self) -> bool:
        """
        Returns True if a new model is available and immediately resets the flag.
        This is for client heartbeats to check and receive the model only once.
        
        Returns:
            bool: True if a new model is available, False otherwise.
        """
        status = self.new_model_available
        if status:
            self.new_model_available = False
        return status
    
    async def admin_unblock_client(self, client_id: str) -> bool:
        """
        Provides an administrative interface to unblock a client via the API.

        This method acts as a safe facade, delegating the unblocking request to the
        ADRM's ResponseSystem. It's an `async` function to align with the `async`
        nature of the API handler that calls it.

        Args:
            client_id (str): The ID of the client to unblock.

        Returns:
            bool: True if the client was successfully unblocked, False otherwise.
        """
        self.logger.info(f"Received admin request to unblock client '{client_id}'.")
        
        # Check that the ADRM engine is available before attempting to use it
        if self.orchestrator and hasattr(self.orchestrator, 'adrm_engine'):
            response_system = self.orchestrator.adrm_engine.response_system
            
            # The underlying unblock_client method in ResponseSystem is synchronous,
            # so we call it directly without 'await'.
            success = response_system.unblock_client(client_id)
            
            if success:
                self.logger.info(f"Successfully unblocked client '{client_id}' via ADRM Response System.")
            else:
                self.logger.warning(f"Failed to unblock client '{client_id}'. The client may not have been on the blocklist.")
            return success
        else:
            self.logger.error("ADRM system is not initialized. Cannot process unblock request.")
            return False