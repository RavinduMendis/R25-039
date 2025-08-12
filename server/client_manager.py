# server/client_manager.py

import logging
import time
import asyncio
import json
import random
import os
from typing import Dict, Union, List, Tuple, Any

# Import ContextAdapter for consistent logging
from utils.log_manager import ContextAdapter

# Define the file path for persistent storage of client data
CLIENT_DATA_FILE = "client_data.json"

# Define a simple data structure for client information
class ClientInfo:
    def __init__(self, client_id: str, ip_address: str, client_type: str, status: str = "connected", last_heartbeat: int = int(time.time()), reputation: int = 100):
        self.client_id = client_id
        self.ip_address = ip_address
        self.client_type = client_type # e.g., "WebSocket", "gRPC"
        self.status = status # You can manage more detailed statuses here
        self.last_heartbeat = last_heartbeat # Timestamp of last received heartbeat
        self.reputation = reputation # A simple score to track client behavior

    def to_dict(self) -> Dict[str, Any]:
        """Converts the ClientInfo object to a dictionary for JSON serialization."""
        return self.__dict__

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ClientInfo':
        """Creates a ClientInfo object from a dictionary."""
        return ClientInfo(**data)

    def __repr__(self):
        return f"ClientInfo(id='{self.client_id}', ip='{self.ip_address}', type='{self.client_type}', status='{self.status}', last_heartbeat={self.last_heartbeat}, reputation={self.reputation})"

