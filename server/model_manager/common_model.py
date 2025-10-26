# common_model.py

import torch
import torch.nn as nn
import torch.nn.functional as F

class SimpleFCN(nn.Module):
    """A simple Fully Connected Network (FCN) for WUSTL-IIoT-2021 tabular data."""
    def __init__(self, input_size, num_classes): # Model now requires dimensions
        super(SimpleFCN, self).__init__()
        # Define layers based on input/output dimensions
        self.fc1 = nn.Linear(input_size, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, num_classes) # Final layer size is num_classes

    def forward(self, x):
        # x is a 1D feature vector for each sample
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x
    
# Alias the new model to SimpleCNN for minimal changes in model_manager.py
SimpleCNN = SimpleFCN