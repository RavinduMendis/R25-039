# utils/log_manager.py

import logging
import os
from pythonjsonlogger.json import JsonFormatter
from logging.handlers import TimedRotatingFileHandler

# --- FIX START: Define a robust, absolute path for the log directory ---
# Get the directory where the main server script is likely located.
# This assumes a structure where the log_manager package is at the same level as the 'server' directory.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_project_root, "server", "logs")
# --- FIX END ---

class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        kwargs['extra'].update(self.extra)
        return msg, kwargs

def configure_root_logging(logger: logging.Logger): 
    """
    Configures the given logger (intended for the root logger) with a plain text formatter for console output.
    Clears existing handlers to prevent duplicate logs.
    """
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logging.getLogger('websockets.protocol').setLevel(logging.WARNING)
    logging.getLogger('grpc').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
def add_json_file_handler(logger_name: str, log_file_name: str):
    logger = logging.getLogger(logger_name)
    
    json_formatter = JsonFormatter(
        '{ "time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", '
        '"process": "%(process)d", "thread": "%(thread)d", "func": "%(funcName)s", "line": "%(lineno)d", '
        '"message": "%(message)s" }'
    )

    os.makedirs(LOG_DIR, exist_ok=True) 
    file_handler = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, log_file_name),
        when="midnight", interval=1, backupCount=7
    )
    file_handler.setFormatter(json_formatter)
    
    file_handler.setLevel(logger.level)

    logger.addHandler(file_handler)
    logger.propagate = True

    class PeriodicFlushFilter(logging.Filter):
        def filter(self, record):
            if (record.levelname in ['CRITICAL', 'ERROR', 'WARNING', 'INFO'] and 
                (record.name == 'root' or record.name.startswith('ServerControlPlaneManager'))):
                file_handler.flush()
            return True