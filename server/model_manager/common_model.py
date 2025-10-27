# common_model.py

import torch
import torch.nn as nn
import torch.nn.functional as F

class SimpleFCN(nn.Module):
    """
    A Deeper Fully Connected Network (FCN) for WUSTL-IIoT-2021 tabular data.
    Increased depth and width to improve model capacity.
    """
    def __init__(self, input_size, num_classes):
        super(SimpleFCN, self).__init__()
        
        # Increase the size of the first hidden layer (128 -> 256)
        self.fc1 = nn.Linear(input_size, 256)
        
        # Increase the size of the second hidden layer (64 -> 128)
        self.fc2 = nn.Linear(256, 128)
        
        # --- NEW: Added a third hidden layer to increase depth ---
        self.fc3 = nn.Linear(128, 64)
        
        # Final output layer
        self.fc4 = nn.Linear(64, num_classes) 

    def forward(self, x):
        # x is a 1D feature vector for each sample
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        
        # --- NEW: Added the forward pass for the third hidden layer ---
        x = F.relu(self.fc3(x))
        
        x = self.fc4(x)
        return x
    
# Alias the new model to SimpleCNN for minimal changes in model_manager.py
SimpleCNN = SimpleFCN