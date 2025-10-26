# data_loader.py

import torch
from torch.utils.data import Dataset, DataLoader
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

# --- New Custom Dataset Class for Tabular Data ---
class IIoTDataset(Dataset):
    """Custom Dataset for WUSTL-IIoT-2021 tabular data."""
    def __init__(self, features, labels):
        # Convert preprocessed numpy arrays to PyTorch Tensors
        self.features = torch.tensor(features, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]

def load_wustl_iiot_test_data(file_path: str = './data/WUSTL_IIoT_2021.csv'):
    """
    Loads, preprocesses, and prepares the WUSTL-IIoT-2021 test dataset.
    
    Returns:
        tuple: (DataLoader, num_features, num_classes)
    """
    if not os.path.exists(file_path):
        logger.warning(f"Dataset file not found at: {file_path}. Please download the dataset and place it in the correct location.")
        return None, 41, 2 # Return None for loader on failure

    logger.info(f"Loading and preprocessing data from {file_path}...")
    df = pd.read_csv(file_path)
    
    # --- Preprocessing Step 1: Drop non-generalizable columns ---
    columns_to_drop = ['StartTime', 'LastTime', 'SrcAddr', 'DstAddr', 'sIpId', 'dIpId']
    df = df.drop(columns=columns_to_drop, errors='ignore')
    
    # --- Feature and Label Separation ---
    # Assuming the label column is the last one
    label_column = df.columns[-1] 
    X = df.drop(columns=[label_column])
    y = df[label_column]
    
    # --- FIX: Handle non-numeric feature columns ---
    # Identify all non-numeric columns remaining in the features (X)
    numeric_cols = X.select_dtypes(include=np.number).columns
    non_numeric_cols = X.select_dtypes(include=['object']).columns

    if len(non_numeric_cols) > 0:
        logger.warning(f"Dropping non-numeric feature columns: {non_numeric_cols.tolist()} for simplicity.")
        # For a full solution, these should be one-hot encoded.
        # For this fix, we assume they are either irrelevant or too complex to encode here.
        X_numeric = X[numeric_cols]
    else:
        X_numeric = X
    
    # --- Feature Scaling ---
    # Apply scaling only to the numeric features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_numeric)
    
    # --- Label Encoding (for the target variable y) ---
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)
    
    # --- Create Dataset and DataLoader ---
    test_dataset = IIoTDataset(X_scaled, y_encoded)
    
    num_features = X_scaled.shape[1] 
    num_classes = len(np.unique(y_encoded))
    
    logger.info(f"WUSTL-IIoT Dataset loaded: Features={num_features}, Classes={num_classes}")
    
    return DataLoader(test_dataset, batch_size=256, shuffle=False), num_features, num_classes

# Alias the new function name for compatibility with model_manager.py
load_cifar10_test_data = load_wustl_iiot_test_data