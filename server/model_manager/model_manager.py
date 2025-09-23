import os
import logging
import torch
import torch.nn as nn
from typing import Dict, Any, List, Optional
import datetime
import json

# Import the new, secure aggregation function and the modular model and data loader
from sam.sam import aggregate_model_weights_securely
from model_manager.common_model import SimpleCNN
from model_manager.data_loader import load_cifar10_test_data

class ModelManager:
    """
    Manages the global model for the federated learning process.
    This includes loading the initial model, updating it with aggregated client weights,
    and evaluating its performance on a test dataset.
    """
    def __init__(self, cfg: Dict[str, Any]):
        """
        Initializes the ModelManager with a configuration dictionary.
        
        Args:
            cfg (Dict[str, Any]): The configuration dictionary.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cfg = cfg # Store the configuration dictionary
        self.global_model = self.load_model()
        self.global_model_version = 0
        self.cifar10_test_loader = load_cifar10_test_data()

        # New attributes for model convergence checking
        self.best_accuracy = 0.0
        self.rounds_since_last_improvement = 0
        self.convergence_window = self.cfg.get("model_convergence_window", 5)
        self.model_save_path = self.cfg.get("model_save_path", "saved_models")

        # Create the model save directory if it doesn't exist
        os.makedirs(self.model_save_path, exist_ok=True)
        
        # --- NEW: Initialize metrics history and load from file ---
        self.metrics_history: List[Dict[str, Any]] = []
        self.metrics_log_path = self.cfg.get("metrics_log_path", "./database/logs/model_metrics_history.json")
        self._load_metrics_history() # Load any existing history on startup

        # FIX: Add attributes for tracking first and last aggregation details
        self.first_aggregated_model_details: Optional[Dict[str, Any]] = None
        self.last_aggregated_model_details: Optional[Dict[str, Any]] = None

    # --- NEW: Methods to save and load metrics history ---
    def _load_metrics_history(self):
        """Loads metrics history from a JSON file if it exists."""
        if os.path.exists(self.metrics_log_path):
            try:
                with open(self.metrics_log_path, 'r') as f:
                    self.metrics_history = json.load(f)
                self.logger.info(f"Successfully loaded {len(self.metrics_history)} metric records from {self.metrics_log_path}")
            except (IOError, json.JSONDecodeError) as e:
                self.logger.error(f"Failed to load metrics history from {self.metrics_log_path}: {e}. Starting with an empty history.")
                self.metrics_history = []
        else:
            self.logger.info("No existing metrics history file found. Starting fresh.")

    def _save_metrics_history(self):
        """Saves the current metrics history to a JSON file."""
        try:
            # Ensure the directory exists before writing
            log_dir = os.path.dirname(self.metrics_log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            with open(self.metrics_log_path, 'w') as f:
                json.dump(self.metrics_history, f, indent=4)
            self.logger.debug(f"Metrics history successfully saved to {self.metrics_log_path}")
        except IOError as e:
            self.logger.error(f"Failed to save metrics history to {self.metrics_log_path}: {e}")
    # --- END NEW METHODS ---

    def get_global_model_state(self) -> Dict[str, Any]:
        """Returns the current state dictionary of the global model."""
        return self.global_model.state_dict()

    def update_global_model(self, new_state: Dict[str, Any]):
        """
        Updates the global model with a new state dictionary.
        """
        self.global_model.load_state_dict(new_state)
        self.global_model_version += 1
        self.logger.info(f"Global model updated to version {self.global_model_version}.")

    def load_model(self):
        """
        Loads the appropriate model based on the configuration.
        """
        self.logger.info("Loading initial global model.")
        
        model_name = self.cfg.get('model_name', 'SimpleCNN')

        if model_name == 'SimpleCNN':
            return SimpleCNN()
        else:
            self.logger.error(f"Unknown model name '{model_name}'. Falling back to SimpleCNN.")
            return SimpleCNN()

    def evaluate_model(self) -> Dict[str, float]:
        """Evaluates the current global model on the CIFAR-10 test set and returns metrics."""
        self.global_model.eval()
        correct = 0
        total = 0
        loss = 0.0
        criterion = nn.CrossEntropyLoss()
        
        with torch.no_grad():
            for images, labels in self.cifar10_test_loader:
                outputs = self.global_model(images)
                loss += criterion(outputs, labels).item()
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        accuracy = 100 * correct / total
        avg_loss = loss / len(self.cifar10_test_loader)
        self.logger.info(f"Global model evaluation: Accuracy = {accuracy:.2f}%, Loss = {avg_loss:.4f}.")
        
        # Check for and save the best model
        if accuracy > self.best_accuracy:
            self.best_accuracy = accuracy
            self.rounds_since_last_improvement = 0
            self.save_model_state(f"best_model_v{self.global_model_version}_acc{accuracy:.2f}.pt")
            self.logger.info(f"New best model found! Accuracy: {self.best_accuracy:.2f}%.")
        else:
            self.rounds_since_last_improvement += 1
            self.logger.info(f"No accuracy improvement. Rounds since last improvement: {self.rounds_since_last_improvement}.")


        return {"accuracy": accuracy, "loss": avg_loss}
    
    def has_model_converged(self) -> bool:
        """
        Checks if the model has converged by monitoring accuracy on the test set.
        
        Returns:
            bool: True if the model has not improved for 'convergence_window' rounds,
                  False otherwise.
        """
        return self.rounds_since_last_improvement >= self.convergence_window

    def save_model_state(self, filename: str):
        """
        Saves the current state dictionary of the global model to a file.
        """
        file_path = os.path.join(self.model_save_path, filename)
        try:
            torch.save(self.global_model.state_dict(), file_path)
            self.logger.info(f"Model state saved to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to save model state: {e}")

    def record_aggregation_event(self, round_number: int, metrics: Dict[str, Any]):
        """Records the details of a model aggregation event."""
        details = {
            "version": self.global_model_version,
            "round": round_number,
            "timestamp": datetime.datetime.now().isoformat(),
            "metrics": metrics
        }
        if self.global_model_version == 1:
            self.first_aggregated_model_details = details
        self.last_aggregated_model_details = details
        self.logger.info(f"Aggregation event for version {self.global_model_version} recorded.")

    def get_aggregation_summary(self) -> Dict[str, Any]:
        """Returns details of the first and most recent model aggregations."""
        return {
            "first_aggregation": self.first_aggregated_model_details,
            "last_aggregation": self.last_aggregated_model_details
        }
        
    def get_metrics_history(self) -> List[Dict[str, Any]]:
        """Returns the stored model metrics history."""
        return self.metrics_history

    def add_metrics_to_history(self, round_number: int, metrics: Dict[str, Any], aggregation_method: str):
        """Adds new metrics to the history and saves it to a file."""
        metrics_entry = {
            "round": round_number,
            "timestamp": datetime.datetime.now().isoformat(),
            "aggregation_method": aggregation_method,
            "metrics": metrics
        }
        self.metrics_history.append(metrics_entry)
        self.logger.info(f"Added metrics for round {round_number} to history.")
        self._save_metrics_history()