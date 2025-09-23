import logging
import torch
from typing import Dict, Any, List, Optional, Tuple

from log_manager.log_manager import ContextAdapter

logger = logging.getLogger(__name__)
logger = ContextAdapter(logger, {"component": "SAM"})

# This global state is used by the FedAdam optimizer. In a production system,
# this would be managed more robustly within a class instance.
fedadam_state = {
    "m": None, "v": None, "beta1": 0.9, "beta2": 0.99,
    "epsilon": 1e-8, "server_learning_rate": 0.01
}

# ----------------------------
# Aggregation Strategies
# ----------------------------

def fedavg(client_updates: List[Dict[str, Any]], global_model_state: Dict[str, Any]) -> Dict[str, Any]:
    """Standard Federated Averaging (equal weights)."""
    if not client_updates:
        return global_model_state
    
    aggregated_update = {k: torch.zeros_like(v) for k, v in global_model_state.items()}
    
    for update in client_updates:
        for key in aggregated_update:
            if key in update:
                aggregated_update[key] += update[key]
                
    num_clients = len(client_updates)
    for key in aggregated_update:
        aggregated_update[key] /= num_clients
        
    new_global_state = {k: global_model_state[k] + aggregated_update[k] for k in global_model_state}
    logger.info("Performed FedAvg aggregation.")
    return new_global_state

def fedadam(
    avg_update: Dict[str, Any],
    global_model_state: Dict[str, Any],
    state: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Applies a server-side Adam optimization step to the global model."""
    if state["m"] is None:
        state["m"] = {k: torch.zeros_like(v) for k, v in avg_update.items()}
        state["v"] = {k: torch.zeros_like(v) for k, v in avg_update.items()}
        
    new_global_state = {}
    for key in global_model_state:
        state["m"][key] = state["beta1"] * state["m"][key] + (1 - state["beta1"]) * avg_update[key]
        state["v"][key] = state["beta2"] * state["v"][key] + (1 - state["beta2"]) * (avg_update[key] ** 2)
        
        m_hat = state["m"][key] / (1 - state["beta1"])
        v_hat = state["v"][key] / (1 - state["beta2"])
        
        update_value = state["server_learning_rate"] * m_hat / (torch.sqrt(v_hat) + state["epsilon"])
        new_global_state[key] = global_model_state[key] + update_value
        
    logger.info("Applied FedAdam optimization step.")
    return new_global_state, state

def homomorphic_aggregation(client_updates: List[Dict[str, Any]], global_model_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles aggregation of HE-decrypted updates by applying a stabilizing optimizer.
    """
    logger.info("Performing homomorphic aggregation using FedAdam optimizer.")
    if not client_updates:
        return global_model_state
    
    # First, compute the simple average of the decrypted updates.
    avg_update = {k: torch.zeros_like(v) for k, v in global_model_state.items()}
    for update in client_updates:
        for key in avg_update:
            if key in update:
                avg_update[key] += update[key]
    for key in avg_update:
        avg_update[key] /= len(client_updates)
            
    # Apply the FedAdam optimizer to the averaged update.
    global fedadam_state
    new_model, new_state = fedadam(avg_update, global_model_state, fedadam_state)
    fedadam_state = new_state
    return new_model

# ----------------------------
# Secure Aggregation Coordinator
# ----------------------------

def aggregate_model_weights_securely(
    client_updates: List[Dict[str, Any]],
    global_model_state: Dict[str, Any],
    method: str = "fedadam",
    client_sizes: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Coordinates the secure aggregation process based on the commanded method from the Orchestrator.
    """
    if not client_updates:
        logger.warning("No client updates for aggregation. Returning global model state.")
        return global_model_state

    logger.info(f"SAM dispatching to aggregation method: {method}")

    if method == "fedavg":
        return fedavg(client_updates, global_model_state)
        
    elif method == "fedadam":
        # Calculate the simple average of the updates first
        avg_update = {k: torch.zeros_like(v) for k, v in global_model_state.items()}
        for update in client_updates:
            for key in avg_update:
                if key in update:
                    avg_update[key] += update[key]
        for key in avg_update:
            avg_update[key] /= len(client_updates)
            
        # Pass the averaged update to the FedAdam optimizer
        global fedadam_state
        new_model, new_state = fedadam(avg_update, global_model_state, fedadam_state)
        fedadam_state = new_state
        return new_model

    elif method == "homomorphic_aggregation":
        return homomorphic_aggregation(client_updates, global_model_state)
        
    else:
        raise ValueError(f"Unknown aggregation method commanded: {method}")