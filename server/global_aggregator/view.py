import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
from tensorflow.keras.datasets import cifar10
from tensorflow.keras.utils import to_categorical

# CIFAR-10 class labels
class_labels = ['airplane', 'automobile', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck']

# Load CIFAR-10 test dataset
(x_train, y_train), (x_test, y_test) = cifar10.load_data()
y_test = to_categorical(y_test, 10)  # One-hot encode the labels
x_test = x_test.astype('float32') / 255.0  # Normalize the test images

# Load the global model (the final aggregated model after federated learning)
def load_model():
    model = tf.keras.models.load_model('global_model.h5')
    print("Global model loaded.")
    return model

# Evaluate the model on the CIFAR-10 test set
def evaluate_model(model):
    loss, accuracy = model.evaluate(x_test, y_test)
    print(f"Final Model - Loss: {loss:.4f}, Accuracy: {accuracy:.4f}")

# Visualize the predictions of the model on a few test images
def visualize_predictions(model):
    predictions = model.predict(x_test[:5])  # Predict on the first 5 test samples

    # Plot the test images with their predicted and true labels
    for i in range(5):
        plt.imshow(x_test[i])  # Display image
        predicted_label = np.argmax(predictions[i])  # Predicted class index
        true_label = np.argmax(y_test[i])  # True class index
        plt.title(f"Predicted: {class_labels[predicted_label]}, True: {class_labels[true_label]}")
        plt.show()

if __name__ == "__main__":
    # Load the aggregated model
    global_model = load_model()

    # Evaluate the model on the test dataset
    evaluate_model(global_model)

    # Visualize predictions
    visualize_predictions(global_model)
