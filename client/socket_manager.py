import socket
import ssl
import logging
import pickle

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

CLIENT_PORT = 6001  # Static client port

def create_secure_socket(server_host, server_port, certfile, keyfile):
    """Create a secure socket connection with a static port."""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        client_socket.bind(('0.0.0.0', CLIENT_PORT))  # Bind to static client port
        client_socket.settimeout(10)  # 10-second timeout

        # Wrap socket with SSL for security
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Set to CERT_REQUIRED for full security

        secure_socket = context.wrap_socket(client_socket, server_hostname=server_host)
        return secure_socket
    except Exception as e:
        logging.error(f"Failed to create secure socket: {e}")
        return None

def receive_model_from_server(client_socket):
    """Receive model weights from the server."""
    try:
        # Receive data length (4 bytes)
        data_length_bytes = client_socket.recv(4)
        if not data_length_bytes:
            logging.error("Server closed connection while receiving model.")
            return None

        data_length = int.from_bytes(data_length_bytes, byteorder='big')

        # Receive the model data
        received_data = bytearray()
        while len(received_data) < data_length:
            chunk = client_socket.recv(min(4096, data_length - len(received_data)))
            if not chunk:
                logging.error("Server closed connection unexpectedly.")
                return None
            received_data.extend(chunk)

        logging.info(f"Received {len(received_data)} bytes of model data.")
        return pickle.loads(received_data)  # Deserialize the model weights
    except Exception as e:
        logging.error(f"Error receiving model weights: {e}")
        return None

def send_updated_weights_to_server(client_socket, model):
    """Send updated model weights to the server."""
    try:
        updated_weights = pickle.dumps(model.get_weights())  # Serialize model weights
        data_length = len(updated_weights)

        # Send data length (4 bytes)
        client_socket.sendall(data_length.to_bytes(4, byteorder='big'))

        # Send serialized weights
        sent_bytes = 0
        while sent_bytes < data_length:
            sent = client_socket.send(updated_weights[sent_bytes:sent_bytes + 4096])
            if sent == 0:
                logging.error("Connection lost while sending weights.")
                return False
            sent_bytes += sent

        logging.info("Updated weights sent successfully.")
        return True
    except Exception as e:
        logging.error(f"Error sending updated weights: {e}")
        return False
