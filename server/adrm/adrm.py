# server/adrm/adrm.py

import logging
from typing import Dict, Any, List
import torch
import numpy as np
import datetime

class ADRM:
    """
    Attack Detection & Resilience Module.
    This module is responsible for detecting suspicious client updates
    and potentially implementing resilience mechanisms.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.total_updates_processed = 0
        self.suspicious_updates_detected = 0
        self.blocked_clients: List[str] = []
        self.update_history: Dict[str, Dict[str, Any]] = {}  # Stores learned behavior for each client
        self.anomaly_threshold = 3.0  # e.g., 3 standard deviations from the mean
        self.logger.info("ADRM initialized.")

    def _get_update_magnitude(self, update: Dict[str, Any]) -> float:
        """Calculates the L2 norm of the flattened model update."""
        with torch.no_grad():
            flat_tensor = torch.cat([p.view(-1) for p in update.values()])
            return torch.norm(flat_tensor).item()

    def learn_client_behavior(self, client_id: str, update: Dict[str, Any]):
        """
        Updates the statistical model for a client's normal behavior.
        This simulates the 'learning' process of the anomaly detection model.
        """
        magnitude = self._get_update_magnitude(update)
        if client_id not in self.update_history:
            # Initialize with the first update
            self.update_history[client_id] = {
                'count': 1,
                'mean_magnitude': magnitude,
                'sum_sq_diff': 0.0
            }
        else:
            history = self.update_history[client_id]
            count = history['count']
            mean_magnitude = history['mean_magnitude']
            sum_sq_diff = history['sum_sq_diff']

            # Update mean and sum of squared differences (Welford's algorithm)
            new_count = count + 1
            new_mean = mean_magnitude + (magnitude - mean_magnitude) / new_count
            new_sum_sq_diff = sum_sq_diff + (magnitude - new_mean) * (magnitude - mean_magnitude)

            history['count'] = new_count
            history['mean_magnitude'] = new_mean
            history['sum_sq_diff'] = new_sum_sq_diff

    def detect_suspicious_update(self, client_id: str, update: Dict[str, Any]) -> bool:
        """
        Detects if a new update is an anomaly based on the client's learned behavior.
        """
        self.total_updates_processed += 1
        
        if client_id not in self.update_history or self.update_history[client_id]['count'] < 5: # Need a few updates to establish a baseline
            self.learn_client_behavior(client_id, update)
            return False # Not enough data to make a reliable detection

        magnitude = self._get_update_magnitude(update)
        history = self.update_history[client_id]
        
        mean = history['mean_magnitude']
        count = history['count']
        
        # Calculate standard deviation
        std_dev = np.sqrt(history['sum_sq_diff'] / (count - 1)) if count > 1 else 0

        # Check if update is outside the anomaly threshold
        is_suspicious = abs(magnitude - mean) > self.anomaly_threshold * std_dev

        if is_suspicious:
            self.suspicious_updates_detected += 1
            self.logger.warning(f"Suspicious update detected from client '{client_id}'. Magnitude: {magnitude:.4f}, Learned Mean: {mean:.4f}, Std Dev: {std_dev:.4f}")
            return True
        else:
            # Update the learned behavior with the non-anomalous update
            self.learn_client_behavior(client_id, update)
            return False

    def get_adrm_status(self) -> Dict[str, Any]:
        """Provides a status summary of the ADRM."""
        return {
            "status": "running",
            "total_updates_processed": self.total_updates_processed,
            "suspicious_updates_detected": self.suspicious_updates_detected,
            "blocked_clients_count": len(self.blocked_clients),
            "learned_clients_count": len(self.update_history),
            "last_check_timestamp": str(datetime.datetime.now())
        }