import logging
import torch
import torch.nn as nn
from torchvision import datasets, transforms
from torch.utils.data import DataLoader, Subset
from typing import Dict, Any, List
import random
import os
import io

# Configure a logger for this module
logger = logging.getLogger(__name__)

# --- UTILITY FUNCTION ---
def deserialize_model_state(data: bytes) -> Dict[str, Any]:
    """
    Deserializes a byte stream back into a PyTorch model state dictionary.
    """
    buffer = io.BytesIO(data)
    # Load the model state and map it to the CPU to avoid CUDA errors on non-GPU clients
    return torch.load(buffer, map_location='cpu')

def serialize_model_state(state_dict: Dict[str, Any]) -> bytes:
    """
    Serializes a PyTorch model state dictionary into a byte stream.
    """
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()


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
        x = torch.flatten(x, 1) # flatten all dimensions except batch
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = self.fc3(x)
        return x

class ClientModelManager:
    """
    Manages the local model, data, and training process for a client.
    """

    def __init__(self, cfg: Dict[str, Any], client_id: str):
        self.cfg = cfg
        self.client_id = client_id
        # Use a consistent device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SimpleCNN().to(self.device)
        
        # Data preparation (assuming CIFAR-10)
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
        ])
        
        # Load the training dataset
        trainset = datasets.CIFAR10(root=self.cfg.get("data_dir", './data'), train=True, download=True, transform=transform)
        
        # Randomly select a subset of the data for this client to simulate heterogeneity
        num_samples = self.cfg.get("num_samples_per_client", 500)
        all_indices = list(range(len(trainset)))
        
        # FIX: Use hash() to get a consistent seed from the client ID string, regardless of its format.
        random.seed(hash(self.client_id)) 
        
        selected_indices = random.sample(all_indices, num_samples)
        
        self.local_train_loader = DataLoader(
            Subset(trainset, selected_indices), 
            batch_size=self.cfg.get("batch_size", 32), 
            shuffle=True
        )
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"ClientModelManager for {self.client_id} initialized.")

    def deserialize_model_state(self, data: bytes) -> Dict[str, Any]:
        """
        Deserializes a byte stream back into a PyTorch model state dictionary.
        This is now the single point of deserialization for the client.
        """
        return deserialize_model_state(data)

    def train_model(self, global_model_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trains the local model using the global model state on local data.
        
        Args:
            global_model_state (Dict[str, Any]): The global model state as a dictionary.
        
        Returns:
            Dict[str, Any]: The updated state dictionary of the local model.
        """
        self.logger.info("Starting local model training.")
        
        # Load the global model state into the local model
        self.model.load_state_dict(global_model_state)
        
        # Set up optimizer and loss function
        # FIX: The learning rate (lr) was changed from 0.01 to 0.001 to prevent divergence.
        optimizer = torch.optim.SGD(self.model.parameters(), lr=0.001, momentum=0.9)
        criterion = nn.CrossEntropyLoss()
        
        self.model.train()
        epochs = self.cfg.get("local_epochs", 1)
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