import tensorflow as tf
import socket
import ssl
import pickle
import time

# Define the CNN model architecture for the client to match the server's model
def create_model():
    """Define the CNN model architecture."""
    model = tf.keras.models.Sequential([
        tf.keras.layers.Conv2D(32, (3, 3), activation='relu', input_shape=(32, 32, 3)),
        tf.keras.layers.MaxPooling2D((2, 2)),
        tf.keras.layers.Conv2D(64, (3, 3), activation='relu'),
        tf.keras.layers.MaxPooling2D((2, 2)),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(64, activation='relu'),
        tf.keras.layers.Dense(10, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])
    return model

# Load and preprocess CIFAR-10 dataset
def load_data():
    """Load and preprocess CIFAR-10 dataset."""
    from tensorflow.keras.datasets import cifar10
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    x_train, x_test = x_train / 255.0, x_test / 255.0  # Normalize the data
    y_train = tf.keras.utils.to_categorical(y_train, 10)  # One-hot encode labels
    y_test = tf.keras.utils.to_categorical(y_test, 10)
    return x_train, y_train, x_test, y_test

# Train the model locally
def train_local_model(model, x_train, y_train, x_test, y_test, epochs=1):
    """Train the model locally for a given number of epochs."""
    model.fit(x_train, y_train, epochs=epochs, batch_size=64, validation_data=(x_test, y_test), verbose=1)
    return model

# Receive model weights from the server
def receive_model_from_server(client_socket):
    try:
        # Receive data length first
        data_length_bytes = client_socket.recv(4)
        if not data_length_bytes:
            print("Server closed connection while receiving model.")
            return None

        data_length = int.from_bytes(data_length_bytes, byteorder='big')

        # Receive the model data
        received_data = b''
        while len(received_data) < data_length:
            chunk = client_socket.recv(4096)
            if not chunk:
                print("Server closed connection while receiving model weights.")
                return None
            received_data += chunk

        model_weights = pickle.loads(received_data)
        return model_weights
    except Exception as e:
        print(f"Error receiving model weights: {e}")
        return None

# Send updated model weights to the server
def send_updated_weights_to_server(client_socket, model):
    try:
        updated_weights = pickle.dumps(model.get_weights())
        data_length = len(updated_weights)

        # Send data length first
        client_socket.sendall(data_length.to_bytes(4, byteorder='big'))

        # Send serialized weights
        client_socket.sendall(updated_weights)
        print("Updated weights sent to the server.")
    except Exception as e:
        print(f"Error sending updated weights: {e}")

def start_client():
    server_host = '127.0.0.1'
    server_port = 5000
    retries = 5  # Number of retry attempts
    retry_interval = 5  # Interval between retries in seconds

    # Create a regular TCP/IP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.settimeout(10)  # Set a 10-second timeout for socket operations

    # Wrap the socket using SSL for HTTPS
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_cert_chain(certfile='./certifications/client_cert.pem', keyfile='./certifications/client_key.pem')
    # Disable SSL certificate verification (for self-signed certs only)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    client_socket = context.wrap_socket(client_socket, server_hostname=server_host)

    for attempt in range(retries):
        try:
            client_socket.connect((server_host, server_port))
            print(f"Connected to server at {server_host}:{server_port} via HTTPS.")
            break
        except socket.timeout:
            print(f"Error: Connection timeout. Retrying...")
        except ssl.SSLError as e:
            print(f"SSL error: {e}. Retrying...")
        except Exception as e:
            if attempt < retries - 1:
                print(f"Error connecting to server (attempt {attempt + 1}/{retries}): {e}")
                print(f"Retrying in {retry_interval} seconds...")
                time.sleep(retry_interval)
            else:
                print("Max retries reached. Exiting.")
                return

    rounds = 3
    trained_model = None
    for round_num in range(rounds):
        print(f"\nRound {round_num + 1}...")

        # Receive the model weights from the server
        model_weights = receive_model_from_server(client_socket)

        if model_weights:
            model = create_model()
            model.set_weights(model_weights)
            print("Received model weights from the server.")

            # Load data for training
            x_train, y_train, x_test, y_test = load_data()

            # Train the model for more epochs
            trained_model = train_local_model(model, x_train, y_train, x_test, y_test, epochs=1)
            print("Model trained locally.")

            # Send updated weights back to server
            send_updated_weights_to_server(client_socket, trained_model)
        else:
            print("No model received from server. Exiting.")
            break

    print("Finished training and sending updates to the server.")

    # Optionally, evaluate the final model (after all rounds)
    try:
        if trained_model:
            print("Evaluating final model on the test data...")
            x_train, y_train, x_test, y_test = load_data()
            loss, accuracy = trained_model.evaluate(x_test, y_test, verbose=2)
            print(f"Test Accuracy: {accuracy:.4f}")
    except Exception as e:
        print(f"Error evaluating final model: {e}")

    client_socket.close()

if __name__ == "__main__":
    start_client()
