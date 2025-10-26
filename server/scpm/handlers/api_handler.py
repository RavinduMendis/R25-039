# server/scpm/handlers/api_handler.py

import logging
from aiohttp import web
import json
from typing import TYPE_CHECKING, Dict, Any, List, Callable, Coroutine, Tuple
import torch
import aiohttp_cors
import asyncio
import time
import datetime
from functools import wraps

if TYPE_CHECKING:
    from server.client_manager import ClientManager
    from server.scpm.scpm import ServerControlPlaneManager
    from server.orchestrator import Orchestrator
    from server.model_manager.model_manager import ModelManager

# Helper type for type hinting the decorator
HandlerResult = Coroutine[Any, Any, Tuple[Dict[str, Any], int]]
DecoratedHandler = Callable[['ApiHandler', web.Request], HandlerResult]


def api_handler(func: DecoratedHandler) -> Callable[['ApiHandler', web.Request], Coroutine[Any, Any, web.Response]]:
    """
    Decorator to streamline API handlers.
    
    This decorator wraps the core logic of an API endpoint to provide
    standardized error handling, logging, and JSON response formatting.
    It eliminates the need for repetitive try/except blocks and response
    creation in each handler.
    """
    @wraps(func)
    async def wrapper(self: 'ApiHandler', request: web.Request) -> web.Response:
        try:
            # Execute the core logic of the handler
            response_data, status_code = await func(self, request)
            return web.json_response({"status": "success", "data": response_data}, status=status_code)
        
        except Exception as e:
            # Log errors with context and return a standardized error response
            self.logger.error(f"Error in handler '{func.__name__}' for {request.path}: {e}", exc_info=True)
            status_code = getattr(e, 'status_code', 500)
            error_message = str(e) if hasattr(e, 'status_code') else "Internal Server Error"
            return web.json_response({"status": "error", "message": error_message}, status=status_code)
            
    return wrapper


