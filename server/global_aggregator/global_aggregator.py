import threading
import pickle
import time
import numpy as np
from .model import create_model  # Import the model creation function

class GlobalAggregator:
    def __init__(self):
        self.global_model = create_model()  # Initialize the global model
        self.all_weights = []  # Store the model weights received from clients
        self.lock = threading.Lock()  # Lock to ensure thread safety

    def aggregate_weights(self, weights_list):
        """Perform Federated Averaging of model weights."""
        print(f"🔄 Aggregating {len(weights_list)} models...")
        # Perform federated averaging by averaging the weights of each layer across all models
        return [np.mean(np.array(layer), axis=0) for layer in zip(*weights_list)]

    def update_model(self, all_weights):
        """Update the global model with aggregated weights."""
        if all_weights:
            print(f"🔄 Aggregating model weights...")
            new_weights = self.aggregate_weights(all_weights)
            self.global_model.set_weights(new_weights)
            print(f"✅ Global model updated.")
        self.all_weights.clear()

    def send_updated_model(self, client_manager):
        """Send the updated global model to all connected clients."""
        serialized_weights = pickle.dumps(self.global_model.get_weights())
        print(f"📤 Sending updated model to clients...")
        for client_socket, _ in client_manager.clients:
            try:
                client_socket.sendall(len(serialized_weights).to_bytes(4, byteorder='big'))
                client_socket.sendall(serialized_weights)
                print(f"✅ Sent updated model to client.")
            except Exception as e:
                print(f"⚠️ Error sending model: {e}")

    def run(self, client_manager):
        """Continuously process updates and send the new model to clients."""
        while True:
            # Check if new weights are available from clients
            while not client_manager.model_queue.empty():
                client_address, weights = client_manager.model_queue.get()
                print(f"📥 Received new weights from {client_address}")
                with self.lock:
                    self.all_weights.append(weights)

            # If new weights were aggregated, send them to clients
            if self.all_weights:
                self.update_model(self.all_weights)
                self.send_updated_model(client_manager)

            time.sleep(1)  # Avoid tight loops, to let threads work more efficiently
