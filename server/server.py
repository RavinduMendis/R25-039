# server.py
# Server - Client Manager 

import socket
import ssl
import threading
import curses

from client_manager import ClientManager

# Main server function
def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1', 5000))
    server_socket.listen(5)
    print("Server listening...")

    # Create an SSL context and load the server's certificate and key
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile='./certifications/server.crt', keyfile='./certifications/server.key')

    # Initialize Client Manager
    client_manager = ClientManager()

    # Start client manager in a separate thread
    threading.Thread(target=client_manager.accept_clients, args=(server_socket, context), daemon=True).start()

    # Start the terminal UI with curses
    curses.wrapper(client_manager.terminal_ui)

if __name__ == "__main__":
    start_server()
