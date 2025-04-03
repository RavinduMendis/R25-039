import logging
from flask_socketio import SocketIO, emit
from client_manager import ClientManager

class SecureC2:
    def __init__(self, ssl_context=None):
        self.ssl_context = ssl_context
        self.socketio = None
        self.client_manager = None

    def initialize_socketio(self, socketio):
        """ Initialize the SocketIO instance """
        self.socketio = socketio

    def initialize_client_manager(self):
        """ Initialize ClientManager only when needed to avoid circular imports """
        from client_manager import ClientManager
        self.client_manager = ClientManager(self)

    def send_client_status_to_dashboard(self):
        """ Fetch client status and send it to the dashboard via SocketIO """
        if self.client_manager:
            client_status = self.client_manager.get_client_status()
            data = {'clients': client_status, 'message': 'New round started'}  # Add custom messages if needed
            self.socketio.emit('update_dashboard', data)
        else:
            logging.error("Client Manager is not initialized!")

    def process_command_queue(self, clients):
        """ Process commands and interact with the client manager """
        if not self.client_manager:
            logging.error("Client Manager is not initialized!")
            return
        
        # Start the rounds on the ClientManager instance
        logging.info("Starting the round of training...")
        self.client_manager.run_rounds()
        logging.info("Training rounds processed successfully.")
