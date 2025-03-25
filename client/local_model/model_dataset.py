import tensorflow as tf

def load_data():
    """Load and preprocess CIFAR-10 dataset."""
    from tensorflow.keras.datasets import cifar10
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    x_train, x_test = x_train / 255.0, x_test / 255.0  # Normalize the data
    y_train = tf.keras.utils.to_categorical(y_train, 10)  # One-hot encode labels
    y_test = tf.keras.utils.to_categorical(y_test, 10)
    return x_train, y_train, x_test, y_test
