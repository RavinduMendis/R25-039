import tensorflow as tf


# Train the model locally
def train_local_model(model, x_train, y_train, x_test, y_test, epochs=1):
    """Train the model locally for a given number of epochs."""
    model.fit(x_train, y_train, epochs=epochs, batch_size=64, validation_data=(x_test, y_test), verbose=1)
    return model