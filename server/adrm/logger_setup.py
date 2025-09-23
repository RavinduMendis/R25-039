# server/adrm/logger_setup.py

import logging
# UPDATED: Changed to an explicit relative import
from . import config

def setup_loggers():
    """Sets up and returns the general and audit loggers."""

    # --- General Logger ---
    gen_logger = logging.getLogger("ADRM_General")
    gen_logger.setLevel(logging.INFO)
    gen_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    if not gen_logger.handlers:
        gen_file_handler = logging.FileHandler(config.GENERAL_LOG_FILE)
        gen_file_handler.setFormatter(gen_formatter)
        gen_logger.addHandler(gen_file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(gen_formatter)
        gen_logger.addHandler(console_handler)

    # --- Audit Logger ---
    audit_logger = logging.getLogger("ADRM_Audit")
    audit_logger.setLevel(logging.INFO)
    audit_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    if not audit_logger.handlers:
        audit_file_handler = logging.FileHandler(config.AUDIT_LOG_FILE)
        audit_file_handler.setFormatter(audit_formatter)
        audit_logger.addHandler(audit_file_handler)

    # Prevent audit logs from showing up in the general logger's console output
    audit_logger.propagate = False

    return gen_logger, audit_logger