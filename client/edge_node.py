import logging
import tensorflow as tf
import pickle
import os
import time
from local_model.model_manager import load_and_train_model, send_model_weights, receive_model_weights
from socket_manager import receive_model_from_server, send_updated_weights_to_server
import socket

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def evaluate_model(model, x_test, y_test):
    """Evaluate the model on the test dataset."""
    try:
        loss, accuracy = model.evaluate(x_test, y_test, verbose=0)
        return accuracy
    except Exception as e:
        logging.error(f"Error during model evaluation: {e}")
        return None

def print_model_details(model):
    """Print all details of the model, including architecture, summary, and weights."""
    if isinstance(model, tf.keras.Model):
        logging.info("Model Architecture:")
        for layer in model.layers:
            logging.info(f"Layer: {layer.name}, Type: {type(layer)}, Output Shape: {layer.output_shape}")
        
        logging.info("Model Summary:")
        model.summary()

        logging.info("Model Weights:")
        for layer in model.layers:
            weights = layer.get_weights()
            if weights:
                logging.info(f"Layer {layer.name} weights: {weights}")
            else:
                logging.info(f"Layer {layer.name} has no weights.")
    elif isinstance(model, list):
        logging.info("Model is a list, likely just weights:")
        for idx, item in enumerate(model):
            logging.info(f"Item {idx}: {item}")
    else:
        logging.error("Unknown model format received.")

def save_model_weights(model, version):
    """Save model weights with versioning and timestamp."""
    try:
        # Get model weights
        weights = model.get_weights()

        # Create a directory for model versions if it doesn't exist
        os.makedirs("model_versions", exist_ok=True)

        # Create a filename based on version and timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"model_versions/model_v{version}_{timestamp}.pkl"

        # Serialize and save the model weights
        with open(filename, 'wb') as f:
            pickle.dump(weights, f)
        
        logging.info(f"Model weights saved as {filename}")
        return filename
    except Exception as e:
        logging.error(f"Error saving model weights: {e}")
        return None

def send_model_weights_to_server(client_socket, filename):
    """Send the model weights file to the server."""
    try:
        with open(filename, 'rb') as file:
            model_data = file.read()
            send_updated_weights_to_server(client_socket, model_data)
        logging.info(f"Sent model weights file {filename} to the server.")
    except Exception as e:
        logging.error(f"Error sending model weights file {filename}: {e}")

def send_model_weights_directly(client_socket, model):
    """Send the serialized model weights directly to the server."""
    try:
        # Serialize model weights using pickle
        model_weights = pickle.dumps(model.get_weights())
        
        # Send the length of the model data first
        model_data_length = len(model_weights)
        client_socket.sendall(model_data_length.to_bytes(4, 'big'))  # Sending size as 4 bytes
        
        # Send the actual model weights
        client_socket.sendall(model_weights)
        logging.info("Sent model weights directly to the server.")
    except Exception as e:
        logging.error(f"Error sending model weights: {e}")

def receive_full_data(client_socket):
    """Receive data from the socket in a way that ensures complete data is received."""
    try:
        # First, receive the length of the data (4 bytes)
        length_data = client_socket.recv(4)
        if len(length_data) < 4:
            logging.error("Error receiving length of model data.")
            return None

        # Extract the length from the first 4 bytes
        data_length = int.from_bytes(length_data, 'big')
        logging.info(f"Expecting {data_length} bytes of model data.")

        # Now receive the full data based on the expected length
        data = b""
        while len(data) < data_length:
            chunk = client_socket.recv(min(4096, data_length - len(data)))
            if not chunk:
                logging.error("Error receiving model data or connection lost.")
                return None
            data += chunk
        logging.info(f"Successfully received {len(data)} bytes of model data.")
        return data
    except Exception as e:
        logging.error(f"Error receiving model data: {e}")
        return None

def edge_node_function(client_socket):
    """Edge node function to receive model, train it, and send back the updated weights."""
    
    logging.info("Waiting to receive initial model from the server.")
    
    try:
        # Receive the initial model from the server
        model_data = receive_full_data(client_socket)
        
        if model_data:
            # Deserialize model weights into a Keras model
            model = receive_model_weights(model_data)
            #logging.info("Received initial model weights from the server.")
            
            # Print model details
            #logging.info("Server sent the following model:")
            #print_model_details(model)
            
            # Train the model locally
            trained_model, x_test, y_test = load_and_train_model(epochs=1)
            logging.info("Model trained locally.")
    
            # Save and send the trained model weights directly (no .h5 file)
            send_model_weights_directly(client_socket, trained_model)

            # Evaluate the trained model
            accuracy = evaluate_model(trained_model, x_test, y_test)
            if accuracy is not None:
                logging.info(f"Test Accuracy: {accuracy:.4f}")
            else:
                logging.error("Failed to evaluate the model. Accuracy is unavailable.")
            
            # Listen for the next rounds of updates
            while True:
                logging.info("Waiting for the next model from the server.")
                try:
                    client_socket.settimeout(60)
                    model_data = receive_full_data(client_socket)
                    
                    if model_data:
                        # Deserialize model weights and apply them to the model
                        model = receive_model_weights(model_data)
                        #logging.info("Received new model weights from the server.")
                        
                        #logging.info("Server sent the following updated model:")
                        #print_model_details(model)
                        
                        # Continue training with the new weights
                        trained_model, x_test, y_test = load_and_train_model(epochs=1)
                        logging.info("Model trained locally.")
                        
                        # Send the updated model weights directly
                        send_model_weights_directly(client_socket, trained_model)

                        # Evaluate the updated model
                        accuracy = evaluate_model(trained_model, x_test, y_test)
                        if accuracy is not None:
                            logging.info(f"Test Accuracy: {accuracy:.4f}")
                        else:
                            logging.error("Failed to evaluate the updated model.")
                    else:
                        logging.info("No model received from server. Exiting.")
                        break  # Exit when no model is received (training complete or server disconnected)
                except socket.timeout:
                    logging.info("Timeout waiting for the server. Retrying...")
                except Exception as e:
                    logging.error(f"Error receiving model: {e}")
                    break  # Exit the loop on error
        else:
            logging.error("No model received from server. Exiting.")
    except Exception as e:
        logging.error(f"Error in edge node function: {e}")
