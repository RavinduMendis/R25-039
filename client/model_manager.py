# client/client_model_manager.py

import logging
import torch
import torch.nn as nn
from torchvision import datasets, transforms
from torch.utils.data import DataLoader, Subset
from typing import Dict, Any, List
import random
import os

# Configure a logger for this module
logger = logging.getLogger(__name__)

# --- MODEL DEFINITION ---
# A simple Convolutional Neural Network for CIFAR-10, identical to the one on the server
class SimpleCNN(nn.Module):
    """
    A simple Convolutional Neural Network for CIFAR-10.
    This architecture must be identical to the one on the server.
    """
    def __init__(self):
        super(SimpleCNN, self).__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def forward(self, x):
        x = self.pool(torch.relu(self.conv1(x)))
        x = self.pool(torch.relu(self.conv2(x)))
        x = x.view(-1, 16 * 5 * 5)
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = self.fc3(x)
        return x

# --- CLIENT MODEL MANAGER ---
class ClientModelManager:
    """
    Manages the local model and its training process on the client side.
    """
    def __init__(self, client_id: str, local_data_size: int = 500):
        """
        Initializes the model manager with a client ID and a size for the local dataset.
        
        Args:
            client_id (str): The unique ID of the client.
            local_data_size (int): The number of samples to use for the local training dataset.
        """
        self.client_id = client_id
        self.logger = logging.getLogger(self.__class__.__name__)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SimpleCNN().to(self.device)
        self.local_train_loader = self._get_local_data_loader(local_data_size)
        self.logger.info(f"ClientModelManager initialized on device: {self.device}")

    def _get_local_data_loader(self, local_data_size: int) -> DataLoader:
        """
        Loads a local dataset (a subset of CIFAR-10) for training.
        This simulates a client having a small, local dataset.
        """
        # Define the transformations for the dataset
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
        ])

        # Download the full CIFAR-10 dataset
        try:
            full_dataset = datasets.CIFAR10(root='./data', train=True, download=True, transform=transform)
        except Exception as e:
            self.logger.error(f"Failed to download CIFAR-10 dataset: {e}. Aborting data loading.")
            return None

        # Create a random subset to simulate a client's local data
        total_data_size = len(full_dataset)
        if local_data_size > total_data_size:
            local_data_size = total_data_size
            self.logger.warning(f"Requested local data size is larger than the full dataset. Using full dataset size: {local_data_size}")

        indices = random.sample(range(total_data_size), local_data_size)
        local_dataset = Subset(full_dataset, indices)
        self.logger.info(f"Loaded a local dataset of size {len(local_dataset)} for client {self.client_id}.")
        return DataLoader(local_dataset, batch_size=16, shuffle=True)

    def train_model(self, global_model_state: Dict[str, Any], epochs: int = 1) -> Dict[str, Any]:
        """
        Trains the provided global model on the client's local data.
        Returns the updated state dictionary.
        
        Args:
            global_model_state (Dict[str, Any]): The state dictionary of the global model.
            epochs (int): The number of local epochs to train for.
            
        Returns:
            Dict[str, Any]: The state dictionary of the updated local model.
        """
        if self.local_train_loader is None:
            self.logger.error("Local data loader is not available. Cannot train model.")
            return self.model.state_dict() # Return the current, untrianed model state

        self.logger.info("Starting local model training.")
        
        # Load the global model state into the local model
        self.model.load_state_dict(global_model_state)
        
        # Set up optimizer and loss function
        optimizer = torch.optim.SGD(self.model.parameters(), lr=0.01, momentum=0.9)
        criterion = nn.CrossEntropyLoss()
        
        self.model.train()
        for epoch in range(epochs):
            for i, (images, labels) in enumerate(self.local_train_loader):
                images, labels = images.to(self.device), labels.to(self.device)
                
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
        
        self.logger.info(f"Local model training finished after {epochs} epochs. Final loss: {loss.item():.4f}")
        return self.model.state_dict()

    def get_model_state(self) -> Dict[str, Any]:
        """
        Returns the current state dictionary of the local model.
        
        Returns:
            Dict[str, Any]: The state dictionary of the local model.
        """
        return self.model.state_dict()
