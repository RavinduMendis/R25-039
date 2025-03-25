import threading
import pickle
import logging
import queue
import socket
import ssl
import random
from global_aggregator.global_aggregator import GlobalAggregator
from global_aggregator.model_manager import train_initial_model

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.model_queue = queue.Queue()
        self.lock = threading.Lock()
        self.global_aggregator = GlobalAggregator()
        self.rounds = 3
        self.current_round = 0
        self.model = train_initial_model()
        self.server_socket = None
        self.clients_per_round = 3  # Adjust the number of clients per round

    def start_server(self, server_socket, ssl_context):
        self.server_socket = server_socket
        threading.Thread(target=self.accept_clients, args=(server_socket, ssl_context), daemon=True).start()

    def accept_clients(self, server_socket, ssl_context):
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                logging.info(f"[NEW] Client connected: {client_address}")
                secure_client_socket = ssl_context.wrap_socket(client_socket, server_side=True)
                self.clients[client_address] = (secure_client_socket, "connected", 0, 2, 'Not Sent', 'Not Received')  # Track status
                threading.Thread(target=self.handle_client, args=(secure_client_socket, client_address), daemon=True).start()
            except Exception as e:
                logging.error(f"[ERROR] Accepting client: {e}")

    def handle_client(self, secure_client_socket, client_address):
        try:
            self.send_initial_model(secure_client_socket, client_address)
            while True:
                data_length_bytes = self.receive_data(secure_client_socket, 4)
                if not data_length_bytes:
                    break

                data_length = int.from_bytes(data_length_bytes, 'big')
                data = self.receive_data(secure_client_socket, data_length)
                if not data:
                    break

                logging.info(f"[MODEL] Received {len(data)} bytes of model update from {client_address}")
                model_data = pickle.loads(data)

                # Track the client's rounds and stop if the limit is reached
                _, status, rounds_participated, max_rounds, _, _ = self.clients[client_address]
                if rounds_participated >= max_rounds:
                    logging.info(f"[INFO] Client {client_address} has completed its max rounds. Disconnecting.")
                    self.clients[client_address] = (secure_client_socket, "disconnected", rounds_participated, max_rounds, 'Not Sent', 'Not Received')
                    break

                self.model_queue.put((client_address, model_data))
                self.aggregate_and_update_clients()

        except Exception as e:
            logging.error(f"[ERROR] Client {client_address}: {e}")
        finally:
            with self.lock:
                self.clients.pop(client_address, None)
            logging.info(f"[DISCONNECTED] {client_address} removed from active clients.")

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
                    logging.error(f"[ERROR] Connection lost while receiving data.")
                    return None
                data += chunk
            except Exception as e:
                logging.error(f"[ERROR] Exception receiving data: {e}")
                return None

        if len(data) != expected_length:
            logging.warning(f"[WARNING] Incomplete data received.")
            return None

        return data

    def aggregate_and_update_clients(self):
        if not self.model_queue.empty():
            client_updates = []
            while not self.model_queue.empty():
                client_address, model_data = self.model_queue.get()
                logging.info(f"[AGGREGATE] Adding model update from {client_address} to aggregation queue.")
                client_updates.append(model_data)

            aggregated_weights = self.global_aggregator.aggregate_weights(client_updates)

            if aggregated_weights is not None:
                self.global_aggregator.update_model(aggregated_weights)
                logging.info("[AGGREGATE] Global model updated. Sending updated model to all clients.")
                self.send_updated_model_to_clients()
            else:
                logging.warning("[AGGREGATE] No valid model updates to aggregate.")

    def send_updated_model_to_clients(self):
        """Send updated model to clients and remove those that complete max rounds."""
        with self.lock:
            for client_address in list(self.clients.keys()):
                secure_client_socket, status, rounds_participated, max_rounds, model_sent, model_received = self.clients[client_address]

                if rounds_participated >= max_rounds:
                    logging.info(f"[INFO] Client {client_address} has reached max rounds. Removing from active clients.")
                    self.clients[client_address] = (secure_client_socket, "disconnected", rounds_participated, max_rounds, 'Not Sent', 'Not Received')
                    secure_client_socket.close()
                    continue  # Skip sending model

                try:
                    self.global_aggregator.send_updated_model(secure_client_socket)
                    # Update the number of rounds the client has participated in
                    self.clients[client_address] = (secure_client_socket, status, rounds_participated + 1, max_rounds, 'Sent', model_received)
                except Exception as e:
                    logging.error(f"[ERROR] Sending updated model to {client_address}: {e}")

    def select_clients_for_round(self):
        eligible_clients = [client_address for client_address, client_info in self.clients.items()
                            if client_info[2] < client_info[3]]  # Track rounds and max rounds

        selected_clients = random.sample(eligible_clients, min(self.clients_per_round, len(eligible_clients)))
        return selected_clients

    def run_rounds(self):
        for self.current_round in range(self.rounds):
            logging.info(f"Starting round {self.current_round + 1}/{self.rounds}")

            selected_clients = self.select_clients_for_round()

            # Stop if all clients have completed their max rounds
            if not selected_clients:
                logging.info("[STOP] All clients have completed their assigned rounds. Training is complete.")
                break

            self.send_model_to_selected_clients(selected_clients)
            self.aggregate_and_update_clients()

        logging.info("[INFO] Training rounds completed. Clients remain connected but won't receive further updates.")
