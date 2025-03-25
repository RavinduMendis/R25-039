import threading
import pickle
import logging
import numpy as np
import socket
from .model_manager import create_model  # Assuming this function creates the model

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class GlobalAggregator:
    def __init__(self, total_rounds=10):
        self.global_model = create_model()  # Initialize the global model
        self.lock = threading.Lock()
        self.total_rounds = total_rounds
        self.current_round = 0

    def aggregate_weights(self, weights_list):
        """Aggregate model weights from clients."""
        if not weights_list:
            logging.warning("[AGGREGATOR] No weights received for aggregation.")
            return None

        logging.info(f"[AGGREGATOR] Aggregating {len(weights_list)} models...")

        # Convert all weights into NumPy arrays
        weights_list = [np.array(weights, dtype=object) for weights in weights_list]

        # Perform element-wise averaging
        aggregated_weights = [np.mean(np.array(layer), axis=0) for layer in zip(*weights_list)]

        logging.info("[AGGREGATOR] Model aggregation complete.")
        return aggregated_weights

    def update_model(self, new_weights):
        """Update the global model with the new aggregated weights."""
        if new_weights is None:
            logging.warning("[AGGREGATOR] No new weights to update the model.")
            return

        with self.lock:
            logging.info("[AGGREGATOR] Updating global model...")
            self.global_model.set_weights(new_weights)
            logging.info("[AGGREGATOR] Global model updated.")

    def send_updated_model(self, client_socket):
        """Send the updated global model to the client."""
        try:
            with self.lock:
                updated_weights = self.global_model.get_weights()
                serialized_weights = pickle.dumps(updated_weights)

                client_socket.sendall(len(serialized_weights).to_bytes(4, byteorder="big"))
                client_socket.sendall(serialized_weights)

                logging.info(f"[AGGREGATOR] Sent updated model weights ({len(serialized_weights)} bytes) to client.")
        except Exception as e:
            logging.error(f"[AGGREGATOR] Error sending updated model: {e}")

    def handle_client_update(self, client_address, model_weights, client_socket):
        """Handle the model update from a client."""
        try:
            with self.lock:
                # Aggregate the new model update with the global model
                current_weights = self.global_model.get_weights()
                if not current_weights:
                    aggregated_weights = model_weights  # First round, just use client weights
                else:
                    aggregated_weights = self.aggregate_weights([model_weights, current_weights])

                # Update the global model
                self.update_model(aggregated_weights)

                # Send updated model back to client
                self.send_updated_model(client_socket)

        except Exception as e:
            logging.error(f"[AGGREGATOR] Error handling client update: {e}")

    def start_round(self, client_sockets):
        """Start a round of federated learning."""
        if self.current_round < self.total_rounds:
            logging.info(f"Starting round {self.current_round + 1} of {self.total_rounds}.")

            weights_list = []
            for client_socket in client_sockets:
                try:
                    model_weights = self.receive_client_weights(client_socket)
                    if model_weights:
                        weights_list.append(model_weights)
                except Exception as e:
                    logging.error(f"[AGGREGATOR] Error receiving model from client: {e}")

            if weights_list:
                aggregated_weights = self.aggregate_weights(weights_list)
                if aggregated_weights:
                    self.update_model(aggregated_weights)

            # Send updated model to all clients
            for client_socket in client_sockets:
                self.send_updated_model(client_socket)

            self.current_round += 1
        else:
            logging.info("All rounds completed. Aggregation finished.")

    def receive_client_weights(self, client_socket):
        """Receive model weights from a client."""
        try:
            data_length_bytes = client_socket.recv(4)
            if not data_length_bytes:
                logging.error("[ERROR] Connection lost while receiving data length.")
                return None

            data_length = int.from_bytes(data_length_bytes, 'big')
            data = b""
            while len(data) < data_length:
                chunk = client_socket.recv(min(4096, data_length - len(data)))
                if not chunk:
                    logging.error("[ERROR] Connection lost while receiving data.")
                    return None
                data += chunk

            model_weights = pickle.loads(data)
            return model_weights

        except Exception as e:
            logging.error(f"[AGGREGATOR] Error receiving client weights: {e}")
            return None
