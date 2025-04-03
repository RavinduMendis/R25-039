import threading
import pickle
import logging
import ssl
import socket
from global_aggregator.global_aggregator import GlobalAggregator
from global_aggregator.model_manager import train_initial_model
from attackdefense.adr import ADRMonitor

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ClientManager:
    def __init__(self, rounds=10, clients_per_round=1, test_data=None, test_labels=None):
        self.clients = {}
        self.lock = threading.Lock()
        self.global_aggregator = GlobalAggregator()
        self.rounds = rounds
        self.clients_per_round = clients_per_round
        self.model = train_initial_model()
        self.received_models = []
        self.models_received_in_round = 0
        self.adr_monitor = ADRMonitor()
        # Test dataset for evaluating model accuracy
        self.test_data = test_data
        self.test_labels = test_labels

    def start_server(self, server_socket, ssl_context):
        threading.Thread(target=self.accept_clients, args=(server_socket, ssl_context), daemon=True).start()

    def accept_clients(self, server_socket, ssl_context):
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                secure_client_socket = ssl_context.wrap_socket(client_socket, server_side=True)
                logging.info(f"[NEW] Client connected: {client_address}")
                
                # Log client connection directly in the ADRMonitor
                self.adr_monitor.log_client_connection(client_address)

                with self.lock:
                    self.clients[client_address] = secure_client_socket
                threading.Thread(target=self.handle_client, args=(secure_client_socket, client_address), daemon=True).start()
            except Exception as e:
                logging.error(f"[ERROR] Accepting client: {e}")

    def handle_client(self, secure_client_socket, client_address):
        try:
            # Send initial model to the client
            self.send_initial_model(secure_client_socket, client_address)
            
            while True:
                # Receive model update from the client
                data_length_bytes = self.receive_data(secure_client_socket, 4)
                if not data_length_bytes:
                    break

                # Determine the length of the data and receive it
                data_length = int.from_bytes(data_length_bytes, 'big')
                data = self.receive_data(secure_client_socket, data_length)
                if not data:
                    break
                
                # Unpickle the received model data
                model_data = pickle.loads(data)
                logging.info(f"[MODEL] Received {len(data)} bytes of model update from {client_address}")

                # Test accuracy on the current global model before aggregation
                self.test_model_accuracy(context="Pre-aggregation")
                
                # Send the received model data to ADRMonitor for anomaly detection
                self.adr_monitor.monitor_model_update(client_address, model_data)
                # The monitoring function already detects anomalies, no need to call detect_anomalies here.

                # Store the received model data and update the count
                with self.lock:
                    self.received_models.append(model_data)
                    self.models_received_in_round += 1

                # If all models have been received, aggregate and update
                if self.models_received_in_round == self.clients_per_round:
                    logging.info("[INFO] All models received, starting aggregation...")
                    self.aggregate_and_update_clients()

        except Exception as e:
            logging.error(f"[ERROR] Client {client_address}: {e}")
        finally:
            with self.lock:
                self.clients.pop(client_address, None)
            self.adr_monitor.log_client_disconnection(client_address)
            logging.info(f"[DISCONNECTED] {client_address} removed from active clients.")


    def aggregate_and_update_clients(self):
        """Aggregates received models and sends the updated global model to clients."""
        try:
            # Delegate aggregation to GlobalAggregator
            aggregated_weights = self.global_aggregator.aggregate_weights(self.received_models)
            if aggregated_weights:
                logging.info("[INFO] Aggregation complete, updating global model...")
                self.global_aggregator.update_model(aggregated_weights)
                
                # Test accuracy on the updated model after aggregation
                self.test_model_accuracy(context="Post-aggregation")

                # Send the updated model to all clients using GlobalAggregator
                for client_address, client_socket in self.clients.items():
                    self.global_aggregator.send_updated_model(client_socket)
                
                # Clear the received models for the next round
                self.received_models.clear()
                self.models_received_in_round = 0
                logging.info("[INFO] Completed model aggregation and update.")
        except Exception as e:
            logging.error(f"[ERROR] Aggregation or update failed: {e}")

    def test_model_accuracy(self, context=""):
        """
        Evaluates the global aggregated model on the test dataset (if provided) and logs accuracy.
        """
        if self.test_data is not None and self.test_labels is not None:
            try:
                # Evaluate using the global model in the aggregator
                loss, accuracy = self.global_aggregator.model.evaluate(self.test_data, self.test_labels, verbose=0)
                logging.info(f"[{context}] Test accuracy: {accuracy}")
                return accuracy
            except Exception as e:
                logging.error(f"[{context}] Error during model evaluation: {e}")
                return None
        else:
            logging.info(f"[{context}] Test accuracy: (test dataset not provided)")
            return None

    def send_initial_model(self, client_socket, client_address):
        try:
            serialized_weights = pickle.dumps(self.model.get_weights())
            client_socket.sendall(len(serialized_weights).to_bytes(4, 'big'))
            client_socket.sendall(serialized_weights)
            logging.info(f"[SEND] Initial model sent to {client_address}")
        except Exception as e:
            logging.error(f"[ERROR] Sending initial model to {client_address}: {e}")

    def receive_data(self, secure_client_socket, expected_length):
        data = b""
        while len(data) < expected_length:
            try:
                chunk = secure_client_socket.recv(min(4096, expected_length - len(data)))
                if not chunk:
                    return None
                data += chunk
            except Exception as e:
                logging.error(f"[ERROR] Exception receiving data: {e}")
                return None
        return data

    def send_updated_model_to_clients(self):
        with self.lock:
            for client_address, secure_client_socket in self.clients.items():
                try:
                    serialized_weights = pickle.dumps(self.global_aggregator.model.get_weights())
                    secure_client_socket.sendall(len(serialized_weights).to_bytes(4, 'big'))
                    secure_client_socket.sendall(serialized_weights)
                    logging.info(f"[SEND] Updated model sent to {client_address}")
                except Exception as e:
                    logging.error(f"[ERROR] Sending updated model to {client_address}: {e}")

