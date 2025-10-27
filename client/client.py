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
import threading
import requests
from typing import Optional, Dict, Any, Literal, List
import re

from sam import sss
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import socket

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.x509.extensions import SubjectAlternativeName, DNSName

# Setup paths for protobufs
current_dir = os.path.dirname(os.path.abspath(__file__))
protos_path = os.path.join(current_dir, 'cscpm', 'protos')
if protos_path not in sys.path:
    sys.path.append(protos_path)

import client_service_pb2
import client_service_pb2_grpc
from model_manager import ClientModelManager, deserialize_model_state, serialize_model_state
from ppm.dp import DifferentialPrivacy
from ppm.he import HomomorphicEncryption

# Client-side wrapper for Secret Sharing
class SecretSharing:
    """Client-side class for splitting a model update into shares."""
    def __init__(self, num_shares: int, threshold: int):
        self.num_shares = num_shares
        self.threshold = threshold
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sss_handler = sss.SecretSharing(num_shares=num_shares, threshold=threshold)
        self.logger.info(f"Client-side SecretSharing initialized with {num_shares} shares and a threshold of {threshold}.")

    def split_model(self, state_dict: Dict[str, Any]) -> List[bytes]:
        """Serializes and splits a model state dictionary into secret share bundles."""
        self.logger.info(f"Splitting model state into {self.num_shares} share bundles with a threshold of {self.threshold}.")
        share_bundles = self.sss_handler.split_model(state_dict)
        self.logger.info(f"Model state split into {len(share_bundles)} bundles.")
        return share_bundles

# --- Global Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

CLIENT_ID_FILE = "client_id.txt"
CERT_DIR = os.path.join(current_dir, "cscpm", "certifications")
API_PORT = 8000
HEARTBEAT_INTERVAL = 1 # seconds

# --- Privacy Preferences API (for dash.py) ---
class PrivacyPreferences:
    def __init__(self):
        self.privacy_method: Literal["HE", "SSS", "Normal", "NONE"] = "NONE"

    def set_method(self, method: Literal["HE", "SSS", "Normal", "NONE"]):
        self.privacy_method = method
        logger.info(f"Privacy method set to: {self.privacy_method}")

preferences = PrivacyPreferences()

class Preference(BaseModel):
    # Allow API to accept "NONE" to enable pausing
    method: Literal["HE", "SSS", "Normal", "NONE"]

api_app = FastAPI()

@api_app.post("/set_privacy_preference")
def set_privacy_preference(preference: Preference):
    """API endpoint to set the client's preferred privacy method."""
    try:
        preferences.set_method(preference.method)
        return {"status": "success", "message": f"Privacy method updated to {preference.method}"}
    except Exception as e:
        logger.error(f"Failed to set privacy preference: {e}")
        return {"status": "error", "message": "Failed to update preference."}

@api_app.get("/get_privacy_preference")
def get_privacy_preference():
    """API endpoint to retrieve the current privacy method."""
    return {"status": "success", "method": preferences.privacy_method}

def start_api_server(port):
    """Runs the FastAPI server in a separate thread."""
    uvicorn.run(api_app, host="0.0.0.0", port=port, log_level="warning")

# --- Client ID Management ---
def get_or_create_client_id() -> str:
    """Retrieves a persistent client ID from a file, or generates a new one."""
    if os.path.exists(CLIENT_ID_FILE):
        try:
            with open(CLIENT_ID_FILE, 'r') as f:
                client_id = f.read().strip()
                if client_id:
                    logger.info(f"Loaded existing client ID: {client_id}")
                    return client_id
        except Exception as e:
            logger.warning(f"Could not read client ID: {e}. Generating new ID.")
    
    new_id = f"client_{uuid.uuid4().hex[:6]}"
    try:
        os.makedirs(os.path.dirname(CLIENT_ID_FILE), exist_ok=True)
        with open(CLIENT_ID_FILE, 'w') as f:
            f.write(new_id)
        logger.info(f"Generated and saved new client ID: {new_id}")
    except Exception as e:
        logger.error(f"Could not save new client ID: {e}. Using temporary ID.")
    return new_id


