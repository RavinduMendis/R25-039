import logging
from aiohttp import web
import json
import os
from typing import TYPE_CHECKING, Dict, Any, List
import torch
import aiohttp_cors
import io
import asyncio
import time
import datetime

if TYPE_CHECKING:
    from client_manager import ClientManager
    from scpm.scpm import ServerControlPlaneManager
    from server.orchestrator import Orchestrator
    from server.model_manager.model_manager import ModelManager


class ApiHandler:
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager', model_manager: 'ModelManager', orchestrator: 'Orchestrator'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.model_manager = model_manager
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app = web.Application()
        self._setup_routes()
        self._setup_cors()

        self.runner = None
        self.site = None
        self.logger.info("ApiHandler initialized with web routes and CORS configured.")

    def _setup_cors(self):
        """
        Configures CORS for the application.
        In a production environment, you should replace the '*' with a specific origin (e.g., 'https://your-dashboard.com').
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
        self.app.router.add_get('/api/status', self.get_server_status)
        self.app.router.add_get('/api/overview', self.get_overview_data)
        self.app.router.add_get('/api/metrics', self.get_model_metrics_data)
        self.app.router.add_get('/api/client_health', self.get_client_health)
        self.app.router.add_get('/api/logs', self.get_logs)
        self.app.router.add_get('/api/module_status/mm', self.get_mm_status)
        self.app.router.add_get('/api/module_status/sam', self.get_sam_status)
        self.app.router.add_get('/api/module_status/adrm', self.get_adrm_status)
        self.app.router.add_get('/api/module_status/ppm', self.get_ppm_status)
        self.app.router.add_get('/api/module_status/scpm', self.get_scpm_status)
        self.app.router.add_get('/api/model', self.get_global_model_json)
        self.app.router.add_get('/api/model/bytes', self.get_global_model_bytes)
        self.app.router.add_post('/api/submit_update', self.submit_model_update)
        self.app.router.add_get('/api/evaluate_model', self.evaluate_model)
        self.logger.info("API routes configured.")

    async def _handle_request(self, request_handler, *args, **kwargs):
        """Generic request handler to wrap API calls with consistent error handling and logging."""
        request = args[0]
        self.logger.info(f"Received {request.method} {request.path} request.")
        try:
            response_data, status_code = await request_handler(*args, **kwargs)
            if isinstance(response_data, web.Response):
                return response_data
            return web.json_response({"status": "success", "data": response_data}, status=status_code)
        except web.HTTPError as e:
            self.logger.error(f"HTTP Error for {request.path}: {e.reason}", exc_info=True)
            return web.json_response({"status": "error", "message": e.reason}, status=e.status)
        except Exception as e:
            self.logger.error(f"Internal Server Error for {request.path}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": "An internal server error occurred."}, status=500)

    async def get_server_status(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_server_status, request)

    async def _get_server_status(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        status_data = self.scpm.get_server_status()
        return status_data, 200

    async def get_overview_data(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_overview_data, request)

    async def _get_overview_data(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        """Enhanced overview data with comprehensive timing information."""
        try:
            # Get training stats from orchestrator
            training_stats = self.orchestrator.get_training_stats()
            
            # Get current timestamp for dashboard refresh
            current_time = time.time()
            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate time since last aggregation
            time_since_last_agg = 0
            time_since_last_agg_formatted = "No aggregation yet"
            if training_stats.get("last_aggregation_timestamp", 0.0) > 0:
                time_since_last_agg = current_time - training_stats["last_aggregation_timestamp"]
                if time_since_last_agg < 60:
                    time_since_last_agg_formatted = f"{int(time_since_last_agg)} seconds ago"
                elif time_since_last_agg < 3600:
                    time_since_last_agg_formatted = f"{int(time_since_last_agg // 60)} minutes ago"
                else:
                    time_since_last_agg_formatted = f"{int(time_since_last_agg // 3600)} hours ago"
            
            data = {
                "server_status": {
                    "text": "Online" if self.scpm.is_server_ready() else "Offline", 
                    "class": "online" if self.scpm.is_server_ready() else "offline"
                },
                "current_round": training_stats.get("current_round", 0),
                "total_rounds": training_stats.get("total_rounds", 0),
                "connected_clients": self.client_manager.get_connected_clients_count(),
                "updates_in_queue": self.orchestrator.update_queue.qsize(),
                "selected_clients_count": training_stats.get("selected_clients_count", 0),
                "selected_clients": training_stats.get("selected_clients", []),
                
                # Enhanced timing information
                "last_aggregation_time": training_stats.get("last_aggregation_time", "No aggregation yet"),
                "last_aggregation_timestamp": training_stats.get("last_aggregation_timestamp", 0.0),
                "time_since_last_aggregation": time_since_last_agg,
                "time_since_last_aggregation_formatted": time_since_last_agg_formatted,
                "round_duration_seconds": training_stats.get("round_duration_seconds", 0.0),
                "round_duration_formatted": f"{training_stats.get('round_duration_seconds', 0.0):.2f}s",
                
                # Server timestamp for dashboard sync
                "server_timestamp": current_time,
                "server_datetime": current_datetime,
                
                # Training progress
                "training_progress": {
                    "percentage": (training_stats.get("current_round", 0) / max(training_stats.get("total_rounds", 1), 1)) * 100,
                    "rounds_completed": training_stats.get("current_round", 0),
                    "rounds_remaining": max(0, training_stats.get("total_rounds", 0) - training_stats.get("current_round", 0))
                }
            }
            
            self.logger.debug(f"Overview data generated: {data}")
            return data, 200
            
        except Exception as e:
            self.logger.error(f"Error generating overview data: {e}", exc_info=True)
            # Fallback to basic data if there's an error
            fallback_data = {
                "server_status": {"text": "Online", "class": "online"},
                "current_round": 0,
                "connected_clients": 0,
                "updates_in_queue": 0,
                "last_aggregation_time": "Error retrieving data",
                "error": str(e)
            }
            return fallback_data, 200

    async def get_model_metrics_data(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_model_metrics_data, request)

    async def _get_model_metrics_data(self, request: web.Request) -> tuple[List[Dict[str, Any]], int]:
        metrics = self.scpm.get_model_metrics()
        return metrics, 200

    async def get_client_health(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_client_health, request)

    async def _get_client_health(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        client_health = self.scpm.get_client_health_data()
        return client_health, 200

    async def get_logs(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_logs, request)

    async def _get_logs(self, request: web.Request) -> tuple[List[Dict[str, str]], int]:
        limit = int(request.query.get('limit', 50))
        logs = self.scpm.get_server_logs(limit=limit)
        return logs, 200

    async def get_mm_status(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_mm_status, request)

    async def _get_mm_status(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        status = self.scpm.get_mm_status()
        return status, 200

    async def get_sam_status(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_sam_status, request)

    async def _get_sam_status(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        status = self.scpm.get_sam_status()
        return status, 200

    async def get_adrm_status(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_adrm_status, request)

    async def _get_adrm_status(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        status = self.scpm.get_adrm_status()
        return status, 200

    async def get_ppm_status(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_ppm_status, request)

    async def _get_ppm_status(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        status = self.scpm.get_ppm_status()
        return status, 200

    async def get_scpm_status(self, request: web.Request) -> web.Response:
        """API endpoint to get the status of the Secure Communication and Protocol Enforcement Module (SCPM)."""
        return await self._handle_request(self._get_scpm_status, request)

    async def _get_scpm_status(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        """Internal method to fetch the SCPM status details from the module itself."""
        status = self.scpm.get_scpm_status()
        return status, 200

    async def get_global_model_json(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_global_model_json, request)

    async def _get_global_model_json(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        """Returns the global model state as a JSON response."""
        model_state = self.model_manager.get_global_model_state()
        version = self.model_manager.global_model_version
        serializable_state = {k: v.tolist() for k, v in model_state.items()}
        return {"model_state": serializable_state, "version": version}, 200

    async def get_global_model_bytes(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._get_global_model_bytes, request)

    async def _get_global_model_bytes(self, request: web.Request) -> tuple[web.Response, int]:
        """Returns the serialized global model data as a binary stream."""
        model_data = self.orchestrator.get_global_model_data()
        return web.Response(body=model_data, content_type='application/octet-stream'), 200

    async def submit_model_update(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._submit_model_update, request)

    async def _submit_model_update(self, request: web.Request) -> tuple[Dict[str, str], int]:
        client_id = request.query.get("client_id")
        if not client_id:
            raise web.HTTPBadRequest(reason="Client ID is required.")

        if not self.client_manager.is_client_connected(client_id):
            raise web.HTTPForbidden(reason=f"Client {client_id} is not connected or not a valid client.")

        if not self.orchestrator.is_client_in_current_round(client_id):
            raise web.HTTPForbidden(reason=f"Client {client_id} is not selected for the current training round.")

        try:
            update_data_json = await request.json()
            model_update_dict = {k: torch.tensor(v) for k, v in update_data_json.items()}
            
        except (json.JSONDecodeError, TypeError):
            raise web.HTTPBadRequest(reason="Invalid JSON or data format in request body.")

        await self.orchestrator.receive_client_update(client_id, model_update_dict)
        return {"message": f"Model update from client {client_id} received and added to queue."}, 200

    async def evaluate_model(self, request: web.Request) -> web.Response:
        return await self._handle_request(self._evaluate_model, request)

    async def _evaluate_model(self, request: web.Request) -> tuple[Dict[str, Any], int]:
        metrics = self.model_manager.evaluate_model()
        return metrics, 200

    async def start_listener(self, host: str = '0.0.0.0', port: int = 8080):
        if self.runner is None:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, host, port)
            await self.site.start()
            self.logger.info(f"API server for dashboard data started on http://{host}:{port}")
        else:
            self.logger.warning("API server already running.")

    async def stop_listener(self):
        if self.runner:
            self.logger.info("Stopping API server...")
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            self.logger.info("API server stopped.")
        else:
            self.logger.info("API server not running or already stopped.")