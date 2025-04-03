import logging
import threading
import numpy as np
import joblib
import glob
import os
import time
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from collections import deque
from tensorflow.keras.models import load_model
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ADRMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.model_data = deque(maxlen=500)  # Store past model updates
        self.labels = deque(maxlen=500)  # Store labels (0: Normal, 1: Attack)
        self.primary_model_if = None  # Isolation Forest primary model
        self.secondary_model_if = None
        self.primary_model_ae = None  # Autoencoder primary model
        self.secondary_model_ae = None
        self.attack_classifier = None  # Supervised classifier
        self.scaler = StandardScaler()
        self.model_version = 0
        self.model_update_count = 0  # Track the number of updates received
        self.load_latest_models()
        
        # Start background training thread
        threading.Thread(target=self.periodic_training, daemon=True).start()

    def log_client_connection(self, client_address):
        logging.info(f"[ADR] Client {client_address} connected.")

    def log_client_disconnection(self, client_address):
        logging.info(f"[ADR] Client {client_address} disconnected.")

    def monitor_model_update(self, client_address, model_weights, label=0):
        logging.info(f"[ADR] Received model update from {client_address}.")
        self.model_data.append(model_weights)
        self.labels.append(label)
        self.model_update_count += 1
        
        if self.primary_model_if and self.primary_model_ae and self.attack_classifier:
            anomaly_if = self.detect_anomalies_if(model_weights)
            anomaly_ae = self.detect_anomalies_ae(model_weights)
            anomaly_cls = self.detect_anomalies_classifier(model_weights)
            
            if anomaly_if or anomaly_ae or anomaly_cls:
                logging.warning(f"[ADR] Anomalies detected in update from {client_address}.")
        
        self.train_new_models()
    
    def detect_anomalies_if(self, model_weights):
        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        prediction = self.primary_model_if.predict([model_weights_flat])
        return prediction[0] == -1  # IsolationForest returns -1 for anomalies
    
    def detect_anomalies_ae(self, model_weights):
        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        reconstruction = self.primary_model_ae.predict(np.array([model_weights_flat]))
        error = np.mean(np.abs(reconstruction - model_weights_flat))
        return error > 0.1  # Threshold for anomaly detection
    
    def detect_anomalies_classifier(self, model_weights):
        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        model_weights_flat = self.scaler.transform([model_weights_flat])
        prediction = self.attack_classifier.predict(model_weights_flat)
        return prediction[0] == 1  # 1 indicates an attack
    
    def evaluate_model(self, model):
        """
        Evaluates the given model to compare its performance with the current primary model.
        Returns the evaluation score for comparison.
        """
        if isinstance(model, IsolationForest):
            # Here we will assume we have a validation dataset
            validation_data = self.model_data  # Just for example purposes
            validation_data_flat = [np.concatenate([np.ravel(layer) for layer in weights]) for weights in validation_data]
            prediction = model.predict(validation_data_flat)
            accuracy = np.mean(prediction == 1)  # Anomaly detection: predicted as normal
            return accuracy
        
        elif isinstance(model, Sequential):  # Autoencoder
            # For simplicity, use MSE as the metric (reconstruction error)
            validation_data = self.model_data
            validation_data_flat = [np.concatenate([np.ravel(layer) for layer in weights]) for weights in validation_data]
            reconstruction = model.predict(np.array(validation_data_flat))
            error = np.mean(np.abs(reconstruction - validation_data_flat))
            return error  # Lower error means better model
        
        elif isinstance(model, RandomForestClassifier):
            # For RandomForest, use classification accuracy
            validation_data = self.model_data
            validation_labels = self.labels
            validation_data_flat = [np.concatenate([np.ravel(layer) for layer in weights]) for weights in validation_data]
            validation_data_scaled = self.scaler.transform(validation_data_flat)
            accuracy = model.score(validation_data_scaled, validation_labels)  # Accuracy score
            return accuracy
        
        else:
            raise ValueError("Unknown model type for evaluation.")
    
    def train_new_models(self):
        threshold = max(10, int(self.model_update_count / 2))
        if len(self.model_data) < threshold:
            logging.warning(f"[ADR] Not enough data to train new models. Threshold: {threshold}")
            return
        
        X_train = [np.concatenate([np.ravel(layer) for layer in weights]) for weights in self.model_data]
        Y_train = list(self.labels)
        
        self.scaler.fit(X_train)
        X_train_scaled = self.scaler.transform(X_train)
        
        new_if_model = IsolationForest(contamination=0.1, random_state=42)
        new_if_model.fit(X_train)
        
        input_dim = len(X_train[0])
        new_ae_model = Sequential([
            Dense(64, activation='relu', input_shape=(input_dim,)),
            Dense(32, activation='relu'),
            Dense(64, activation='relu'),
            Dense(input_dim, activation='sigmoid')
        ])
        new_ae_model.compile(optimizer='adam', loss='mse')
        new_ae_model.fit(np.array(X_train), np.array(X_train), epochs=10, batch_size=10, verbose=0)
        
        new_cls_model = RandomForestClassifier(n_estimators=100, random_state=42)
        new_cls_model.fit(X_train_scaled, Y_train)
        
        self.model_version += 1
        joblib.dump(new_if_model, f"attackdefense/attackmodel/adr_if_model_v{self.model_version}.pkl")
        new_ae_model.save(f"attackdefense/attackmodel/adr_ae_model_v{self.model_version}.h5")
        joblib.dump(new_cls_model, f"attackdefense/attackmodel/adr_cls_model_v{self.model_version}.pkl")
        
        self.secondary_model_if = new_if_model
        self.secondary_model_ae = new_ae_model
        self.attack_classifier = new_cls_model
        
        if not self.primary_model_if or self.evaluate_model(new_if_model) > self.evaluate_model(self.primary_model_if):
            self.primary_model_if = new_if_model
        if not self.primary_model_ae or self.evaluate_model(new_ae_model) < self.evaluate_model(self.primary_model_ae):  # Minimize error
            self.primary_model_ae = new_ae_model
        if not self.attack_classifier or self.evaluate_model(new_cls_model) > self.evaluate_model(self.attack_classifier):
            self.attack_classifier = new_cls_model
        
        self.model_update_count = 0
    
    def load_latest_models(self):
        model_if_files = glob.glob("attackdefense/attackmodel/adr_if_model_v*.pkl")
        model_ae_files = glob.glob("attackdefense/attackmodel/adr_ae_model_v*.h5")
        model_cls_files = glob.glob("attackdefense/attackmodel/adr_cls_model_v*.pkl")
        
        if model_if_files:
            latest_if_model = max(model_if_files, key=os.path.getctime)
            self.primary_model_if = joblib.load(latest_if_model)
        
        if model_ae_files:
            latest_ae_model = max(model_ae_files, key=os.path.getctime)
            self.primary_model_ae = load_model(latest_ae_model)
        
        if model_cls_files:
            latest_cls_model = max(model_cls_files, key=os.path.getctime)
            self.attack_classifier = joblib.load(latest_cls_model)
        
        logging.info("[ADR] Loaded latest models.")
    
    def periodic_training(self):
        while True:
            time.sleep(60)
            self.train_new_models()
