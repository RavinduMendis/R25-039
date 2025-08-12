import logging
from typing import TYPE_CHECKING, Any # Added Any for type hinting

# Import the helper function for JSON file logging and the LoggerAdapter
from utils.log_manager import add_json_file_handler, ContextAdapter # Assuming utils/log_manager.py exists

# To avoid circular imports if needed and enable type hinting
if TYPE_CHECKING:
    from client_manager import ClientManager
    from scpm.scpm import ServerControlPlaneManager

class BaseCommunicationHandler: # Renamed from BaseHandler for clarity and to avoid conflicts
    """
    Base class for all client connection handlers (e.g., WebSocket, gRPC, HTTP API).
    Provides common functionalities like access to ClientManager and SCPM, and standardized logging.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.logger = logging.getLogger(self.__class__.__name__)

        # Add a dedicated JSON file handler for this handler's logs
        # The file name will be based on the handler's class name (e.g., "GrpcHandler.log")
        add_json_file_handler(self.__class__.__name__, f"{self.__class__.__name__.lower()}.log")

        # Adapt this logger for consistent context handling
        self.logger = ContextAdapter(self.logger, {"component": self.__class__.__name__})

        self.logger.debug("BaseCommunicationHandler initialized.")

    async def start_listener(self):
        """Abstract method to start the listener for this handler."""
        raise NotImplementedError("Subclasses must implement start_listener()")

    async def stop_listener(self):
        """Abstract method to stop the listener for this handler."""
        raise NotImplementedError("Subclasses must implement stop_listener()")

    async def handle_client(self, client_connection: Any):
        """Abstract method to handle a new client connection."""
        raise NotImplementedError("Subclasses must implement handle_client()")