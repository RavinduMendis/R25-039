# server/model_manager.py

import os
import logging
import torch
from typing import Dict, Any, List

# Import the new, secure aggregation function and the modular model and data loader
from sam.sam import aggregate_model_weights_securely
from model_manager.common_model import SimpleCNN
from model_manager.data_loader import load_cifar10_test_data

class ModelManager:
    # CORRECTED: The constructor now accepts a configuration dictionary 'cfg'
    def __init__(self, cfg: Dict[str, Any]):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cfg = cfg # Store the configuration dictionary
        self.global_model = self.load_model()
        self.global_model_version = 0
        self.cifar10_test_loader = load_cifar10_test_data()

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
        
        # CORRECTED: Access the model_name from the dictionary using bracket notation
        model_name = self.cfg.get('model_name', 'SimpleCNN') # Use .get for safety

        if model_name == 'SimpleCNN':
            return SimpleCNN()
        else:
            self.logger.error(f"Unknown model name '{model_name}'. Falling back to SimpleCNN.")
            return SimpleCNN()

    def aggregate_client_updates_securely(self, client_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Delegates the aggregation logic to the new secure aggregation function.
        This conceptual implementation uses Shamir’s Secret Sharing and
        Threshold Cryptography.
        """
        self.logger.info(f"Starting secure aggregation for {len(client_updates)} client updates.")

        # Call the new function from sam.py
        # NOTE: The actual cryptographic operations are represented by placeholder functions
        # in the conceptual `aggregate_model_weights_securely` method.
        new_global_model_state = aggregate_model_weights_securely(client_updates, self.get_global_model_state())

        self.logger.info("Client models aggregated securely.")
        return new_global_model_state

    def evaluate_model(self) -> Dict[str, float]:
        """Evaluates the current global model on the CIFAR-10 test set."""
        self.global_model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in self.cifar10_test_loader:
                outputs = self.global_model(images)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        accuracy = 100 * correct / total
        self.logger.info(f"Global model evaluation: Accuracy = {accuracy:.2f}%." )

        return {"accuracy": accuracy, "total_samples": total}
