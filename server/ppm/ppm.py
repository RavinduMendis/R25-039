# server/ppm/ppm.py

import logging
from typing import Dict, Any

from log_manager.log_manager import ContextAdapter


class PPM:
    """
    Privacy-Preserving Mechanism (PPM) for Federated Learning.
    This class is responsible for auditing privacy protocols and guiding the
    server's aggregation strategy based on policy, not for adding noise itself.
    """

    def __init__(self, cfg: Dict[str, Any]):
        """
        Initializes the PPM with configuration parameters for both DP and HE.
        
        Args:
            cfg (Dict[str, Any]): The configuration dictionary, expected to contain
                                  'privacy' sub-keys for 'dp' and 'he'.
        """
        # Load DP parameters from config, with safe fallbacks
        dp_cfg = cfg.get("privacy", {}).get("dp", {})
        self.epsilon = dp_cfg.get("epsilon", 1.0)
        self.delta = dp_cfg.get("delta", 1e-5)
        
        # Load HE parameters from config
        he_cfg = cfg.get("privacy", {}).get("he", {})
        self.he_active = he_cfg.get("active", False)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})
        self.logger.info(
            f"PPM initialized. DP: (epsilon={self.epsilon}, delta={self.delta}). "
            f"HE active: {self.he_active}"
        )

    def check_aggregation_policy(self) -> bool:
        """
        Performs a privacy audit to determine if homomorphic aggregation should be used.
        The policy checks if Homomorphic Encryption is active.

        Returns:
            bool: True if the policy allows for homomorphic aggregation, False otherwise.
        """
        self.logger.info("Performing privacy audit for aggregation policy...")
        if self.he_active:
            self.logger.info("Audit passed: Homomorphic Encryption is active. Recommending homomorphic aggregation.")
            return True
        else:
            self.logger.warning("Audit failed: HE is not active. Not recommending homomorphic aggregation.")
            return False

    def verify_audit(self, privacy_method: str) -> bool:
        """
        Verifies that the privacy method used for aggregation is consistent with policy.
        
        Args:
            privacy_method (str): The privacy method used for the current updates ("HE", "SSS", or "Normal").
            
        Returns:
            bool: True if the method is consistent with policy, False otherwise.
        """
        self.logger.info(f"Performing consistency audit for privacy method: {privacy_method}...")
        if privacy_method == "HE":
            if self.he_active:
                self.logger.info("Audit passed: HE updates are consistent with active HE policy.")
                return True
            else:
                self.logger.error("Audit failed: HE updates received, but HE policy is not active!")
                return False
        elif privacy_method == "SSS":
            # For SSS, we currently assume it's always allowed as a baseline privacy method.
            # You could add more complex policy checks here if needed.
            self.logger.info("Audit passed: SSS updates are consistent with baseline privacy policy.")
            return True
        elif privacy_method == "Normal":
            self.logger.warning("Audit passed: 'Normal' (non-private) updates are consistent with policy. Use with caution.")
            return True
        else:
            self.logger.error(f"Audit failed: Unknown privacy method {privacy_method}!")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Returns the current status and configuration of the PPM module.
        """
        return {
            "module_name": "PPM",
            "status": "active",
            "epsilon": self.epsilon,
            "delta": self.delta,
            "he_active": self.he_active,
            "description": "Privacy-Preserving Mechanism for policy auditing.",
        }