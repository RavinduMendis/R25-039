# server/utils/decorators.py
import logging
import functools
import asyncio # <-- This was the missing import
from typing import Callable, Any

def handle_exceptions(log_message: str):
    """
    A decorator to gracefully handle and log exceptions from a function.
    """
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger = logging.getLogger(func.__module__)
                logger.error(f"{log_message}: {e}", exc_info=True)
                # You can choose to return a default value or re-raise here.
                # For a server, it's often best to let the error propagate
                # to a higher-level handler that can shut down gracefully.
                return None

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger = logging.getLogger(func.__module__)
                logger.error(f"{log_message}: {e}", exc_info=True)
                return None

        # Check if the function is a coroutine and return the appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

