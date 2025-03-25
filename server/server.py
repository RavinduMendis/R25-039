import socket
import ssl
import threading
import time
# import curses  # Commented out since we're not using the UI part for now
from client_manager import ClientManager
# from colorama import Fore, Style, init  # Commented out as well

# Initialize colorama
# init(autoreset=True)  # Commented out for now

# Commented out UI function since we're not using it
# def update_status_ui(stdscr, client_manager):
#     """Handles real-time display of client status in the terminal."""
#     curses.curs_set(0)  # Hide the cursor
#     curses.start_color()
#     curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Green for Active
#     curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)  # Red for Disconnected

#     while True:
#         stdscr.clear()
#         stdscr.addstr(0, 0, f"{'Client Name':<15} {'IP Address':<15} {'Port':<8} {'Status':<12} {'Rounds Left':<12} {'Model Sent':<20} {'Model Received':<20}\n", curses.A_BOLD)

#         with client_manager.lock:
#             clients = client_manager.clients.items()

#         for idx, (client_address, (secure_client_socket, status, model_send_status, model_receive_status)) in enumerate(clients, start=1):
#             client_ip = client_address[0]
#             client_port = client_address[1]
#             rounds_left = client_manager.rounds - client_manager.current_round

#             if status == "connected":
#                 color = curses.color_pair(1)  # Green for active
#                 client_status = "Active"
#             else:
#                 color = curses.color_pair(2)  # Red for disconnected
#                 client_status = "Disconnected"

#             # Add color for model send and receive status
#             model_send_color = Fore.GREEN if model_send_status == "Sent" else Fore.YELLOW
#             model_receive_color = Fore.GREEN if model_receive_status == "Received" else Fore.YELLOW

#             # Display client status
#             stdscr.addstr(idx, 0, f"{f'client{idx}':<15} {client_ip:<15} {client_port:<8} {client_status:<12} {rounds_left:<12} "
#                                   f"{model_send_color}{model_send_status:<20}{Style.RESET_ALL} "
#                                   f"{model_receive_color}{model_receive_status:<20}{Style.RESET_ALL}", color)

#         stdscr.refresh()
#         time.sleep(2)

def start_server():
    """Start the server, manage client connections."""
    
    # Create a TCP/IP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1', 5000))  # Bind the server to localhost and port 5001
    server_socket.listen(5)  # Listen for up to 5 connections
    print("Server listening...")

    # Set up SSL context for secure communication
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile='./certifications/server.crt', keyfile='./certifications/server.key')

    # Initialize the ClientManager to handle client-related logic
    client_manager = ClientManager()

    # Start a new thread to handle incoming client connections
    threading.Thread(target=client_manager.accept_clients, args=(server_socket, context), daemon=True).start()

    # Main server loop can be kept for other functionalities or can be left empty
    try:
        while True:
            time.sleep(1)  # Server can wait here for client connections
    except KeyboardInterrupt:
        print("Server stopped manually.")  # Graceful shutdown on Ctrl+C

if __name__ == "__main__":
    start_server()
