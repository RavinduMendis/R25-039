import logging
import time
import asyncio
import json
import random
import os
import datetime
from typing import Dict, List, Any, Set, Optional

from log_manager.log_manager import ContextAdapter
from adrm.response_system import ResponseSystem

# File paths for persistent storage
CLIENT_DATA_FILE = "database/client_data.json"
TEMP_CLIENT_DATA_FILE = "database/client_data.json.tmp"


class ClientInfo:
    """Holds information about an individual client."""
    def __init__(
        self,
        client_id: str,
        ip_address: str,
        client_type: str,
        status: str = "connected",
        last_heartbeat: Optional[int] = None,
        reputation: int = 100,
        last_successful_round: int = 0,
        reputation_history: List[int] = None,
        uptime_start_time: Optional[int] = None,
        latency: float = 0.0,
        last_round_participated: int = 0,
        participation_history: List[Dict[str, Any]] = None
    ):
        self.client_id = client_id
        self.ip_address = ip_address
        self.client_type = client_type
        self.status = status
        current_time = int(time.time())
        self.last_heartbeat = last_heartbeat if last_heartbeat is not None else current_time
        self.uptime_start_time = uptime_start_time if uptime_start_time is not None else current_time
        self.reputation = reputation
        self.last_successful_round = last_successful_round
        self.reputation_history = reputation_history if reputation_history is not None else [100]
        self.latency = latency
        self.last_round_participated = last_round_participated
        self.participation_history = participation_history if participation_history is not None else []

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ClientInfo":
        instance = ClientInfo(
            client_id=data['client_id'], ip_address=data['ip_address'], client_type=data['client_type'],
            status=data.get('status', 'connected'), last_heartbeat=data.get('last_heartbeat'),
            reputation=data.get('reputation', 100), last_successful_round=data.get('last_successful_round', 0),
            reputation_history=data.get('reputation_history', [100]), uptime_start_time=data.get('uptime_start_time'),
            latency=data.get('latency', 0.0)
        )
        instance.last_round_participated = data.get('last_round_participated', 0)
        instance.participation_history = data.get('participation_history', [])
        return instance

    def __repr__(self):
        return f"ClientInfo(id='{self.client_id}', ip='{self.ip_address}', status='{self.status}', rep={self.reputation})"


