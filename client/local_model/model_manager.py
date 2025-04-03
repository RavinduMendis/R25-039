import pickle
import logging
from .model_train import create_model, train_local_model
from .model_dataset import load_data

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

def get_model():
    """Create and return the initialized model."""
    return create_model()

def load_and_train_model(epochs=5):
    """Load data and train the model."""
    x_train, y_train, x_test, y_test = load_data()
    model = get_model()
    model = train_local_model(model, x_train, y_train, x_test, y_test, epochs)
    return model, x_test, y_test

def send_model_weights(model):
    """Serialize the model weights to send over the network."""
    try:
        model_weights = pickle.dumps(model.get_weights())  # Serialize model weights
        logging.info("Model weights successfully serialized.")
        return model_weights
    except Exception as e:
        logging.error(f"Error serializing model weights: {e}")
        return None  # Return None on failure

def receive_model_weights(serialized_weights):
    """Deserialize the received model weights."""
    try:
        if isinstance(serialized_weights, bytes):
            # Deserialize the weights from bytes object
            weights = pickle.loads(serialized_weights)
            if isinstance(weights, list):  # Ensure it is a valid list of weights
                logging.info("Successfully deserialized model weights.")
                return weights
            else:
                raise TypeError(f"Deserialized object is not a list: {type(weights)}")
        elif isinstance(serialized_weights, list):
            logging.warning("Received weights as a list (already deserialized).")
            return serialized_weights  # Already deserialized, return as is
        else:
            raise TypeError(f"Expected bytes or list, but got {type(serialized_weights)}")
    except Exception as e:
        logging.error(f"Error deserializing model weights: {e}")
        return None  # Return None on failure
def evaluate_model(model, x_test, y_test):
    """Evaluate the model on the test dataset."""
    try:
        loss, accuracy = model.evaluate(x_test, y_test, verbose=0)
        return accuracy
    except Exception as e:
        logging.error(f"Error during model evaluation: {e}")
        return None
