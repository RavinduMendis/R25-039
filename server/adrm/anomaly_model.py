# server/adrm/anomaly_model.py

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from .logger_setup import setup_loggers

gen_logger, _ = setup_loggers()

class AnomalyModel:
    """A wrapper for the scikit-learn IsolationForest model."""

    def __init__(self, contamination=0.1):
        # contamination is the expected proportion of anomalies in the data
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.is_trained = False

    def train(self, features: np.ndarray):
        """Trains or retrains the model on a batch of feature vectors.

        Args:
            features (np.ndarray): A 2D array where each row is a feature vector
                                   from a client update.
        """
        if features.shape[0] == 0:
            gen_logger.warning("Training skipped: no features provided.")
            return

        gen_logger.info(f"Training Isolation Forest on {features.shape[0]} samples...")
        self.model.fit(features)
        self.is_trained = True
        gen_logger.info("Training complete.")

    def predict(self, features: np.ndarray) -> bool:
        """Predicts if a given feature vector is an anomaly.

        Args:
            features (np.ndarray): A 2D array with a single row representing the
                                   features of one client update.

        Returns:
            bool: True if the update is an anomaly, False otherwise.
        """
        if not self.is_trained:
            gen_logger.warning("Prediction skipped: model is not trained yet. Approving by default.")
            return False

        # predict() returns -1 for outliers (anomalies) and 1 for inliers (normal).
        prediction = self.model.predict(features)
        is_anomaly = (prediction[0] == -1)
        
        return is_anomaly

    def save(self, filepath: str):
        """Saves the trained model to a file."""
        try:
            joblib.dump(self, filepath)
            gen_logger.info(f"Model saved successfully to {filepath}")
        except Exception as e:
            gen_logger.error(f"Error saving model to {filepath}: {e}")

    @staticmethod
    def load(filepath: str) -> 'AnomalyModel':
        """Loads a model from a file."""
        try:
            model = joblib.load(filepath)
            gen_logger.info(f"Model loaded successfully from {filepath}")
            return model
        except FileNotFoundError:
            gen_logger.warning(f"Model file not found at {filepath}. Creating a new, untrained model.")
            return AnomalyModel()
        except Exception as e:
            gen_logger.error(f"Error loading model from {filepath}: {e}. Creating a new one.")
            return AnomalyModel()