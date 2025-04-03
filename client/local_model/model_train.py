import tensorflow as tf

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

def train_local_model(model, x_train, y_train, x_test, y_test, epochs=2):
    """Train the model locally for a given number of epochs."""
    model.fit(x_train, y_train, epochs=epochs, batch_size=64, validation_data=(x_test, y_test), verbose=1)
    return model

def evaluate_model(model, x_test, y_test):
    """Evaluate the model on the test set."""
    loss, accuracy = model.evaluate(x_test, y_test, verbose=2)
    return accuracy