class ClientManager:
    """Manages the state and lifecycle of clients connected to the FL server."""

    # UPDATED: The __init__ no longer requires response_system to break the circular dependency
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        # UPDATED: Initialize response_system as None. It will be set later.
        self.response_system: Optional[ResponseSystem] = None
        self.connected_clients: Dict[str, ClientInfo] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        self.heartbeat_timeout_seconds = self.cfg.get("heartbeat_timeout_seconds", 10)
        self.grace_period_timeout = self.cfg.get("grace_period_timeout", 300)
        self.status_check_interval_seconds = self.cfg.get("status_check_interval_seconds", 1)
        self.status_check_task = None
        self.clients_in_current_round: List[str] = []
        self.clients_notified_for_round: Set[str] = set()
        self._lock = asyncio.Lock()
        self._load_clients()
        self.logger.info(f"ClientManager initialized. Loaded {len(self.connected_clients)} clients.")

    # NEW: Setter method to resolve the circular dependency
    def set_response_system(self, response_system: ResponseSystem):
        """Sets the ResponseSystem instance after initialization."""
        self.response_system = response_system
        self.logger.info("ResponseSystem dependency injected into ClientManager.")

    def _load_clients(self):
        try:
            os.makedirs(os.path.dirname(CLIENT_DATA_FILE), exist_ok=True)
            if os.path.exists(CLIENT_DATA_FILE):
                with open(CLIENT_DATA_FILE, "r") as f:
                    data = json.load(f)
                    self.connected_clients = {
                        client_id: ClientInfo.from_dict(info) for client_id, info in data.items()
                    }
                for c in self.connected_clients.values():
                    c.status = "connected"; c.uptime_start_time = int(time.time())
                self.logger.info(f"Loaded {len(self.connected_clients)} clients from {CLIENT_DATA_FILE}.")
            else:
                self.logger.info("No existing client data file found.")
        except (IOError, json.JSONDecodeError, TypeError) as e:
            self.logger.error(f"Failed to load client data: {e}. Starting fresh.", exc_info=True)
            self.connected_clients = {}

    def _save_clients_nolock(self):
        try:
            with open(TEMP_CLIENT_DATA_FILE, "w") as f:
                json.dump({cid: info.to_dict() for cid, info in self.connected_clients.items()}, f, indent=4)
            os.replace(TEMP_CLIENT_DATA_FILE, CLIENT_DATA_FILE)
            self.logger.debug(f"Client data saved to {CLIENT_DATA_FILE}.")
        except IOError as e:
            self.logger.error(f"Failed to save client data: {e}")

    async def add_or_update_client(self, client_id: str, ip_address: str, client_type: str) -> None:
        async with self._lock:
            client_info = self.connected_clients.get(client_id)
            if client_info:
                client_info.ip_address = ip_address; client_info.client_type = client_type
                client_info.status = "connected"; client_info.last_heartbeat = int(time.time())
                self.logger.debug(f"Updated client info for {client_id}.")
            else:
                self.connected_clients[client_id] = ClientInfo(client_id, ip_address, client_type)
                self.logger.info(f"New client {client_id} added.")
            self._save_clients_nolock()

    async def update_client_heartbeat(self, client_id: str) -> bool:
        async with self._lock:
            client_info = self.connected_clients.get(client_id)
            if not client_info: return False
            client_info.last_heartbeat = int(time.time())
            if client_info.status == "disconnected":
                client_info.status = "connected"; client_info.uptime_start_time = int(time.time())
                self.logger.info(f"Client {client_id} reconnected (heartbeat).")
                self._save_clients_nolock()
            return True

    async def deregister_client(self, client_id: str):
        async with self._lock:
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
                self.logger.info(f"Client {client_id} deregistered. Remaining: {len(self.connected_clients)}")
                self._save_clients_nolock()

    async def _periodic_status_check(self):
        while True:
            await asyncio.sleep(self.status_check_interval_seconds)
            now = int(time.time()); clients_to_deregister = []; needs_save = False
            async with self._lock:
                for client_id, client_info in self.connected_clients.items():
                    delta = now - client_info.last_heartbeat
                    if client_info.status == "connected" and delta > self.heartbeat_timeout_seconds:
                        client_info.status = "disconnected"
                        self.logger.warning(f"Client {client_id} timed out -> disconnected."); needs_save = True
                    elif client_info.status == "disconnected" and delta > self.grace_period_timeout:
                        self.logger.warning(f"Client {client_id} exceeded grace period -> will be deregistered.")
                        clients_to_deregister.append(client_id)
                if needs_save: self._save_clients_nolock()
            for client_id in clients_to_deregister: await self.deregister_client(client_id)

    async def start_status_checker(self):
        if not self.status_check_task or self.status_check_task.done():
            self.status_check_task = asyncio.create_task(self._periodic_status_check())
            self.logger.info("Status checker started.")

    async def stop_status_checker(self):
        if self.status_check_task:
            self.status_check_task.cancel()
            try: await self.status_check_task
            except asyncio.CancelledError: self.logger.info("Status checker stopped.")
            self.status_check_task = None
        async with self._lock: self._save_clients_nolock()

    def _calculate_client_score(self, c: ClientInfo) -> float:
        rep_w, up_w, lat_w = 0.6, 0.3, 0.1; norm_rep = c.reputation / 100.0
        norm_up = min(1.0, (int(time.time()) - c.uptime_start_time) / 3600.0)
        norm_lat = 1.0 - (min(c.latency, 500) / 500.0)
        return rep_w * norm_rep + up_w * norm_up + lat_w * norm_lat

    async def get_eligible_clients_count(self) -> int:
        # Add a strict check at the beginning of the function.
        if not self.response_system:
            self.logger.warning("Cannot determine eligible clients: ResponseSystem is not yet set.")
            return 0

        count = 0
        async with self._lock:
            for cid, client in self.connected_clients.items():
                # Now that we know self.response_system exists, this check is safe.
                is_blocked = self.response_system.is_client_blocked(cid)
                if client.status == "connected" and client.reputation > 20 and not is_blocked:
                    count += 1
        return count
    
    async def select_clients_for_round(self, clients_per_round: int) -> List[str]:
        selected = []
        async with self._lock:
            # UPDATED: Added a check to ensure response_system is set before filtering
            if not self.response_system:
                self.logger.warning("Response system not set in ClientManager; cannot check for blocked clients.")
                return []
            
            connected_ids = [cid for cid, c in self.connected_clients.items() if c.status == "connected"]
            eligible_clients = [
                self.connected_clients[cid] for cid in connected_ids
                if self.connected_clients[cid].reputation > 50 and not self.response_system.is_client_blocked(cid)
            ]
            if len(eligible_clients) < clients_per_round:
                self.logger.warning(f"Not enough eligible clients: {len(eligible_clients)} available, {clients_per_round} required.")
                return []
            eligible_clients.sort(key=lambda c: (c.last_round_participated, -self._calculate_client_score(c)))
            selected_clients_info = eligible_clients[:clients_per_round]
            selected = [c.client_id for c in selected_clients_info]
            self.clients_in_current_round = selected
            self.clients_notified_for_round = set()
        self.logger.info(f"Selected {len(selected)} clients for round using fair sorting: {selected}")
        return selected

    def is_client_connected(self, client_id: str) -> bool: return client_id in self.connected_clients and self.connected_clients[client_id].status == "connected"
    def get_connected_clients_ids(self) -> List[str]: return [cid for cid, c in self.connected_clients.items() if c.status == "connected"]
    def get_total_clients_count(self) -> int: return len(self.connected_clients)
    def get_connected_clients_count(self) -> int: return len(self.get_connected_clients_ids())

    async def get_client_statuses(self) -> Dict[str, Any]:
        async with self._lock:
            clients_dict = {}
            # UPDATED: Added a check to ensure response_system is set
            blocked_clients_details = self.response_system.blocked_clients if self.response_system else {}
            for cid, c in self.connected_clients.items():
                client_data = c.to_dict()
                client_data['is_blocked'] = cid in blocked_clients_details
                client_data['block_details'] = blocked_clients_details.get(cid)
                clients_dict[cid] = client_data
            return {
                "total_clients": self.get_total_clients_count(), "connected_clients": self.get_connected_clients_count(),
                "disconnected_clients": sum(1 for c in self.connected_clients.values() if c.status == "disconnected"),
                "clients": clients_dict,
            }

    def get_status(self) -> Dict[str, Any]:
        return {"total_clients": self.get_total_clients_count(), "connected_clients": self.get_connected_clients_count(), "status_checker_running": self.status_check_task is not None and not self.status_check_task.done()}

    async def penalize_client(self, client_id: str, penalty: int = 10):
        async with self._lock:
            if client_id in self.connected_clients:
                c = self.connected_clients[client_id]; c.reputation = max(0, c.reputation - penalty)
                c.reputation_history.append(c.reputation)
                self.logger.warning(f"Client {client_id} penalized -> reputation {c.reputation}")
                self._save_clients_nolock()

    async def record_round_participation(self, client_id: str, round_number: int, global_metrics: Dict[str, Any]):
        async with self._lock:
            client_info = self.connected_clients.get(client_id)
            if not client_info: return
            client_info.last_round_participated = round_number
            participation_record = {"round": round_number, "timestamp": datetime.datetime.now().isoformat(), "global_accuracy": global_metrics.get("accuracy"), "global_loss": global_metrics.get("loss")}
            client_info.participation_history.append(participation_record)
            self.logger.info(f"Recorded participation for client {client_id} in round {round_number}.")
            self._save_clients_nolock()

    async def reset_round_clients(self):
        async with self._lock: self.clients_in_current_round = []; self.clients_notified_for_round = set()

    async def is_client_selected_and_unnotified(self, client_id: str) -> bool:
        async with self._lock:
            if client_id in self.clients_in_current_round and client_id not in self.clients_notified_for_round:
                self.clients_notified_for_round.add(client_id); return True
        return False

    def is_client_in_current_round(self, client_id: str) -> bool: return client_id in self.clients_in_current_round