# server/adrm/adrm_engine.py

import torch
import numpy as np
from typing import Dict, Any, List

from . import config
from .logger_setup import setup_loggers
from .model_manager import ADRMModelManager
from .response_system import ResponseSystem

gen_logger, audit_logger = setup_loggers()

class ADRMEngine:
    """
    The core detection engine for the ADRM, featuring a two-stage defense system:
    1. An ML-based check for each individual update.
    2. A statistical cross-client (peer) check for the entire round.
    """

    def __init__(self, model_manager: ADRMModelManager, response_system: ResponseSystem):
        self.model_manager = model_manager
        self.response_system = response_system
        self.training_data_buffer = []

    def _featurize_update(self, update: Dict[str, torch.Tensor]) -> np.ndarray:
        """Extracts a feature vector from a raw model update for the ML model."""
        if not update:
            return np.zeros((1, 5))

        # FIX: Filter for torch.Tensor types to ignore metadata like "privacy_method".
        tensor_values = [p for p in update.values() if isinstance(p, torch.Tensor)]
        if not tensor_values:
            return np.zeros((1, 5))

        flat_vector = torch.cat([p.view(-1) for p in tensor_values]).float()
        
        if flat_vector.numel() == 0:
            return np.zeros((1, 5))

        mean = torch.mean(flat_vector).item()
        std = torch.std(flat_vector).item()
        min_val = torch.min(flat_vector).item()
        max_val = torch.max(flat_vector).item()
        norm = torch.linalg.norm(flat_vector).item()
        
        return np.array([[mean, std, min_val, max_val, norm]])

    def process_update(self, client_id: str, update: Dict[str, Any]) -> bool:
        """
        STAGE 1: Analyzes an update using the Champion ML model and trains the Challenger.
        Returns True if the update is normal, False if it's an anomaly.
        """
        if self.response_system.is_client_blocked(client_id):
            gen_logger.warning(f"Update from blocked client '{client_id}' rejected.")
            return False

        features = self._featurize_update(update)
        is_anomaly = self.model_manager.champion_model.predict(features)
        
        if is_anomaly:
            reason = "Flagged as an anomaly by the Champion ML model."
            self.response_system.trigger_response(client_id, 'high', reason, {"features": features.tolist()})
            return False

        self.training_data_buffer.append(features[0])

        if len(self.training_data_buffer) >= config.CHALLENGER_TRAINING_BATCH_SIZE:
            gen_logger.info("Challenger training buffer full. Triggering retraining.")
            training_batch = np.array(self.training_data_buffer)
            self.model_manager.challenger_model.train(training_batch)
            self.model_manager.challenger_model.save(config.CHALLENGER_MODEL_PATH)
            self.training_data_buffer = []

        return True

    def _get_update_magnitude(self, update: Dict[str, Any]) -> float:
        """Helper to calculate the L2-norm for the statistical peer check."""
        if not update: return 0.0
        
        # FIX: Filter for torch.Tensor types to ignore metadata.
        tensor_values = [p for p in update.values() if isinstance(p, torch.Tensor)]
        if not tensor_values:
            return 0.0
            
        flat_vector = torch.cat([p.view(-1) for p in tensor_values]).float()
        return torch.linalg.norm(flat_vector).item()

    def detect_outliers_in_group(self, updates: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        STAGE 2: Statistical peer check. Detects outliers within a group of updates
        from a single round using Median Absolute Deviation (MAD).

        Returns a list of client IDs that are outliers.
        """
        if len(updates) < 3:
            gen_logger.info("Cross-client check skipped: Not enough updates for comparison.")
            return []

        magnitudes = {
            client_id: self._get_update_magnitude(update)
            for client_id, update in updates.items()
        }
        
        mag_values = np.array(list(magnitudes.values()))
        median = np.median(mag_values)
        mad = np.median(np.abs(mag_values - median))

        if mad < 1e-9: # Avoid division by zero
            return []

        outlier_ids = []
        for client_id, mag in magnitudes.items():
            modified_z_score = 0.6745 * (mag - median) / mad
            if modified_z_score > config.CROSS_CLIENT_THRESHOLD:
                outlier_ids.append(client_id)
                reason = "Flagged as a statistical outlier compared to peers in the same round."
                details = {
                    "magnitude": round(mag, 4),
                    "group_median": round(median, 4),
                    "modified_z_score": round(modified_z_score, 2)
                }
                audit_logger.warning(f"CROSS-CLIENT outlier detected: {client_id} with Z-Score={details['modified_z_score']}")
                self.response_system.trigger_response(client_id, 'high', reason, details)

        return outlier_ids
        
    def evaluate_and_swap_models(self, labeled_data):
        """
        Evaluates Champion and Challenger models and promotes the Challenger if it performs better.
        This should be called periodically by the main server orchestrator.
        """
        if not labeled_data:
            gen_logger.info("Model evaluation skipped: no labeled data provided.")
            return
            
        features, labels = zip(*labeled_data)
        features = np.array(features)
        labels = np.array(labels)

        champ_preds = self.model_manager.champion_model.model.predict(features)
        chall_preds = self.model_manager.challenger_model.model.predict(features)
        
        champ_preds = (champ_preds == -1).astype(int)
        chall_preds = (chall_preds == -1).astype(int)

        from sklearn.metrics import f1_score
        champ_score = f1_score(labels, champ_preds)
        chall_score = f1_score(labels, chall_preds)
        
        self.model_manager.update_performance_report(champ_score, chall_score)
        
        if chall_score > champ_score * config.PROMOTION_THRESHOLD:
            gen_logger.warning(f"Challenger F1-score ({chall_score:.4f}) exceeds champion ({champ_score:.4f}). Promoting.")
            self.model_manager.promote_challenger_to_champion()