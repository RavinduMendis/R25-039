# client_model_manager.py

import logging
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from typing import Dict, Any, List
import random
import io
import os
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
import numpy as np
import torch.nn.functional as F

# Configure a logger for this module
logger = logging.getLogger(__name__)

# --- UTILITY FUNCTIONS ---
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


# --- MODEL DEFINITION: SimpleFCN (MATCHES DEEPER SERVER MODEL) ---
class SimpleFCN(nn.Module):
    """
    A Deeper Fully Connected Network (FCN) for WUSTL-IIoT-2021 tabular data.
    Structure matches the server's updated common_model.py.
    """
    def __init__(self, input_size: int = 41, num_classes: int = 2): 
        super(SimpleFCN, self).__init__()
        
        # Define layers based on expected input/output dimensions from data_loader.py
        
        # Layer 1: Increased size from 128 to 256
        self.fc1 = nn.Linear(input_size, 256) 
        
        # Layer 2: Increased size from 64 to 128
        self.fc2 = nn.Linear(256, 128)
        
        # --- NEW: Added third hidden layer for increased depth ---
        self.fc3 = nn.Linear(128, 64)
        
        # Final output layer
        self.fc4 = nn.Linear(64, num_classes) 

    def forward(self, x):
        # x is a 1D feature vector for each sample
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        
        # --- NEW: Forward pass through the third hidden layer ---
        x = F.relu(self.fc3(x))
        
        x = self.fc4(x)
        return x
    
# --- Data Loading (Matches Server's data_loader.py logic) ---

class IIoTDataset(Dataset):
    """Custom Dataset for WUSTL-IIoT-2021 tabular data."""
    def __init__(self, features, labels):
        self.features = torch.tensor(features, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]

def load_wustl_iiot_train_data(cfg: Dict[str, Any], client_id: str):
    """
    Loads, preprocesses, and prepares a randomized subset of WUSTL-IIoT-2021 
    data for a specific client.
    """
    file_path = cfg.get("data_file_path", './data/WUSTL_IIoT_2021.csv')
    
    if not os.path.exists(file_path):
        logger.error(f"Dataset file not found at: {file_path}. Cannot load client data.")
        return None, 41, 2 

    df = pd.read_csv(file_path)
    
    # Preprocessing (must match the server's data_loader.py)
    columns_to_drop = ['StartTime', 'LastTime', 'SrcAddr', 'DstAddr', 'sIpId', 'dIpId']
    df = df.drop(columns=columns_to_drop, errors='ignore')
    
    label_column = df.columns[-1] 
    X = df.drop(columns=[label_column])
    y = df[label_column]
    
    numeric_cols = X.select_dtypes(include=np.number).columns
    X_numeric = X[numeric_cols]
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_numeric)
    
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)
    
    # --- Client-Specific Data Partitioning ---
    num_samples = cfg.get("num_samples_per_client", 500)
    
    # Use the entire processed dataset for sampling
    full_dataset = IIoTDataset(X_scaled, y_encoded)
    all_indices = list(range(len(full_dataset)))
    
    # Use hash() for a consistent, client-specific seed
    random.seed(hash(client_id)) 
    
    # Sample a subset of indices for this client
    selected_indices = random.sample(all_indices, min(num_samples, len(full_dataset)))
    
    # Create the client's subset
    client_subset = torch.utils.data.Subset(full_dataset, selected_indices)
    
    num_features = X_scaled.shape[1] 
    num_classes = len(np.unique(y_encoded))
    
    logger.info(f"Client {client_id} loaded {len(client_subset)} samples. Features={num_features}, Classes={num_classes}")
    
    return DataLoader(client_subset, batch_size=cfg.get("batch_size", 32), shuffle=True), num_features, num_classes


class ClientModelManager:
    """
    Manages the local model, data, and training process for a client 
    using the WUSTL-IIoT SimpleFCN architecture.
    """

    def __init__(self, cfg: Dict[str, Any], client_id: str):
        self.cfg = cfg
        self.client_id = client_id
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Load the client's data
        self.local_train_loader, num_features, num_classes = load_wustl_iiot_train_data(cfg, client_id)
        
        # Initialize the FCN model with determined dimensions
        self.model = SimpleFCN(input_size=num_features, num_classes=num_classes).to(self.device)
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"ClientModelManager for {self.client_id} initialized with DEEPER SimpleFCN.")

    def deserialize_model_state(self, data: bytes) -> Dict[str, Any]:
        """
        Deserializes a byte stream back into a PyTorch model state dictionary.
        """
        return deserialize_model_state(data)

    def train_model(self, global_model_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trains the local model using the global model state on local data.
        """
        if self.local_train_loader is None:
            self.logger.error("Training skipped: Data loader failed to initialize.")
            return self.model.state_dict()
            
        self.logger.info("Starting local model training on WUSTL-IIoT data.")
        
        # Load the server's state dict into the local model
        self.model.load_state_dict(global_model_state)
        
        # Setup for FCN/Tabular Data Training
        optimizer = torch.optim.SGD(self.model.parameters(), lr=self.cfg.get("client_lr", 0.001), momentum=0.9)
        criterion = nn.CrossEntropyLoss()
        
        self.model.train()
        epochs = self.cfg.get("local_epochs", 1)
        last_loss = 0.0
        
        for epoch in range(epochs):
            for images, labels in self.local_train_loader:
                # The input data is now a 1D feature vector per sample
                images, labels = images.to(self.device), labels.to(self.device)
                
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
                last_loss = loss.item()
        
        self.logger.info(f"Local model training finished after {epochs} epochs. Final loss: {last_loss:.4f}")
        return self.model.state_dict()

    def get_model_state(self) -> Dict[str, Any]:
        """
        Returns the current state dictionary of the local model.
        """
        return self.model.state_dict()