class ApiHandler:
    """
    Handles all REST API endpoints for the Federated Learning Server dashboard.

    This class sets up a web server using aiohttp to expose various endpoints
    for monitoring and controlling the federated learning process. It provides
    real-time data on server status, client health, model metrics, and
    training progress.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager', model_manager: 'ModelManager', orchestrator: 'Orchestrator'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.model_manager = model_manager
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app = web.Application()
        
        self.runner = None
        self.site = None

        self._setup_routes()
        self._setup_cors()
        self.logger.info("ApiHandler initialized with web routes and CORS configured.")

    async def _ensure_awaited(self, result: Any) -> Any:
        """
        Helper method to await a result if it's a coroutine, otherwise return it directly.
        This makes the handlers robust against mixed sync/async methods in underlying managers.
        """
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _setup_cors(self):
        """
        Configures Cross-Origin Resource Sharing (CORS) for the application.
        This allows a web-based dashboard on a different origin to access the API.
        """
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*",
            )
        })
        for route in list(self.app.router.routes()):
            cors.add(route)
        self.logger.info("CORS configured.")

    def _setup_routes(self):
        """Configures the routes for the aiohttp web application."""
        routes = [
            # Server & Training Status
            ('GET', '/api/status', self.get_server_status),
            ('GET', '/api/overview', self.get_overview_data),
            ('GET', '/api/orchestrator_progress', self.get_orchestrator_progress),
            
            # Model & Metrics
            ('GET', '/api/metrics', self.get_model_metrics_data),
            ('GET', '/api/metrics_history', self.get_metrics_history),
            ('GET', '/api/model/metrics_details', self.get_model_metrics_details),
            ('GET', '/api/model', self.get_global_model_json),
            ('GET', '/api/model/bytes', self.get_global_model_bytes),
            ('POST', '/api/submit_update', self.submit_model_update),
            ('GET', '/api/evaluate_model', self.evaluate_model),

            # Client Status
            ('GET', '/api/client_health', self.get_client_health),
            ('GET', '/api/client_privacy_methods', self.get_client_privacy_methods),
            ('GET', '/api/client_heartbeat', self.client_heartbeat),

            # System Internals & Logs
            ('GET', '/api/logs', self.get_logs),
            ('GET', '/api/module_status/mm', self.get_mm_status),
            ('GET', '/api/module_status/sam', self.get_sam_status),
            ('GET', '/api/module_status/adrm', self.get_adrm_status),
            ('GET', '/api/module_status/ppm', self.get_ppm_status),
            ('GET', '/api/module_status/scpm', self.get_scpm_status),
            ('GET', '/api/module_status/orchestrator', self.get_orchestrator_status),
            
            # Admin Endpoints for ADRM
            ('POST', '/api/admin/adrm/unblock/{client_id}', self.admin_unblock_client),
            ('DELETE', '/api/admin/adrm/history/{client_id}', self.admin_reset_client_history),
            ('PUT', '/api/admin/adrm/config', self.admin_update_adrm_config),
        ]
        for method, path, handler in routes:
            self.app.router.add_route(method, path, handler)
            
        self.logger.info("API routes configured.")

    # --- API ENDPOINT HANDLERS ---

    @api_handler
    async def get_server_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Fetches the overall server status from the SCPM."""
        status_data = await self._ensure_awaited(self.scpm.get_server_status())
        return status_data, 200

    @api_handler
    async def get_overview_data(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Gathers and formats comprehensive training overview data."""
        # FIX: Replaced asyncio.gather with sequential awaited calls for robustness.
        training_stats = await self._ensure_awaited(self.orchestrator.get_training_stats())
        server_ready = await self._ensure_awaited(self.scpm.is_server_ready())
        connected_clients = await self._ensure_awaited(self.client_manager.get_connected_clients_count())
        queue_size = await self._ensure_awaited(self.orchestrator.get_queue_size())
        
        current_time = time.time()
        
        # FIX: Correctly retrieve the timestamp and perform the check separately.
        last_agg_ts = training_stats.get("last_aggregation_timestamp", 0.0)
        time_since_last_agg_formatted = "No aggregation yet"
        
        if last_agg_ts > 0:
            time_since_last_agg = current_time - last_agg_ts
            if time_since_last_agg < 60:
                time_since_last_agg_formatted = f"{int(time_since_last_agg)}s ago"
            elif time_since_last_agg < 3600:
                time_since_last_agg_formatted = f"{int(time_since_last_agg // 60)}m ago"
            else:
                time_since_last_agg_formatted = f"{int(time_since_last_agg // 3600)}h ago"

        total_rounds = max(training_stats.get("total_rounds", 1), 1)
        current_round = training_stats.get("current_round", 0)

        data = {
            "server_status": {"text": "Online" if server_ready else "Offline", "class": "online" if server_ready else "offline"},
            "current_round": current_round,
            "total_rounds": training_stats.get("total_rounds", 0),
            "connected_clients": connected_clients,
            "updates_in_queue": queue_size,
            "selected_clients_count": training_stats.get("selected_clients_count", 0),
            "selected_clients": training_stats.get("selected_clients", []),
            "last_aggregation_time": training_stats.get("last_aggregation_time", "N/A"),
            "time_since_last_aggregation_formatted": time_since_last_agg_formatted,
            "round_duration_seconds": training_stats.get("round_duration_seconds", 0.0),
            "server_timestamp": current_time,
            "training_progress": {
                "percentage": (current_round / total_rounds) * 100,
                "rounds_remaining": max(0, total_rounds - current_round)
            }
        }
        return data, 200

    @api_handler
    async def get_model_metrics_data(self, request: web.Request) -> Tuple[List[Dict[str, Any]], int]:
        """Fetches the history of model evaluation metrics."""
        metrics = await self._ensure_awaited(self.scpm.get_model_metrics())
        return metrics, 200

    @api_handler
    async def get_client_health(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Fetches the health status of all connected clients."""
        # FIX: Added await with the helper to fix JSON serialization error.
        client_health = await self._ensure_awaited(self.scpm.get_client_health_data())
        return client_health, 200

    @api_handler
    async def get_logs(self, request: web.Request) -> Tuple[List[Dict[str, str]], int]:
        """Retrieves structured server logs with a configurable limit."""
        limit = int(request.query.get('limit', 100))
        logs = await self._ensure_awaited(self.scpm.get_server_logs(limit=limit))
        return logs, 200

    # --- Module Status Handlers ---
    @api_handler
    async def get_mm_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        status = await self._ensure_awaited(self.scpm.get_mm_status())
        return status, 200

    @api_handler
    async def get_sam_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        status = await self._ensure_awaited(self.scpm.get_sam_status())
        return status, 200

    @api_handler
    async def get_adrm_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        status = await self._ensure_awaited(self.scpm.get_adrm_status())
        return status, 200
    
    @api_handler
    async def get_ppm_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        status = await self._ensure_awaited(self.scpm.get_ppm_status())
        return status, 200

    @api_handler
    async def get_scpm_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        status = await self._ensure_awaited(self.scpm.get_scpm_status())
        return status, 200

    @api_handler
    async def get_orchestrator_status(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        status = await self._ensure_awaited(self.scpm.get_orchestrator_status())
        return status, 200

    # --- Model Interaction Handlers ---

    @api_handler
    async def get_global_model_json(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Returns the global model state and version as a JSON response."""
        model_state = await self._ensure_awaited(self.model_manager.get_global_model_state())
        version = await self._ensure_awaited(self.model_manager.get_global_model_version())
        serializable_state = {k: v.cpu().numpy().tolist() for k, v in model_state.items()}
        return {"model_state": serializable_state, "version": version}, 200

    async def get_global_model_bytes(self, request: web.Request) -> web.Response:
        """Provides the global model as a binary stream for clients."""
        try:
            model_data = await self._ensure_awaited(self.orchestrator.get_global_model_data())
            if model_data:
                return web.Response(body=model_data, content_type='application/octet-stream')
            raise web.HTTPNotFound(reason="Global model is not available.")
        except Exception as e:
            self.logger.error(f"Error serving global model bytes: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": "Failed to retrieve model data."}, status=500)

    @api_handler
    async def submit_model_update(self, request: web.Request) -> Tuple[Dict[str, str], int]:
        """Handles model update submissions from validated clients."""
        client_id = request.query.get("client_id")
        if not client_id:
            raise web.HTTPBadRequest(reason="Client ID is required.")

        is_valid = await self._ensure_awaited(self.client_manager.is_client_connected(client_id))
        is_in_round = await self._ensure_awaited(self.orchestrator.is_client_in_current_round(client_id))
        
        if not is_valid:
            raise web.HTTPForbidden(reason=f"Client {client_id} is not a valid, connected client.")
        if not is_in_round:
            raise web.HTTPForbidden(reason=f"Client {client_id} is not selected for the current training round.")

        try:
            update_data_json = await request.json()
            privacy_method = update_data_json.pop("privacy_method", "Unknown")
            model_update_dict = {k: torch.tensor(v) for k, v in update_data_json.items()}
        except (json.JSONDecodeError, TypeError, KeyError):
            raise web.HTTPBadRequest(reason="Invalid JSON or data format in request body.")

        await self._ensure_awaited(self.orchestrator.receive_client_update(client_id, model_update_dict, privacy_method))
        return {"message": f"Update from client {client_id} successfully queued."}, 200

    @api_handler
    async def evaluate_model(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Triggers a server-side evaluation of the global model."""
        metrics = await self._ensure_awaited(self.model_manager.evaluate_model())
        return metrics, 200

    # --- Client Communication & Progress Monitoring ---

    async def client_heartbeat(self, request: web.Request) -> web.Response:
        """Handles client heartbeats and proactively sends new models if ready."""
        client_id = request.query.get("client_id")
        if not client_id:
            raise web.HTTPBadRequest(reason="Client ID is required.")
        
        await self._ensure_awaited(self.client_manager.update_client_heartbeat(client_id))
        
        if await self._ensure_awaited(self.client_manager.is_client_selected_and_unnotified(client_id)):
            self.logger.info(f"Client {client_id} selected for new round. Sending model via heartbeat.")
            return await self.get_global_model_bytes(request)
        else:
            return web.json_response({"status": "acknowledged", "message": "Heartbeat received."})

    @api_handler
    async def get_orchestrator_progress(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Fetches the current state and progress of the orchestrator."""
        progress_data = await self._ensure_awaited(self.orchestrator.get_orchestrator_progress())
        return progress_data, 200

    @api_handler
    async def get_model_metrics_details(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Combines model metrics with training progress for a detailed view."""
        # FIX: Replaced asyncio.gather with sequential awaited calls for robustness.
        metrics_history = await self._ensure_awaited(self.model_manager.get_metrics_history())
        mm_status = await self._ensure_awaited(self.scpm.get_mm_status())
        training_stats = await self._ensure_awaited(self.orchestrator.get_training_stats())

        total_rounds = max(training_stats.get("total_rounds", 1), 1)
        current_round = training_stats.get("current_round", 0)

        response_data = {
            "model_version": mm_status.get("model_version", 0),
            "convergence_status": "Converged" if mm_status.get("converged", False) else "Training",
            "metrics_history": metrics_history,
            "training_progress": {
                "current_round": current_round,
                "total_rounds": training_stats.get("total_rounds", 0),
                "progress_percentage": (current_round / total_rounds) * 100
            },
            "last_model_update": mm_status.get("last_model_update", "N/A")
        }
        return response_data, 200

    @api_handler
    async def get_metrics_history(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Fetches the full history of model evaluation metrics."""
        metrics_history = await self._ensure_awaited(self.model_manager.get_metrics_history())
        return {"metrics_history": metrics_history}, 200

    @api_handler
    async def get_client_privacy_methods(self, request: web.Request) -> Tuple[Dict[str, str], int]:
        """Retrieves the privacy method used by each client in the current round."""
        privacy_methods = await self._ensure_awaited(self.orchestrator.get_client_privacy_methods())
        return {"client_privacy_methods": privacy_methods}, 200
        
    # --- Admin Handler Methods ---

    @api_handler
    async def admin_unblock_client(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Admin endpoint to manually unblock a client."""
        client_id = request.match_info.get('client_id')
        if not client_id:
            raise web.HTTPBadRequest(reason="Client ID must be provided in the URL path.")
        
        success = await self._ensure_awaited(self.scpm.admin_unblock_client(client_id))
        if success:
            return {"message": f"Client '{client_id}' has been unblocked."}, 200
        else:
            raise web.HTTPNotFound(reason=f"Client '{client_id}' was not found or not blocked.")

    @api_handler
    async def admin_reset_client_history(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Admin endpoint to delete a client's learned history from ADRM."""
        client_id = request.match_info.get('client_id')
        if not client_id:
            raise web.HTTPBadRequest(reason="Client ID must be provided in the URL path.")
            
        await self._ensure_awaited(self.scpm.admin_reset_client_history(client_id))
        return {"message": f"History for client '{client_id}' has been reset."}, 200

    @api_handler
    async def admin_update_adrm_config(self, request: web.Request) -> Tuple[Dict[str, Any], int]:
        """Admin endpoint to update the ADRM configuration in real-time."""
        try:
            new_config = await request.json()
            updated_keys = await self._ensure_awaited(self.scpm.admin_update_adrm_config(new_config))
            return {"message": "ADRM config updated successfully.", "updated_keys": updated_keys}, 200
        except json.JSONDecodeError:
            raise web.HTTPBadRequest(reason="Invalid JSON format provided in the request body.")

    # --- Server Lifecycle Methods ---

    async def start_listener(self, host: str = '0.0.0.0', port: int = 8080):
        """Starts the aiohttp web server listener."""
        if self.runner is None:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, host, port)
            await self.site.start()
            self.logger.info(f"API server started successfully on http://{host}:{port}")
        else:
            self.logger.warning("API server is already running.")

    async def stop_listener(self):
        """Stops the aiohttp web server gracefully."""
        if self.runner:
            self.logger.info("Stopping API server...")
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            self.logger.info("API server stopped.")
        else:
            self.logger.info("API server is not currently running.")