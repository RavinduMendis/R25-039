# dp.py

import torch
import numpy as np
import logging
from typing import Dict, Any

class DifferentialPrivacy:
    """
    Applies local differential privacy to model updates by adding Gaussian noise.
    """
    def __init__(self, epsilon: float, clipping_norm: float = 1.0):
        if epsilon <= 0 or clipping_norm <= 0:
            raise ValueError("Epsilon and clipping norm must be positive values.")
            
        self.epsilon = epsilon
        self.clipping_norm = clipping_norm
        self.std_dev = self.clipping_norm / self.epsilon
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"DifferentialPrivacy initialized with epsilon={self.epsilon}, clipping_norm={self.clipping_norm}, std_dev={self.std_dev:.4f}")

    def add_noise(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clips the norm of the entire model update and then adds Gaussian noise
        to each parameter.
        """
        self.logger.info("Applying differential privacy: Clipping and adding Gaussian noise.")
        
        # 1. Flatten all parameters into a single vector to calculate the L2 norm
        flat_params = torch.cat([p.flatten() for p in state_dict.values()])
        total_norm = torch.linalg.norm(flat_params)
        
        # 2. Calculate the clipping factor to scale the update if its norm exceeds the threshold
        clip_factor = min(1.0, self.clipping_norm / (total_norm + 1e-6))
        
        self.logger.info(f"Update norm: {total_norm:.4f}, Clipping factor: {clip_factor:.4f}")

        noisy_state_dict = {}
        for key, param in state_dict.items():
            # 3. Apply the clipping factor to each parameter
            clipped_param = param * clip_factor
            
            # 4. Add Gaussian noise scaled to the clipping norm
            noise = torch.randn_like(clipped_param) * self.std_dev
            noisy_state_dict[key] = clipped_param + noise
            
        self.logger.info("Noise and clipping successfully applied to model update.")
        return noisy_state_dict