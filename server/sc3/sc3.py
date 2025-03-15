# sc3.py
import socket
import threading
import pickle
import time
from server import ServerConfig  # Import the server configuration

class ServerControl:
    def __init__(self, host='127.0.0.1', port=5001):
        self.host = host
        self.port = port
        self.clients = {}  # Dictionary to hold client details {client_id: (client_socket, client_address)}
        self.server_socket = None
        self.lock = threading.Lock()  # To prevent race conditions on the clients list

    def start_server(self):
        # Create TCP/IP socket for the server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)  # Allow 5 clients to connect at once
        print(f"Server started on {self.host}:{self.port}, waiting for clients...")

        # Start the thread to handle incoming connections
        threading.Thread(target=self.accept_clients).start()

    def accept_clients(self):
        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"Client connected from {client_address}")

            with self.lock:
                client_id = len(self.clients) + 1
                self.clients[client_id] = (client_socket, client_address)

            # Start a new thread to handle the client
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address, client_id))
            client_thread.start()

    def handle_client(self, client_socket, client_address, client_id):
        try:
            while True:
                # Receive data from the client (raw bytes, not decoded text)
                data = client_socket.recv(1024)
                if not data:
                    break  # Client disconnected

                try:
                    # Try to deserialize the received data (expecting a model update)
                    model_data = pickle.loads(data)
                    print(f"Received model data from {client_address}: {model_data}")
                    client_socket.send(b"Model data received successfully.")
                except Exception as e:
                    print(f"Failed to deserialize data from {client_address}: {e}")
                    client_socket.send(b"Failed to process model data.")
        finally:
            # Remove client from the list and close the connection
            with self.lock:
                del self.clients[client_id]
            client_socket.close()

    def send_to_all_clients(self, message):
        """Send a message to all connected clients."""
        with self.lock:
            for client_id, (client_socket, client_address) in self.clients.items():
                try:
                    client_socket.send(pickle.dumps(message))
                    print(f"Sent message to client {client_id}: {client_address}")
                except Exception as e:
                    print(f"Error sending message to client {client_id}: {e}")

    def get_client_details(self):
        """Retrieve details about all connected clients."""
        with self.lock:
            return [(client_id, client_address) for client_id, (_, client_address) in self.clients.items()]

    def shutdown_server(self):
        """Shut down the server gracefully."""
        with self.lock:
            for client_socket, _ in self.clients.values():
                client_socket.close()
        self.server_socket.close()
        print("Server shut down.")

if __name__ == "__main__":
    # Initialize and start the server control script
    server = ServerControl()
    server.start_server()

    while True:
        print("\nServer Control Options:")
        print("1. Display client details")
        print("2. Send message to all clients")
        print("3. Shutdown server")
        choice = input("Enter your choice: ")

        if choice == '1':
            clients = server.get_client_details()
            if clients:
                print("\nConnected Clients:")
                for client_id, client_address in clients:
                    print(f"Client {client_id}: {client_address}")
            else:
                print("No clients connected.")
        elif choice == '2':
            message = input("Enter message to send to all clients: ")
            server.send_to_all_clients(message)
        elif choice == '3':
            server.shutdown_server()
            break
        else:
            print("Invalid option. Please try again.")
        time.sleep(1)
