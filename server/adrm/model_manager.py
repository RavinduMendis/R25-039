# server/adrm/model_manager.py

import os
import json
import datetime
from . import config
from .anomaly_model import AnomalyModel
from .logger_setup import setup_loggers

gen_logger, audit_logger = setup_loggers()

class ADRMModelManager:
    """Manages the lifecycle of Champion/Challenger ML models."""

    def __init__(self):
        gen_logger.info("Initializing ADRM ML Model Manager...")
        self.champion_model = AnomalyModel.load(config.CHAMPION_MODEL_PATH)
        self.challenger_model = AnomalyModel.load(config.CHALLENGER_MODEL_PATH)
        self.performance_log = self._load_performance_log()
        gen_logger.info("ADRM ML Model Manager initialized.")

    def _load_performance_log(self):
        """Loads model performance history from a JSON file."""
        try:
            if os.path.exists(config.PERFORMANCE_LOG_FILE):
                with open(config.PERFORMANCE_LOG_FILE, 'r') as f:
                    return json.load(f)
        except (IOError, json.JSONDecodeError):
            gen_logger.warning("Could not load performance log. Starting fresh.")
        return {"champion": 0.0, "challenger": 0.0, "history": []}

    def _save_performance_log(self):
        """Saves the performance log to a file."""
        try:
            with open(config.PERFORMANCE_LOG_FILE, 'w') as f:
                json.dump(self.performance_log, f, indent=4)
        except IOError as e:
            gen_logger.error(f"Failed to save performance log: {e}")

    def promote_challenger_to_champion(self):
        """Promotes the challenger to champion and resets the challenger."""
        audit_logger.warning("PROMOTING CHALLENGER TO CHAMPION.")
        
        # 1. Archive the old champion
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = os.path.join(config.MODEL_DIR, f"champion_archive_{timestamp}.pkl")
        self.champion_model.save(archive_path)
        
        # 2. Promote challenger
        self.champion_model = self.challenger_model
        self.champion_model.save(config.CHAMPION_MODEL_PATH)
        
        # 3. Create a new, untrained challenger
        self.challenger_model = AnomalyModel()
        self.challenger_model.save(config.CHALLENGER_MODEL_PATH)
        
        # 4. Update performance logs
        self.performance_log['champion'] = self.performance_log['challenger']
        self.performance_log['challenger'] = 0.0
        self.performance_log['history'].append({
            "timestamp": timestamp,
            "event": "PROMOTION",
            "promoted_performance": self.performance_log['champion']
        })
        self._save_performance_log()
        
        gen_logger.info("Challenger promoted. New challenger created.")

    def update_performance_report(self, champion_score: float, challenger_score: float):
        """Updates the performance scores for both models."""
        self.performance_log['champion'] = champion_score
        self.performance_log['challenger'] = challenger_score
        self._save_performance_log()
        gen_logger.info(f"Performance updated: Champion={champion_score:.4f}, Challenger={challenger_score:.4f}")

    def get_best_historical_model(self) -> AnomalyModel:
        """Finds, loads, and returns the best performing archived model."""
        # This would contain logic to parse filenames, find the best
        # performing archived model, and load it.
        gen_logger.warning("Fallback to historical model not yet implemented.")
        return self.champion_model # Placeholder