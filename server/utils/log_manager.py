# utils/log_manager.py

import logging
import os
from pythonjsonlogger.json import JsonFormatter
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = "utils/logs" 

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
    
    # NEW: Explicitly set the file handler's level to match the logger's level
    file_handler.setLevel(logger.level) # <--- ADDED THIS LINE

    logger.addHandler(file_handler)
    logger.propagate = True 

    # NEW: Add a small periodic flushing for diagnostic purposes if logs aren't appearing
    # This creates a custom filter to periodically flush. For production, rely on handler's internal flush.
    class PeriodicFlushFilter(logging.Filter):
        def filter(self, record):
            if (record.levelname in ['CRITICAL', 'ERROR', 'WARNING', 'INFO'] and 
                (record.name == 'root' or record.name.startswith('ServerControlPlaneManager'))):
                file_handler.flush()
            return True
    # file_handler.addFilter(PeriodicFlushFilter()) # <--- OPTIONAL: UNCOMMENT FOR EXTREME DEBUGGING if flushing is the issue