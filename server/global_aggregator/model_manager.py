import tensorflow as tf
from tensorflow.keras.datasets import cifar10
from tensorflow.keras.utils import to_categorical
import os
import numpy as np
from .model import create_model, load_cifar10

def train_initial_model():
    """Train the model on CIFAR-10 and save the weights."""
    model = create_model()
    (x_train, y_train), (x_test, y_test) = load_cifar10()

    if os.path.exists("initial_model_weights.h5"):
        print("Loading saved model weights.")
        model.load_weights("initial_model_weights.h5")
    else:
        print("Training model...")
        model.fit(x_train, y_train, epochs=1, validation_data=(x_test, y_test), batch_size=64)
        model.save_weights("initial_model_weights.h5")

    test_loss, test_acc = model.evaluate(x_test, y_test)
    print(f"Test accuracy: {test_acc:.4f}")
    return model

def test_model_on_cifar10(model):
    """Evaluate the given model on CIFAR-10 test dataset."""
    (_, _), (x_test, y_test) = load_cifar10()
    test_loss, test_acc = model.evaluate(x_test, y_test)
    print(f"[TEST] Aggregated Model Accuracy on CIFAR-10: {test_acc:.4f}")
    return test_acc