# --- Main Client Class ---
class Client:
    def __init__(self, client_id: str, secure_server_address: str = 'localhost:50051', insecure_server_address: str = 'localhost:50052'):
        self.client_id = client_id
        self.secure_server_address = secure_server_address
        self.insecure_server_address = insecure_server_address
        self.secure_channel: Optional[grpc.aio.Channel] = None
        self.client_service_stub: Optional[client_service_pb2_grpc.ClientServiceStub] = None
        
        cfg = {'local_epochs': 1}
        self.client_model_manager = ClientModelManager(client_id=self.client_id, cfg=cfg)
        
        self.dp_handler = DifferentialPrivacy(epsilon=1.0, clipping_norm=1.0)
        self.he_handler = HomomorphicEncryption()
        self.sss_handler = SecretSharing(num_shares=3, threshold=2)

        self.client_key_path = os.path.join(CERT_DIR, f'{self.client_id}.key')
        self.client_crt_path = os.path.join(CERT_DIR, f'{self.client_id}.crt')
        self.ca_crt_path = os.path.join(CERT_DIR, 'ca.crt')
        logger.info(f"Client {self.client_id} initialized.")

    async def _register_client_on_insecure_channel(self) -> bool:
        """Handles one-time registration and certificate retrieval."""
        logger.info(f"Client '{self.client_id}' not yet registered. Starting registration...")
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.client_id)])
        ).add_extension(SubjectAlternativeName([DNSName(self.client_id)]), critical=False,).sign(private_key, hashes.SHA256(), default_backend())
        private_key_pem = private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption())
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
                    client_id=self.client_id, certificate_signing_request=csr.public_bytes(serialization.Encoding.PEM), registration_token='secure-one-time-token'
                )
                response = await insecure_stub.RegisterClient(registration_request, timeout=10)
                if response.success:
                    logger.info("Registration successful!")
                    with open(self.client_crt_path, 'wb') as f: f.write(response.signed_certificate)
                    logger.info(f"Signed certificate saved to '{self.client_crt_path}'")
                    with open(self.ca_crt_path, 'wb') as f: f.write(response.ca_certificate)
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

    async def connect(self) -> bool:
        """Establishes a secure gRPC connection to the server using mTLS."""
        if not all(os.path.exists(p) for p in [self.ca_crt_path, self.client_key_path, self.client_crt_path]):
            if not await self._register_client_on_insecure_channel():
                logger.critical("Registration failed. Cannot proceed.")
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
            logger.error(f"Error creating mTLS credentials: {e}", exc_info=True)
            return False

        channel_options = [('grpc.ssl_target_name_override', 'localhost')]
        
        self.secure_channel = grpc.aio.secure_channel(self.secure_server_address, credentials, options=channel_options)
        self.client_service_stub = client_service_pb2_grpc.ClientServiceStub(self.secure_channel)
        
        try:
            register_request = client_service_pb2.RegisterClientRequest(client_id=self.client_id, client_info="Python Client")
            response = await self.client_service_stub.RegisterClient(register_request, timeout=10)
            
            if response.success:
                logger.info(f"Client {self.client_id} connected and registered: {response.message}")
                return True
            else:
                logger.error(f"Failed to connect on secure channel: {response.message}")
                await self.secure_channel.close()
                return False

        except grpc.aio.AioRpcError as e:
            logger.error(f"Failed to connect on secure channel: {e.code()} - {e.details()}")
            await self.secure_channel.close()
            return False

    async def disconnect(self):
        """Closes the gRPC connection."""
        if self.secure_channel:
            await self.secure_channel.close()
            logger.info(f"Client {self.client_id} disconnected.")

    async def _handle_training_round(self):
        """Handles a single federated learning round."""
        logger.info(f"Client {self.client_id} starting a new training round.")
        
        try:
            current_preference = preferences.privacy_method
            if current_preference == "NONE":
                logger.info("Privacy method is NONE. Skipping training round.")
                return
                
            fetch_request = client_service_pb2.FetchModelRequest(client_id=self.client_id)
            model_response = await self.client_service_stub.FetchModel(fetch_request, timeout=30)
            
            if not model_response.success:
                logger.error(f"Failed to fetch global model: {model_response.message}")
                return
            
            global_model_state = deserialize_model_state(model_response.model_data)
            logger.info("Successfully fetched and deserialized the global model.")
            
            original_global_model_state = {key: val.clone() for key, val in global_model_state.items()}
            updated_model_state = self.client_model_manager.train_model(global_model_state)
            
            model_update = {
                key: updated_model_state[key] - original_global_model_state[key]
                for key in updated_model_state
            }
            
            if current_preference == "HE":
                logger.info("Using Homomorphic Encryption.")
                encrypted_updated_model_data = self.he_handler.encrypt_model_state(model_update)
                
                update_request = client_service_pb2.SendModelUpdateRequest(
                    client_id=self.client_id,
                    model_update=encrypted_updated_model_data,
                    privacy_method=current_preference
                )
                update_response = await self.client_service_stub.SendModelUpdate(update_request, timeout=60)
                if update_response.success:
                    logger.info("Successfully sent HE model update to the server.")
                else:
                    logger.error(f"Failed to send HE model update: {update_response.message}")
            
            elif current_preference == "SSS":
                logger.info("Using Secret Sharing.")
                share_bundles = self.sss_handler.split_model(model_update)
                
                client_to_drop = os.getenv("CLIENT_ID_TO_DROP")
                is_dropout_client = (client_to_drop == self.client_id)

                for i, bundle_data in enumerate(share_bundles):
                    update_request = client_service_pb2.SendModelUpdateSharesRequest(
                        client_id=self.client_id,
                        share_index=i,
                        total_shares=len(share_bundles),
                        share_data=bundle_data 
                    )
                    update_response = await self.client_service_stub.SendModelUpdateShares(update_request, timeout=60)
                    if update_response.success:
                        logger.info(f"Successfully sent share bundle {i+1}/{len(share_bundles)} to the server.")
                    else:
                        logger.error(f"Failed to send share bundle {i+1}/{len(share_bundles)}: {update_response.message}")

                    if is_dropout_client and i == (self.sss_handler.threshold - 1):
                        logger.warning(f"SIMULATING DROPOUT for client {self.client_id}. Exiting.")
                        sys.exit(0)
            
            elif current_preference == "Normal":
                logger.info("Using Normal (plaintext) update.")
                serialized_update = serialize_model_state(model_update)

                update_request = client_service_pb2.SendModelUpdateRequest(
                    client_id=self.client_id,
                    model_update=serialized_update,
                    privacy_method=current_preference
                )
                # **FIX**: Changed from 'SendModelUpdateNormal' to the correct 'SendModelUpdate'
                update_response = await self.client_service_stub.SendModelUpdate(update_request, timeout=60)
                if update_response.success:
                    logger.info("Successfully sent Normal model update to the server.")
                else:
                    logger.error(f"Failed to send Normal model update: {update_response.message}")
                
        except grpc.aio.AioRpcError as e:
            logger.error(f"RPC error during training round: {e.code()} - {e.details()}")
        except Exception:
            logger.exception(f"An unexpected error occurred during a training round.")

    async def run(self):
        """Main client loop for heartbeats and training."""
        is_connected = await self.connect()
        if not is_connected:
            logger.critical(f"Client {self.client_id} could not establish an initial connection. Exiting.")
            return

        logger.info(f"Client {self.client_id} running...")
        
        try:
            while True:
                heartbeat_request = client_service_pb2.HeartbeatRequest(client_id=self.client_id, timestamp=int(time.time()))
                try:
                    heartbeat_response = await self.client_service_stub.SendHeartbeat(heartbeat_request, timeout=30)
                    if heartbeat_response.success:
                        logger.debug(f"Heartbeat success. Server time: {heartbeat_response.server_timestamp}")
                        if heartbeat_response.new_round_available:
                            await self._handle_training_round()
                            logger.info("Training round completed. Resuming heartbeat cycle.")
                    else:
                        if "not recognized" in heartbeat_response.message:
                            logger.warning("Heartbeat failed: Client not recognized by server. Attempting to re-register.")
                            await self.disconnect()
                            if not await self.connect():
                                logger.error("Re-registration failed. Will retry after interval.")
                        else:
                            logger.warning(f"Heartbeat failed: {heartbeat_response.message}")

                except grpc.aio.AioRpcError as e:
                    logger.error(f"Heartbeat RPC failed: {e.code()}. Attempting to reconnect...")
                    await self.disconnect()
                    if not await self.connect():
                        logger.error("Reconnection failed. Will retry after interval.")
                
                await asyncio.sleep(HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Client run loop cancelled.")
        finally:
            await self.disconnect()

async def main():
    api_thread = threading.Thread(target=start_api_server, args=(API_PORT,), daemon=True)
    api_thread.start()
    logger.info(f"API server running on http://0.0.0.0:{API_PORT}")

    client_id = get_or_create_client_id()
    client = Client(client_id)
    await client.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client shutdown initiated by user.")
    except Exception:
        logger.critical("Client exited with an unhandled error:", exc_info=True)