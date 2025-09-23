# server/adrm/response_system.py

import json
import os
import datetime
import asyncio
from typing import TYPE_CHECKING
from . import config
from .logger_setup import setup_loggers

if TYPE_CHECKING:
    from server.client_manager import ClientManager

gen_logger, audit_logger = setup_loggers()

class ResponseSystem:
    """Handles graduated responses like penalties, blocks, and quarantines."""

    def __init__(self, client_manager: 'ClientManager'):
        self.client_manager = client_manager
        self.blocked_clients = {}
        self.quarantined_updates = {} # For manual review
        self._load_blocked_clients()

    def _load_blocked_clients(self):
        """Loads blocked clients from a JSON file."""
        if os.path.exists(config.BLOCKED_CLIENTS_FILE):
            try:
                with open(config.BLOCKED_CLIENTS_FILE, 'r') as f:
                    self.blocked_clients = json.load(f)
                gen_logger.info(f"Loaded {len(self.blocked_clients)} blocked clients from file.")
            except (IOError, json.JSONDecodeError) as e:
                gen_logger.error(f"Failed to load blocked clients from file: {e}")

    def _save_blocked_clients(self):
        """Saves the current blocked clients to a JSON file."""
        try:
            with open(config.BLOCKED_CLIENTS_FILE, 'w') as f:
                json.dump(self.blocked_clients, f, indent=4)
            audit_logger.info(f"Blocklist with {len(self.blocked_clients)} clients saved to file.")
        except IOError as e:
            gen_logger.error(f"Failed to save blocked clients to file: {e}")

    def trigger_response(self, client_id: str, severity: str, reason: str, details: dict):
        """Triggers a response based on the severity of the anomaly."""
        audit_logger.warning(f"Response triggered for '{client_id}'. Severity: {severity}. Reason: {reason}")

        if severity == 'low':
            # Apply a reputation penalty instead of a block
            penalty = 25
            asyncio.create_task(self.client_manager.penalize_client(client_id, penalty=penalty))
            gen_logger.info(f"Low severity anomaly for '{client_id}'. Applied {penalty}-point reputation penalty.")

        elif severity == 'medium':
            # Block for a dynamic, shorter duration
            duration = int(config.BLOCK_DURATION_MINUTES / 2)
            self._block_client(client_id, reason, details, duration_minutes=duration)
            
        elif severity == 'high':
            # Block for the full duration and quarantine the update
            self._block_client(client_id, reason, details, duration_minutes=config.BLOCK_DURATION_MINUTES)
            self.quarantined_updates[client_id] = {
                "timestamp": datetime.datetime.now().isoformat(),
                "reason": reason,
                "details": details
            }
            gen_logger.warning(f"High severity anomaly for '{client_id}'. Update quarantined for review.")

    def _block_client(self, client_id: str, reason: str, details: dict, duration_minutes: int):
        """Internal method to block a client and apply a reputation penalty."""
        now = datetime.datetime.now()
        expiration = now + datetime.timedelta(minutes=duration_minutes)
        self.blocked_clients[client_id] = {
            "block_timestamp": now.isoformat(), "block_expiration_timestamp": expiration.timestamp(),
            "reason": reason, **details
        }

        # Apply a significant reputation penalty for the blocking offense.
        penalty = config.REPUTATION_PENALTY_FOR_BLOCK
        # Use asyncio.create_task to call the async penalize_client method
        # from this synchronous function without blocking.
        asyncio.create_task(self.client_manager.penalize_client(client_id, penalty=penalty))
        
        log_message = f"Client '{client_id}' blocked for {duration_minutes} minutes. Reason: {reason}"
        gen_logger.warning(log_message)
        # Update audit log to include the penalty for a more complete record.
        audit_logger.warning(f"{log_message} | Reputation Penalty: -{penalty} points.")
        self._save_blocked_clients()

    def is_client_blocked(self, client_id: str) -> bool:
        """Checks if a client is currently blocked, unblocking them if expired."""
        if client_id in self.blocked_clients:
            expiration = self.blocked_clients[client_id]["block_expiration_timestamp"]
            if datetime.datetime.now().timestamp() < expiration:
                return True
            else:
                del self.blocked_clients[client_id]
                log_message = f"Client '{client_id}' unblocked. Duration expired."
                gen_logger.info(log_message)
                audit_logger.info(log_message)
                self._save_blocked_clients()
                return False
        return False
        
    def unblock_client(self, client_id: str):
        """Manually removes a client from the blocklist."""
        if client_id in self.blocked_clients:
            del self.blocked_clients[client_id]
            self._save_blocked_clients()
            gen_logger.warning(f"Admin manually unblocked client '{client_id}'.")
            audit_logger.warning(f"ADMIN ACTION: Unblocked client '{client_id}'.")
            return True
        return False