# client/client.py

import asyncio
import grpc
import logging
import os
import uuid
import time
import sys
import datetime
import torch
import io
from typing import Optional, Dict, Any

# Import cryptography libraries for key and certificate management
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.x509.extensions import SubjectAlternativeName, DNSName

# Get the path to the directory containing this script.
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the 'protos' directory to the Python path directly.
protos_path = os.path.join(current_dir, 'cscpm', 'protos')
if protos_path not in sys.path:
    sys.path.append(protos_path)


# Import generated gRPC code from the combined service file.
import client_service_pb2
import client_service_pb2_grpc
from model_manager import ClientModelManager # Import the new model manager

# Configure client-side logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the file path for storing the client ID
CLIENT_ID_FILE = "client_id.txt"
# Define the directory where your mTLS certificates are located.
CERT_DIR = os.path.join(current_dir, "cscpm", "certifications")

# Helper function to serialize the model state dict
def serialize_model_state(state_dict: Dict[str, Any]) -> bytes:
    """
    Serializes a PyTorch model state dictionary into a byte stream.
    """
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()

# Helper function to deserialize the model state dict
def deserialize_model_state(data: bytes) -> Dict[str, Any]:
    """
    Deserializes a byte stream back into a PyTorch model state dictionary.
    """
    buffer = io.BytesIO(data)
    return torch.load(buffer)


def get_or_create_client_id() -> str:
    """
    Retrieves a persistent client ID from a file, or generates a new one if not found.
    """
    if os.path.exists(CLIENT_ID_FILE):
        try:
            with open(CLIENT_ID_FILE, 'r') as f:
                client_id = f.read().strip()
                if client_id:
                    logger.info(f"Loaded existing client ID: {client_id}")
                    return client_id
        except Exception as e:
            logger.warning(f"Could not read client ID from {CLIENT_ID_FILE}: {e}. Generating new ID.")
    
    new_id = f"client_{uuid.uuid4().hex[:12]}"
    try:
        os.makedirs(os.path.dirname(CLIENT_ID_FILE), exist_ok=True)
        with open(CLIENT_ID_FILE, 'w') as f:
            f.write(new_id)
        logger.info(f"Generated and saved new client ID: {new_id}")
    except Exception as e:
        logger.error(f"Could not save new client ID to {CLIENT_ID_FILE}: {e}. Using temporary ID.")
    return new_id


