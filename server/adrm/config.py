# server/adrm/config.py

import os

# --- Directory and File Paths ---
DB_DIR = "database"
LOG_DIR = "logs"
MODEL_DIR = os.path.join(DB_DIR, "adrm_models") # Directory for ML models

# Ensure directories exist
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

BLOCKED_CLIENTS_FILE = os.path.join(DB_DIR, "adrm_blocked_clients.json")
AUDIT_LOG_FILE = os.path.join(LOG_DIR, "adrm_audit.log")
GENERAL_LOG_FILE = os.path.join(LOG_DIR, "adrm_general.log")
PERFORMANCE_LOG_FILE = os.path.join(DB_DIR, "adrm_performance_log.json")

# ML Model Paths
CHAMPION_MODEL_PATH = os.path.join(MODEL_DIR, "champion_model.pkl")
CHALLENGER_MODEL_PATH = os.path.join(MODEL_DIR, "challenger_model.pkl")

# --- Response System Settings ---
BLOCK_DURATION_MINUTES = 0.30
REPUTATION_PENALTY_FOR_BLOCK = 15

# --- ML Model & Engine Settings ---
# How much better (as a multiplier) a challenger's performance must be to be promoted.
# 1.1 means the challenger must be at least 10% better than the champion.
PROMOTION_THRESHOLD = 1.1

# How many updates to collect before retraining the challenger model.
CHALLENGER_TRAINING_BATCH_SIZE = 10


# --- NEWLY ADDED ---
# The statistical threshold (Modified Z-Score) for detecting outliers in a group of updates.
# A common value is 3.5, which is fairly strict.
CROSS_CLIENT_THRESHOLD = 3.5