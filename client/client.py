import time
import socket
import ssl
from socket_manager import create_secure_socket, receive_model_from_server, send_updated_weights_to_server
from edge_node import edge_node_function

def start_client():
    server_host = '127.0.0.1'
    server_port = 5000
    client_port = 6001  # Static port for the client
    certfile = './certifications/client_cert.pem'
    keyfile = './certifications/client_key.pem'
    retries = 5
    retry_interval = 5

    # Create the raw socket first and bind before SSL wrapping
    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        raw_socket.bind(('0.0.0.0', client_port))  # Bind before wrapping
    except OSError as e:
        print(f"Error binding to port {client_port}: {e}")
        return

    # Wrap the socket with SSL after binding
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    client_socket = context.wrap_socket(raw_socket, server_hostname=server_host)

    # Retry logic for connecting to the server
    for attempt in range(retries):
        try:
            client_socket.connect((server_host, server_port))
            print(f"Connected to server at {server_host}:{server_port} from static port {client_port}.")
            break
        except (socket.timeout, ssl.SSLError, socket.error) as e:
            print(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(retry_interval)
            else:
                print("Max retries reached. Exiting.")
                return

    # Run edge node function to handle training and sending updates
    edge_node_function(client_socket)

    client_socket.close()

if __name__ == "__main__":
    start_client()
