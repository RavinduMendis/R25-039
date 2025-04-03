import logging
import threading
import pickle
import numpy as np
from .model_manager import create_model
from attackdefense.adr import ADRMonitor

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class GlobalAggregator:
    def __init__(self, total_rounds=10, test_data=None, test_labels=None):
        self.model = create_model()
        if not self.model:
            logging.error("[ERROR] Model creation failed.")
        else:
            logging.info("[INFO] Model successfully created.")

        self.lock = threading.Lock()
        self.total_rounds = total_rounds
        self.current_round = 0
        self.client_updates = {}
        self.client_sockets = set()
        self.adr_monitor = ADRMonitor()
        # Optionally provide test dataset for evaluating model accuracy.
        self.test_data = test_data
        self.test_labels = test_labels

    def update_model(self, new_weights):
        if new_weights is None:
            logging.warning("[AGGREGATOR] No new weights to update the model.")
            return

        logging.info("[AGGREGATOR] Updating global model...")
        self.model.set_weights(new_weights)
        logging.info("[AGGREGATOR] Global model updated.")

    def aggregate_weights(self, weights_list):
        if not weights_list:
            logging.warning("[AGGREGATOR] No weights received for aggregation.")
            return None

        logging.info(f"[AGGREGATOR] Aggregating {len(weights_list)} models...")
        # Convert weights to numpy arrays for aggregation
        weights_list = [np.array(weights, dtype=object) for weights in weights_list]
        aggregated_weights = [np.mean(np.array(layer), axis=0) for layer in zip(*weights_list)]
        logging.info("[AGGREGATOR] Model aggregation complete.")

        return aggregated_weights

    def test_model_accuracy(self, context=""):
        """
        Evaluate the model on a provided test dataset and log the accuracy.
        If no test dataset is provided, logs a placeholder message.
        """
        if self.test_data is not None and self.test_labels is not None:
            try:
                loss, accuracy = self.model.evaluate(self.test_data, self.test_labels, verbose=0)
                logging.info(f"[{context}] Test accuracy: {accuracy}")
                return accuracy
            except Exception as e:
                logging.error(f"[{context}] Error during model evaluation: {e}")
                return None
        else:
            logging.info(f"[{context}] Test accuracy: (test dataset not provided)")
            return None

    def handle_client_update(self, client_socket, client_address):
        try:
            # Receive the model weights sent by the client
            model_weights = self.receive_client_weights(client_socket)
            if model_weights:
                # Test the accuracy before aggregation
                self.test_model_accuracy(context="Pre-aggregation")
                
                # Monitor the received model update and log anomalies
                self.adr_monitor.monitor_model_update(client_address, model_weights)
                anomalies_detected = self.adr_monitor.detect_anomalies(model_weights)

                # Log anomalies but continue aggregation
                if anomalies_detected:
                    logging.warning(f"[ADR] Anomaly detected from client {client_address}, but continuing aggregation.")
                
                # Store the model update from the client
                with self.lock:
                    self.client_updates[client_address] = model_weights

                    # Check if all clients have submitted their updates
                    if len(self.client_updates) == len(self.client_sockets):
                        logging.info("[AGGREGATOR] All clients submitted updates. Aggregating...")
                        aggregated_weights = self.aggregate_weights(list(self.client_updates.values()))
                        self.update_model(aggregated_weights)
                        
                        # Test the accuracy after aggregation
                        self.test_model_accuracy(context="Post-aggregation")
                        
                        # Send the updated model to all clients
                        for client in self.client_sockets:
                            self.send_updated_model(client)

                        # Clear the received updates and increment the round
                        self.client_updates.clear()
                        self.current_round += 1
                        logging.info(f"[AGGREGATOR] Completed round {self.current_round}.")
        except Exception as e:
            logging.error(f"[AGGREGATOR] Error handling client update: {e}")

    def send_updated_model(self, client_socket):
        try:
            with self.lock:
                updated_weights = self.model.get_weights()
                serialized_weights = pickle.dumps(updated_weights)
                # Send the updated model weights to the client
                client_socket.sendall(len(serialized_weights).to_bytes(4, byteorder="big"))
                client_socket.sendall(serialized_weights)
                logging.info(f"[AGGREGATOR] Sent updated model to client {client_socket.getpeername()}.")
        except Exception as e:
            logging.error(f"[AGGREGATOR] Error sending updated model: {e}")
    
    def receive_client_weights(self, client_socket):
        try:
            # Receive the model weights from the client (in the form of pickled data)
            data_length_bytes = client_socket.recv(4)
            data_length = int.from_bytes(data_length_bytes, 'big')
            data = b""
            while len(data) < data_length:
                data += client_socket.recv(min(4096, data_length - len(data)))
            model_weights = pickle.loads(data)
            return model_weights
        except Exception as e:
            logging.error(f"[AGGREGATOR] Error receiving client weights: {e}")
            return None