class Client:
    def __init__(self, client_id: str, secure_server_address: str = 'localhost:50051', insecure_server_address: str = 'localhost:50052'):
        self.client_id = client_id
        self.secure_server_address = secure_server_address
        self.insecure_server_address = insecure_server_address
        self.secure_channel: Optional[grpc.aio.Channel] = None
        self.client_service_stub: Optional[client_service_pb2_grpc.ClientServiceStub] = None
        self.client_model_manager = ClientModelManager(client_id) # Instantiate the new model manager

        self.client_key_path = os.path.join(CERT_DIR, f'{self.client_id}.key')
        self.client_crt_path = os.path.join(CERT_DIR, f'{self.client_id}.crt')
        self.ca_crt_path = os.path.join(CERT_DIR, 'ca.crt')
        logger.info(f"Client {self.client_id} initialized.")

    async def _register_client_on_insecure_channel(self) -> bool:
        """
        Performs the one-time registration on the insecure channel.
        Generates a key pair and CSR, sends it to the server, and saves the signed certificate.
        """
        logger.info(f"Client '{self.client_id}' not yet registered. Starting registration on insecure channel...")

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, self.client_id)
            ])
        ).add_extension(
            SubjectAlternativeName([DNSName(self.client_id)]),
            critical=False,
        ).sign(private_key, hashes.SHA256(), default_backend())

        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        try:
            os.makedirs(CERT_DIR, exist_ok=True)
            with open(self.client_key_path, 'wb') as f:
                f.write(private_key_pem)
            logger.info(f"Private key saved to '{self.client_key_path}'")
        except Exception as e:
            logger.error(f"Failed to save private key: {e}")
            return False

        try:
            async with grpc.aio.insecure_channel(self.insecure_server_address) as channel:
                insecure_stub = client_service_pb2_grpc.GreeterStub(channel)
                registration_request = client_service_pb2.ClientRegistrationRequest(
                    client_id=self.client_id,
                    certificate_signing_request=csr.public_bytes(serialization.Encoding.PEM),
                    registration_token='secure-one-time-token'
                )
                response = await insecure_stub.RegisterClient(registration_request, timeout=10)
                
                if response.success:
                    logger.info("Registration successful!")
                    
                    if not response.signed_certificate:
                        logger.error("Received empty signed_certificate from server.")
                        return False
                    
                    with open(self.client_crt_path, 'wb') as f:
                        f.write(response.signed_certificate)
                    logger.info(f"Signed certificate saved to '{self.client_crt_path}'")
                    
                    if not response.ca_certificate:
                        logger.error("Received empty ca_certificate from server.")
                        return False

                    with open(self.ca_crt_path, 'wb') as f:
                        f.write(response.ca_certificate)
                    logger.info(f"CA certificate saved to '{self.ca_crt_path}'")
                    
                    return True
                else:
                    logger.error(f"Registration failed: {response.message}")
                    return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"Registration RPC failed with code {e.code()}: {e.details()}")
            return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred during registration: {e}")
            return False

    async def connect(self):
        """Establishes a secure gRPC connection to the server using mTLS."""
        if not all(os.path.exists(p) for p in [self.ca_crt_path, self.client_key_path, self.client_crt_path]):
            logger.info("Client certificates not found. Attempting registration...")
            if not await self._register_client_on_insecure_channel():
                logger.critical("Registration failed. Cannot proceed with secure connection.")
                return False
        
        try:
            with open(self.client_crt_path, 'rb') as f: client_cert_pem = f.read()
            with open(self.client_key_path, 'rb') as f: client_key_pem = f.read()
            with open(self.ca_crt_path, 'rb') as f: ca_cert_pem = f.read()
            
            credentials = grpc.ssl_channel_credentials(
                root_certificates=ca_cert_pem,
                private_key=client_key_pem,
                certificate_chain=client_cert_pem
            )
            logger.info("mTLS credentials loaded successfully.")
        except Exception as e:
            logger.error(f"An unexpected error occurred creating mTLS credentials: {e}", exc_info=True)
            return False

        channel_options = [
            ('grpc.ssl_target_name_override', 'localhost'),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 5000),
            ('grpc.keepalive_permit_without_calls', True),
            ('grpc.http2.max_pings_without_data', 0),
            ('grpc.http2.min_time_between_pings_ms', 10000),
            ('grpc.http2.min_ping_interval_without_data_ms', 300000)
        ]
        
        self.secure_channel = grpc.aio.secure_channel(
            self.secure_server_address,
            credentials,
            options=channel_options
        )
        self.client_service_stub = client_service_pb2_grpc.ClientServiceStub(self.secure_channel)
        
        try:
            register_request = client_service_pb2.RegisterClientRequest(
                client_id=self.client_id,
                client_info="Python Client"
            )
            response = await self.client_service_stub.RegisterClient(register_request, timeout=10)
            
            if response.success:
                logger.info(f"Client {self.client_id} successfully connected and registered with server: {response.message}")
                return True
            else:
                logger.error(f"Client {self.client_id} failed to connect or register on secure channel: {response.message}")
                await self.secure_channel.close()
                self.secure_channel = None
                self.client_service_stub = None
                return False

        except grpc.aio.AioRpcError as e:
            logger.error(f"Client {self.client_id} failed to connect or register on secure channel: {e.code()} - {e.details()}")
            await self.secure_channel.close()
            self.secure_channel = None
            self.client_service_stub = None
            return False

    async def disconnect(self):
        """Closes the gRPC connection."""
        if self.secure_channel:
            await self.secure_channel.close()
            logger.info(f"Client {self.client_id} disconnected.")
            self.secure_channel = None
            self.client_service_stub = None

    async def _handle_training_round(self):
        """
        Handles a single federated learning round.
        Fetches the global model, trains locally, and sends the update back.
        """
        logger.info(f"Client {self.client_id} starting a new training round.")
        
        try:
            # 1. Fetch the global model from the server
            fetch_request = client_service_pb2.FetchModelRequest(client_id=self.client_id)
            model_response = await self.client_service_stub.FetchModel(fetch_request, timeout=30)
            
            if not model_response.success:
                logger.error(f"Failed to fetch global model: {model_response.message}")
                return
            
            global_model_state = deserialize_model_state(model_response.model_data)
            logger.info("Successfully fetched the global model.")
            
            # 2. Train the model on local data
            updated_model_state = self.client_model_manager.train_model(global_model_state)
            
            # 3. Serialize the updated model and send it back to the server
            updated_model_data = serialize_model_state(updated_model_state)
            update_request = client_service_pb2.SendModelUpdateRequest(
                client_id=self.client_id,
                model_update=updated_model_data
            )
            update_response = await self.client_service_stub.SendModelUpdate(update_request, timeout=60)
            
            if update_response.success:
                logger.info("Successfully sent model update to the server.")
            else:
                logger.error(f"Failed to send model update: {update_response.message}")

        except grpc.aio.AioRpcError as e:
            logger.error(f"RPC error during training round: {e.code()} - {e.details()}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during a training round.")

    async def run(self):
        """Main client loop for heartbeats and training."""
        if not await self.connect():
            logger.critical(f"Client {self.client_id} could not establish a secure connection. Exiting.")
            return

        logger.info(f"Client {self.client_id} running. Sending heartbeats and awaiting training rounds...")
        
        # This is the main loop. It handles both heartbeats and training.
        try:
            while True:
                # Send heartbeat
                heartbeat_request = client_service_pb2.HeartbeatRequest(
                    client_id=self.client_id,
                    timestamp=int(time.time())
                )
                
                try:
                    heartbeat_response = await self.client_service_stub.SendHeartbeat(heartbeat_request, timeout=10)
                    
                    if heartbeat_response.success:
                        logger.debug(f"Client {self.client_id} sent heartbeat. Server time: {heartbeat_response.server_timestamp}")
                        
                        # --- THIS IS THE CORRECTED LOGIC ---
                        # The server now tells the client if a new round is available
                        # via the heartbeat response, eliminating the old, separate RPC call.
                        if heartbeat_response.new_round_available:
                            logger.info(f"Server signaled a new training round is available. Starting training...")
                            await self._handle_training_round()
                            logger.info(f"Training round completed. Resuming heartbeat cycle.")
                        
                    else:
                        logger.warning(f"Heartbeat failed for client {self.client_id}: {heartbeat_response.message}")
                        
                except grpc.aio.AioRpcError as e:
                    logger.error(f"Heartbeat RPC failed: {e.code()} - {e.details()}")
                    # If we get a connection error, try to reconnect
                    if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]:
                        logger.info("Connection issue detected. Attempting to reconnect...")
                        await self.disconnect()
                        if not await self.connect():
                            logger.error("Reconnection failed. Will retry in next heartbeat cycle.")
                        continue
                except Exception as e:
                    logger.exception(f"Unexpected error during heartbeat: {e}")
                
                # Wait before sending the next heartbeat
                await asyncio.sleep(10) # Send heartbeat every 10 seconds
                
        except asyncio.CancelledError:
            logger.info(f"Client {self.client_id} run loop cancelled.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred in client {self.client_id} run loop.")
        finally:
            await self.disconnect()


async def main():
    client_id = get_or_create_client_id()
    client = Client(client_id)
    await client.run()

if __name__ == "__main__":
    try:
        # A common practice is to create and run the main function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client shutdown initiated by user.")
    except Exception as e:
        logger.critical(f"Client exited with an unhandled error: {e}", exc_info=True)
