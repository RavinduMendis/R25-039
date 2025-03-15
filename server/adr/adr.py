import socket
import pickle
import random
import time


def detect_anomaly(model_weights):
    """Simulated anomaly detection (Replace with ML Model)."""
    return random.choice(["trusted", "malicious"])

def send_to_adr(model_weights, adr_host, adr_port):
    try:
        adr_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        adr_socket.connect((adr_host, adr_port))

        serialized_weights = pickle.dumps(model_weights)
        adr_socket.sendall(len(serialized_weights).to_bytes(4, byteorder='big'))
        adr_socket.sendall(serialized_weights)

        response = adr_socket.recv(1024).decode()
        adr_socket.close()

        return response == "trusted"
    except Exception as e:
        print(f"⚠️ Error communicating with ADR: {e}")
        return False

def start_adr_server(host="127.0.0.1", port=5001):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    print(f"🟢 ADR System listening on {host}:{port}")

    while True:
        client_socket, client_address = server_socket.accept()
        print(f"🔗 ADR: Connection from {client_address}")

        try:
            data_length = int.from_bytes(client_socket.recv(4), byteorder='big')
            received_data = b''
            while len(received_data) < data_length:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                received_data += chunk

            if len(received_data) == data_length:
                model_weights = pickle.loads(received_data)
                result = detect_anomaly(model_weights)

                if result == "trusted":
                    client_socket.send(b"trusted")
                else:
                    client_socket.send(b"malicious")
        finally:
            client_socket.close()
