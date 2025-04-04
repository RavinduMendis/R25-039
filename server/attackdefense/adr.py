# ✅ Your full code with dynamic adaptation and detailed anomaly classification
# Including structured anomaly reports with likely attack types

import logging
import threading
import numpy as np
import joblib
import glob
import os
import time
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense
from collections import deque
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ADRMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.model_data = deque(maxlen=500)
        self.labels = deque(maxlen=500)
        self.model_deltas = deque(maxlen=500)
        self.previous_model_weights = None

        self.primary_model_if = None
        self.secondary_model_if = None
        self.primary_model_ae = None
        self.secondary_model_ae = None
        self.primary_model_delta_if = None
        self.secondary_model_delta_if = None
        self.attack_classifier = None

        self.scaler = StandardScaler()
        self.model_version = 0
        self.model_update_count = 0

        self.load_latest_models()
        threading.Thread(target=self.periodic_training, daemon=True).start()

    def log_client_connection(self, client_address):
        logging.info(f"[ADR] Client {client_address} connected.")

    def log_client_disconnection(self, client_address):
        logging.info(f"[ADR] Client {client_address} disconnected.")

    def monitor_model_update(self, client_address, model_weights, label=0):
        logging.info(f"[ADR] Received model update from {client_address}.")

        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        self.model_data.append(model_weights)
        self.labels.append(label)
        self.model_update_count += 1

        if self.previous_model_weights is not None:
            prev_flat = np.concatenate([np.ravel(layer) for layer in self.previous_model_weights])
            delta = model_weights_flat - prev_flat
            self.model_deltas.append(delta)
        self.previous_model_weights = model_weights

        anomaly_if = anomaly_ae = anomaly_cls = anomaly_delta_if = None
        ae_error = if_score = cls_prob = None

        if self.primary_model_if and self.primary_model_ae and self.attack_classifier:
            anomaly_if = self.detect_anomalies_if(model_weights)
            anomaly_ae, ae_error = self.detect_anomalies_ae(model_weights)
            anomaly_cls = self.detect_anomalies_classifier(model_weights)
            anomaly_delta_if = self.detect_anomalies_delta_if()

            if anomaly_if:
                if_score = self.detect_anomalies_if(model_weights)
            if anomaly_cls:
                cls_prob = self.attack_classifier.predict_proba([model_weights_flat])[0] if self.attack_classifier else None

            self.log_anomaly_report(client_address, anomaly_if, anomaly_ae, anomaly_cls, anomaly_delta_if, ae_error, if_score, cls_prob)

        self.train_new_models()

    def log_anomaly_report(self, client_address, anomaly_if, anomaly_ae, anomaly_cls, anomaly_delta_if, ae_error, if_score, cls_prob):
        timestamp = time.time()

        attack_guess = "None"
        poisoning_type = "Normal"

        if anomaly_if and anomaly_delta_if:
            attack_guess = "Isolation Forest & Delta Spike"
            poisoning_type = "Model Poisoning"
        elif anomaly_ae and not anomaly_if:
            attack_guess = "Autoencoder High Error"
            poisoning_type = "Data Poisoning"
        elif anomaly_cls:
            attack_guess = "Classifier Flagged"
            poisoning_type = "Uncertain (Possibly Mixed)"

        ae_error = ae_error if ae_error is not None else "N/A"
        if_score = if_score if if_score is not None else "N/A"
        cls_prob = cls_prob if cls_prob is not None else "N/A"

        report = f"""
        **Anomaly Report for Client {client_address}**

        | **Field**                             | **Value**                                                      |
        |--------------------------------------|----------------------------------------------------------------|
        | **Client IP**                         | {client_address}                                               |
        | **IF Anomaly**                        | {anomaly_if}                                                   |
        | **AE Anomaly**                        | {anomaly_ae}                                                   |
        | **Classifier Anomaly**               | {anomaly_cls}                                                  |
        | **Delta IF Anomaly**                 | {anomaly_delta_if}                                             |
        | **AE Error**                          | {ae_error}                                                     |
        | **IF Score**                          | {if_score}                                                     |
        | **Classifier Prediction Prob.**      | {cls_prob}                                                     |
        | **Attack Detection Source**          | {attack_guess}                                                 |
        | **Likely Attack Type**               | {poisoning_type}                                               |
        | **Time (UTC)**                        | {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))}   |
        """

        logging.info(report)

    def detect_anomalies_if(self, model_weights):
        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        prediction = self.primary_model_if.predict([model_weights_flat])
        return prediction[0] == -1

    def detect_anomalies_ae(self, model_weights):
        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        reconstruction = self.primary_model_ae.predict(np.array([model_weights_flat]))
        error = np.mean(np.abs(reconstruction - model_weights_flat))
        return error > 0.1, error

    def detect_anomalies_classifier(self, model_weights):
        model_weights_flat = np.concatenate([np.ravel(layer) for layer in model_weights])
        if len(self.model_data) > 0:
            X_train = [np.concatenate([np.ravel(layer) for layer in weights]) for weights in self.model_data]
            self.scaler.fit(X_train)
        model_weights_flat = self.scaler.transform([model_weights_flat])
        prediction = self.attack_classifier.predict(model_weights_flat)
        return prediction[0] == 1

    def detect_anomalies_delta_if(self):
        if not self.primary_model_delta_if or len(self.model_deltas) == 0:
            return False
        delta = self.model_deltas[-1]
        prediction = self.primary_model_delta_if.predict([delta])
        return prediction[0] == -1

    def evaluate_model(self, model, data=None, labels=None):
        if isinstance(model, IsolationForest):
            data_flat = data or [np.concatenate([np.ravel(layer) for layer in weights]) for weights in self.model_data]
            prediction = model.predict(data_flat)
            return np.mean(prediction == 1)

        elif isinstance(model, Sequential):
            data_flat = data or [np.concatenate([np.ravel(layer) for layer in weights]) for weights in self.model_data]
            reconstruction = model.predict(np.array(data_flat))
            error = np.mean(np.abs(reconstruction - data_flat))
            return error

        elif isinstance(model, RandomForestClassifier):
            data_flat = data or [np.concatenate([np.ravel(layer) for layer in weights]) for weights in self.model_data]
            labels = labels or list(self.labels)
            scaled_data = self.scaler.transform(data_flat)
            return model.score(scaled_data, labels)
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

        if len(self.model_deltas) >= threshold:
            new_delta_if = IsolationForest(contamination=0.1, random_state=42)
            new_delta_if.fit(list(self.model_deltas))
            joblib.dump(new_delta_if, f"attackdefense/attackmodel/adr_delta_if_model_v{self.model_version}.pkl")
            if not self.primary_model_delta_if or self.evaluate_model(new_delta_if, data=list(self.model_deltas)) > self.evaluate_model(self.primary_model_delta_if, data=list(self.model_deltas)):
                self.primary_model_delta_if = new_delta_if

        self.model_version += 1
        joblib.dump(new_if_model, f"attackdefense/attackmodel/adr_if_model_v{self.model_version}.pkl")
        new_ae_model.save(f"attackdefense/attackmodel/adr_ae_model_v{self.model_version}.h5")
        joblib.dump(new_cls_model, f"attackdefense/attackmodel/adr_cls_model_v{self.model_version}.pkl")

        self.secondary_model_if = new_if_model
        self.secondary_model_ae = new_ae_model
        self.attack_classifier = new_cls_model

        if not self.primary_model_if or self.evaluate_model(new_if_model) > self.evaluate_model(self.primary_model_if):
            self.primary_model_if = new_if_model
        if not self.primary_model_ae or self.evaluate_model(new_ae_model) < self.evaluate_model(self.primary_model_ae):
            self.primary_model_ae = new_ae_model
        if not self.attack_classifier or self.evaluate_model(new_cls_model) > self.evaluate_model(self.attack_classifier):
            self.attack_classifier = new_cls_model

        self.model_update_count = 0

    def load_latest_models(self):
        model_if_files = glob.glob("attackdefense/attackmodel/adr_if_model_v*.pkl")
        model_ae_files = glob.glob("attackdefense/attackmodel/adr_ae_model_v*.h5")
        model_cls_files = glob.glob("attackdefense/attackmodel/adr_cls_model_v*.pkl")
        model_delta_if_files = glob.glob("attackdefense/attackmodel/adr_delta_if_model_v*.pkl")

        if model_if_files:
            latest_if_model = max(model_if_files, key=os.path.getctime)
            self.primary_model_if = joblib.load(latest_if_model)

        if model_ae_files:
            latest_ae_model = max(model_ae_files, key=os.path.getctime)
            self.primary_model_ae = load_model(latest_ae_model)

        if model_cls_files:
            latest_cls_model = max(model_cls_files, key=os.path.getctime)
            self.attack_classifier = joblib.load(latest_cls_model)

        if model_delta_if_files:
            latest_delta_model = max(model_delta_if_files, key=os.path.getctime)
            self.primary_model_delta_if = joblib.load(latest_delta_model)

        logging.info("[ADR] Loaded latest models.")

    def periodic_training(self):
        while True:
            time.sleep(60)
            self.train_new_models()