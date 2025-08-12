import asyncio
import logging
import os
import sys
from typing import List, Any
from aiohttp import web

# =======================================================================
# === PATH CONFIGURATION TO FIX ABSOLUTE IMPORTS ===
# This block of code ensures that the project's root directory
# is added to the Python path, allowing for absolute imports like
# `from server.utils.log_manager import ...` to work correctly.
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
# All imports must now reference the 'server' package from the top level.
from utils.log_manager import configure_root_logging, add_json_file_handler, LOG_DIR
from scpm.scpm import ServerControlPlaneManager
from client_manager import ClientManager
from orchestrator import Orchestrator
from model_manager.model_manager import ModelManager 

root_logger = logging.getLogger()
configure_root_logging(root_logger) 

# Attach a JSON file handler for structured logging
add_json_file_handler("server", "server_log.json")
logger = logging.getLogger("server")

# Define a simple training configuration dictionary.
training_config_dict = {
    "min_clients_per_round": 3,
    "client_selection_ratio": 0.5,
    "max_rounds": 10,
    "model_name": "SimpleCNN",
    "dataset": "CIFAR-10"
}


async def main():
    """
    The main entry point for the Federated Learning Server.
    """
    logger.info("Starting Federated Learning Server (FLS)...")

    # Initialize core components
    client_manager = ClientManager()
    logger.info("ClientManager initialized.")

    # Start the client status checker right after initialization
    await client_manager.start_status_checker()

    scpm = ServerControlPlaneManager(client_manager)
    logger.info("ServerControlPlaneManager initialized.")

    orchestrator = Orchestrator(training_config_dict, client_manager, scpm)
    logger.info("Orchestrator initialized with a configuration dictionary.")

    # AVOID CIRCULAR DEPENDENCY: Set the orchestrator on the scpm instance.
    scpm.set_orchestrator(orchestrator)

    # Start the orchestrator's training loop
    orchestrator_task = asyncio.create_task(orchestrator.start_training())
    logger.info("Federated learning training loop started.")

    # Start communication listeners (gRPC, API)
    communication_listener_tasks = await scpm.start_communication_listeners()
    
    logger.info("FLS communication listeners started successfully.")
    
    try:
        await asyncio.gather(
            *communication_listener_tasks,
            orchestrator_task
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
        logger.info("KeyboardInterrupt received. Shutting down server gracefully...")
    except Exception as e:
        logger.critical(f"Server exited with an unhandled error: {e}", exc_info=True)