import tensorflow as tf
from tensorflow.keras.datasets import cifar10
from tensorflow.keras.utils import to_categorical
import os

# Load CIFAR-10 dataset and inspect it
data = cifar10.load_data()
print(f"Loaded CIFAR-10 dataset: {len(data)} items")
print(f"Train data: {data[0][0].shape}, Train labels: {data[0][1].shape}")
print(f"Test data: {data[1][0].shape}, Test labels: {data[1][1].shape}")

# Unpack the data as expected
(x_train, y_train), (x_test, y_test) = data

# Normalize the images to range [0,1]
x_train, x_test = x_train / 255.0, x_test / 255.0

# Convert labels to one-hot encoding
y_train, y_test = to_categorical(y_train, 10), to_categorical(y_test, 10)


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

def train_initial_model():
    """Train the model on CIFAR-10 and save the weights."""
    model = create_model()

    # Check if a saved model exists
    if os.path.exists("initial_model_weights.h5"):
        print("Loading saved model weights.")
        model.load_weights("initial_model_weights.h5")  # Load saved weights if available
    else:
        print("Training model...")
        model.fit(x_train, y_train, epochs=1, validation_data=(x_test, y_test), batch_size=64)
        model.save_weights("initial_model_weights.h5")  # Save weights after training

    # Evaluate on test set
    test_loss, test_acc = model.evaluate(x_test, y_test)
    print(f"Test accuracy: {test_acc:.4f}")
    return model
