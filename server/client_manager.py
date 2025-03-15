import threading
import pickle
import socket
import ssl
import queue
import time
import curses
from global_aggregator.global_aggregator import GlobalAggregator  # Import GlobalAggregator

class ClientManager:
    def __init__(self):
        self.clients = []  # List of connected clients (sockets and their addresses)
        self.model_queue = queue.Queue()  # Queue for storing received models
        self.lock = threading.Lock()  # Lock for thread safety
        self.global_aggregator = GlobalAggregator()  # Initialize GlobalAggregator

    def terminal_ui(self, stdscr):
        """Terminal UI to monitor connected clients and received models."""
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(1)  # Non-blocking input

        prev_clients = set()
        prev_model_count = 0

        try:
            while True:
                stdscr.clear()
                stdscr.addstr(0, 0, "🟢 Client Manager Running...\n")
                stdscr.addstr(1, 0, "Waiting for clients...\n")

                with self.lock:
                    current_clients = {f"{ip}:{port}" for _, (ip, port) in self.clients if isinstance((ip, port), tuple)}

                if current_clients != prev_clients:
                    prev_clients = current_clients
                    stdscr.addstr(2, 0, "Connected Clients:\n")
                    for idx, client in enumerate(current_clients, 3):
                        stdscr.addstr(idx, 0, f"- {client}")

                # Show received model count
                current_model_count = self.model_queue.qsize()
                if current_model_count != prev_model_count:
                    prev_model_count = current_model_count
                    stdscr.addstr(5, 0, f"\n📥 Received {current_model_count} models.")

                stdscr.refresh()
                time.sleep(2)

        except Exception as e:
            print(f"⚠️ Terminal UI error: {e}")

        finally:
            curses.endwin()  # Properly exit curses UI mode

    def accept_clients(self, server_socket, ssl_context):
        """Accept incoming client connections from the server."""
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                print(f"🔗 Client connected: {client_address}")

                # Wrap the socket with SSL encryption
                secure_client_socket = ssl_context.wrap_socket(client_socket, server_side=True)

                with self.lock:
                    self.clients.append((secure_client_socket, client_address))

                # Send the global model to the newly connected client
                threading.Thread(target=self.send_initial_model, args=(secure_client_socket,), daemon=True).start()

                # Start a new thread to handle the client communication
                threading.Thread(target=self.handle_client, args=(secure_client_socket, client_address), daemon=True).start()

            except Exception as e:
                print(f"⚠️ Error accepting client: {e}")

    def send_initial_model(self, client_socket):
        """Send the current global model to the client when they connect."""
        try:
            serialized_weights = pickle.dumps(self.global_aggregator.global_model.get_weights())
            client_socket.sendall(len(serialized_weights).to_bytes(4, byteorder='big'))
            client_socket.sendall(serialized_weights)
            print("✅ Sent initial model to client.")
        except Exception as e:
            print(f"⚠️ Error sending initial model: {e}")

    def handle_client(self, client_socket, client_address):
        """Receive model updates from clients and aggregate them."""
        try:
            while True:
                data_length_bytes = client_socket.recv(4)
                if not data_length_bytes:
                    break  # Connection closed

                data_length = int.from_bytes(data_length_bytes, byteorder='big')
                data = b''
                while len(data) < data_length:
                    chunk = client_socket.recv(4096)
                    if not chunk:
                        break
                    data += chunk

                if len(data) == data_length:
                    try:
                        model_data = pickle.loads(data)
                        print(f"📥 Received model from {client_address}")

                        # Add received model to the queue for aggregation
                        self.model_queue.put((client_address, model_data))

                        # Acknowledge the receipt of the model
                        client_socket.send(b"Model received and aggregated.")
                    except Exception as e:
                        print(f"⚠️ Error processing model from {client_address}: {e}")
                        client_socket.send(b"Error processing model.")
        except Exception as e:
            print(f"⚠️ Error with client {client_address}: {e}")
        finally:
            with self.lock:
                self.clients = [c for c in self.clients if c[1] != client_address]
            client_socket.close()
            print(f"❌ Client {client_address} disconnected.")