class ClientManager:
    def __init__(self):
        self.connected_clients: Dict[str, ClientInfo] = {} # {client_id: ClientInfo}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        
        self.heartbeat_timeout_seconds = 30 # Clients are considered disconnected if no heartbeat in this time
        self.status_check_interval_seconds = 10 # How often to check client statuses
        self.status_check_task = None # asyncio.Task for the status checker
        self.clients_in_current_round: List[str] = []
        self.clients_notified_for_round: List[str] = []
        
        # Load any previously saved client data on startup
        self._load_clients()
        self.logger.info(f"ClientManager initialized. Loaded {len(self.connected_clients)} clients.")

    def _load_clients(self):
        """Loads client data from a JSON file if it exists."""
        if os.path.exists(CLIENT_DATA_FILE):
            try:
                with open(CLIENT_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.connected_clients = {
                        client_id: ClientInfo.from_dict(info)
                        for client_id, info in data.items()
                    }
                    self.logger.info(f"Successfully loaded {len(self.connected_clients)} clients from {CLIENT_DATA_FILE}.")
            except (IOError, json.JSONDecodeError) as e:
                self.logger.error(f"Failed to load client data from {CLIENT_DATA_FILE}: {e}")
        else:
            self.logger.info(f"No existing client data file found at {CLIENT_DATA_FILE}.")

    def _save_clients(self):
        """Saves current client data to a JSON file."""
        try:
            with open(CLIENT_DATA_FILE, 'w') as f:
                data = {
                    client_id: info.to_dict()
                    for client_id, info in self.connected_clients.items()
                }
                json.dump(data, f, indent=4)
            self.logger.info(f"Client data saved to {CLIENT_DATA_FILE}.")
        except IOError as e:
            self.logger.error(f"Failed to save client data to {CLIENT_DATA_FILE}: {e}")

    def add_or_update_client(self, client_id: str, ip_address: str, client_type: str) -> None:
        """Adds or updates a client's information and saves the changes."""
        client_info = self.connected_clients.get(client_id)
        if client_info:
            # Update existing client's info
            client_info.ip_address = ip_address
            client_info.client_type = client_type
            client_info.status = "connected"
            client_info.last_heartbeat = int(time.time())
            self.logger.debug(f"Updated client information for {client_id}.")
        else:
            # Add new client
            self.connected_clients[client_id] = ClientInfo(client_id, ip_address, client_type)
            self.logger.info(f"New client {client_id} added.")
        self._save_clients()

    def update_client_heartbeat(self, client_id: str) -> bool:
        """
        Updates the heartbeat for a specific client.
        Returns True if the client exists and was updated, False otherwise.
        """
        client_info = self.connected_clients.get(client_id)
        if client_info:
            client_info.last_heartbeat = int(time.time())
            # If the client was previously disconnected, mark it as reconnected.
            if client_info.status == "disconnected":
                client_info.status = "connected"
                self.logger.info(f"Client {client_id} reconnected (heartbeat received).")
                self._save_clients()
            return True
        return False

    async def _periodic_status_check(self):
        """
        Background task to periodically check client statuses based on heartbeats.
        """
        while True:
            await asyncio.sleep(self.status_check_interval_seconds)
            current_time = int(time.time())
            disconnected_clients = []
            
            for client_id, client_info in self.connected_clients.items():
                if client_info.status == "connected" and (current_time - client_info.last_heartbeat > self.heartbeat_timeout_seconds):
                    client_info.status = "disconnected"
                    self.logger.warning(f"Client {client_id} ({client_info.client_type}) heartbeat timeout. Marking as 'disconnected'.")
                    disconnected_clients.append(client_id)

            if disconnected_clients:
                self.logger.info(f"Detected {len(disconnected_clients)} disconnected clients. Saving state.")
                self._save_clients()
            
    async def start_status_checker(self):
        """Starts the periodic client status checking task."""
        if self.status_check_task is None or self.status_check_task.done():
            self.status_check_task = asyncio.create_task(self._periodic_status_check())
            self.logger.info("Client status checking task started.")

    async def stop_status_checker(self):
        """Stops the periodic client status checking task and saves client data."""
        if self.status_check_task:
            self.status_check_task.cancel()
            try:
                await self.status_check_task
            except asyncio.CancelledError:
                self.logger.info("Client status checking task cancelled.")
            self.status_check_task = None
        self._save_clients() # Save data on graceful shutdown
        
    def is_client_connected(self, client_id: str) -> bool:
        """Checks if a client is connected and active."""
        client_info = self.connected_clients.get(client_id)
        return client_info and client_info.status == "connected"

    def get_connected_clients_ids(self) -> List[str]:
        """Returns a list of IDs for all clients currently marked as 'connected'."""
        return [client_id for client_id, client_info in self.connected_clients.items() if client_info.status == "connected"]

    def get_all_clients_info(self) -> Dict[str, Dict[str, Any]]:
        """Returns detailed information for all clients, including disconnected ones."""
        return {
            client_id: info.to_dict()
            for client_id, info in self.connected_clients.items()
        }

    def get_total_clients_count(self) -> int:
        """Returns the total number of clients managed by the server (connected and disconnected)."""
        return len(self.connected_clients)

    def get_connected_clients_count(self) -> int:
        """Returns the number of clients currently marked as 'connected'."""
        return len(self.get_connected_clients_ids())

    def get_client_statuses(self) -> Dict[str, Any]:
        """
        Returns a dictionary of all managed clients, with their current status.
        This provides a quick overview for the dashboard.
        """
        status_summary = {
            "total_clients": self.get_total_clients_count(),
            "connected_clients": 0,
            "disconnected_clients": 0,
            "clients": {}
        }

        for client_id, client_info in self.connected_clients.items():
            if client_info.status == "connected":
                status_summary["connected_clients"] += 1
            elif client_info.status == "disconnected":
                status_summary["disconnected_clients"] += 1
            
            status_summary["clients"][client_id] = {
                "ip_address": client_info.ip_address,
                "client_type": client_info.client_type,
                "status": client_info.status,
                "last_heartbeat": client_info.last_heartbeat,
                "reputation": client_info.reputation
            }
            
        return status_summary

    def get_status(self) -> Dict[str, Any]:
        """
        Returns a summary of the ClientManager's current state.
        This method is correctly implemented to be called by scpm.py.
        """
        return {
            "total_clients": self.get_total_clients_count(),
            "connected_clients": self.get_connected_clients_count(),
            "status_checker_running": self.status_check_task is not None and not self.status_check_task.done()
        }

    # =================================================================
    # New methods for Orchestrator to manage clients for a round
    # =================================================================
    def select_clients_for_round(self, clients_per_round: int) -> List[str]:
        """Selects a number of connected clients for the next training round."""
        connected_clients = self.get_connected_clients_ids()
        
        # Filter out clients with low reputation
        eligible_clients = [c for c in connected_clients if self.connected_clients[c].reputation > 50]
        
        if len(eligible_clients) < clients_per_round:
            self.logger.warning("Not enough eligible clients to start a round.")
            return []
        
        # Use a more robust sampling method, e.g., weighted by reputation if needed.
        # For now, we'll stick to a simple random sample from eligible clients.
        selected = random.sample(eligible_clients, clients_per_round)
        self.clients_in_current_round = selected
        self.clients_notified_for_round = []
        self.logger.info(f"Selected {len(selected)} clients for the new round: {selected}")
        return selected

    def is_client_selected_and_unnotified(self, client_id: str) -> bool:
        """
        Checks if the client is selected for the current round and has not yet been notified.
        """
        if client_id in self.clients_in_current_round and client_id not in self.clients_notified_for_round:
            self.clients_notified_for_round.append(client_id)
            return True
        return False

    def is_client_in_current_round(self, client_id: str) -> bool:
        """Checks if a client is part of the current training round."""
        return client_id in self.clients_in_current_round
        
    def penalize_client(self, client_id: str, penalty: int = 10):
        """Reduces a client's reputation score, useful for ADRM."""
        if client_id in self.connected_clients:
            self.connected_clients[client_id].reputation -= penalty
            if self.connected_clients[client_id].reputation < 0:
                self.connected_clients[client_id].reputation = 0
            self.logger.warning(f"Client {client_id} penalized. New reputation: {self.connected_clients[client_id].reputation}")
            self._save_clients()

    def reset_round_clients(self):
        """Clears the client selection for the current round."""
        self.clients_in_current_round = []
        self.clients_notified_for_round = []