import asyncio
import grpc
import logging
import os
import sys
import uuid
import time
import json
import torch
import torch.nn as nn
from concurrent import futures
from collections import defaultdict
import datetime
from typing import Dict, Any, List, Optional
import io
import re

# =======================================================================
# === PATH CONFIGURATION TO FIX ABSOLUTE IMPORTS ===
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
    print(f"Added '{parent_dir}' to sys.path.")
# =======================================================================

# Add the 'scpm/protos' directory to the Python path
protos_path = os.path.join(current_dir, 'scpm', 'protos')
if protos_path not in sys.path:
    sys.path.append(protos_path)
    print(f"Added '{protos_path}' to sys.path.")

# --- CORRECTED IMPORT STATEMENTS ---
from log_manager.log_manager import configure_root_logging, add_json_file_handler, LOG_DIR
from scpm.scpm import ServerControlPlaneManager
from client_manager import ClientManager
from orchestrator import Orchestrator
from model_manager.model_manager import ModelManager
from ppm.ppm import PPM

# UPDATED: Import the new, modular ADRM components
from adrm.response_system import ResponseSystem
from adrm.model_manager import ADRMModelManager
from adrm.adrm_engine import ADRMEngine

root_logger = logging.getLogger()
configure_root_logging(root_logger)

add_json_file_handler(root_logger.name, "server_logs.json")

def load_server_config(file_path: str) -> Dict[str, Any]:
    """Loads server configuration from a JSON file."""
    try:
        with open(file_path, 'r') as f:
            config = json.load(f)
            root_logger.info("Configuration loaded successfully.")
            return config
    except FileNotFoundError:
        root_logger.warning(f"Configuration file not found at {file_path}. Using default configuration.")
        return {
            "federated_learning": {"training_rounds": 100, "clients_per_round": 3, "round_timeout_seconds": 60, "min_clients_for_aggregation": 2, "secure_aggregation_threshold": 3},
            "security": {"tls_enabled": True, "client_authentication_enabled": True, "jwt_secret": "your_secret_key"},
            "privacy": {"dp": {"epsilon": 1.0, "delta": 1e-5, "sensitivity": 1.0}, "he": {"active": True}},
            "communication": {"grpc": {"port": 50051}, "api": {"port": 8080}},
            "heartbeat_timeout_seconds": 60, "status_check_interval_seconds": 10, "model_name": "SimpleCNN"
        }
    except json.JSONDecodeError:
        root_logger.error(f"Invalid JSON format in configuration file at {file_path}. Exiting.")
        sys.exit(1)


async def main():
    """Main entry point for the Federated Learning Server."""
    logger = logging.getLogger(__name__)
    logger.info("Starting Federated Learning Server...")
    SERVER_CONFIG = load_server_config(os.path.join(current_dir, "config.json"))

    # ================================================================================
    # === UPDATED INITIALIZATION LOGIC FOR ADVANCED ADRM =============================
    # ================================================================================
    # The ClientManager must be created first.
    # NOTE: The ClientManager's __init__ must be updated to remove the response_system dependency.
    # I will assume that change is made for this logic to work.
    client_manager = ClientManager(SERVER_CONFIG)
    logger.info("ClientManager initialized.")
    
    # The ResponseSystem is created next, and the client_manager is passed to it.
    adrm_response_system = ResponseSystem(client_manager)
    
    # The ClientManager is now given a reference to the response system to resolve the circular dependency.
    client_manager.set_response_system(adrm_response_system)
    
    adrm_model_manager = ADRMModelManager()
    adrm_engine = ADRMEngine(adrm_model_manager, adrm_response_system)
    logger.info("Modular ADRM initialized with dependencies.")
    # ================================================================================

    ppm = PPM(cfg=SERVER_CONFIG)
    logger.info("PPM module initialized.")
    
    model_manager = ModelManager(SERVER_CONFIG)
    logger.info("ModelManager initialized.")

    scpm = ServerControlPlaneManager(client_manager, model_manager)
    logger.info("ServerControlPlaneManager initialized.")

    orchestrator = Orchestrator(
        client_manager,
        model_manager,
        adrm_engine,
        ppm,
        SERVER_CONFIG
    )
    orchestrator.set_scpm(scpm)
    logger.info("Orchestrator initialized.")

    scpm.set_orchestrator(orchestrator)
    orchestrator_task = asyncio.create_task(orchestrator.start_training())
    logger.info("Federated learning training loop started.")
    communication_listener_tasks = await scpm.start_communication_listeners()
    logger.info("FLS communication listeners started successfully.")

    try:
        await asyncio.gather(
            *communication_listener_tasks,
            orchestrator_task,
            client_manager.start_status_checker()
        )
    except asyncio.CancelledError:
        logger.info("Server shutdown initiated due to task cancellation.")
    except Exception as e:
        logger.exception(f"An unhandled error occurred in the main server loop: {e}")
    finally:
        await client_manager.stop_status_checker()
        logger.info("ClientManager status checker stopped.")
        await scpm.stop_communication_listeners()
        logger.info("FLS communication listeners stopped.")
        logger.info("Federated Learning Server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        root_logger.info("KeyboardInterrupt received. Shutting down server gracefully...")
    except Exception as e:
        root_logger.critical(f"Server exited with an unhandled error: {e}", exc_info=True)