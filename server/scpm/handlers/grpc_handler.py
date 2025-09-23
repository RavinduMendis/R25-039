import grpc
import os
import ssl
import time
import hashlib
import logging
import datetime
import io
import torch
import json
from concurrent import futures
from typing import TYPE_CHECKING, Any, Dict, Union, List

# Imports for gRPC generated code
from scpm.protos import client_service_pb2
from scpm.protos import client_service_pb2_grpc

# Using the cryptography library for certificate handling
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.x509.base import load_der_x509_certificate, load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import CertificateBuilder, ExtendedKeyUsage, KeyUsage
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# Import the base handler for consistent logging
from scpm.handlers.base_handler import BaseCommunicationHandler
from log_manager.log_manager import ContextAdapter

if TYPE_CHECKING:
    from client_manager import ClientManager
    from scpm.scpm import ServerControlPlaneManager
    from orchestrator import Orchestrator


# Logger for the entire module
logger = logging.getLogger(__name__)

# Corrected path to the certifications directory
CERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "certifications")


class InsecureGreeterServicer(client_service_pb2_grpc.GreeterServicer):
    """
    gRPC service implementation for the insecure registration channel.
    This is specifically for the one-time registration handshake.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.logger = ContextAdapter(logging.getLogger(self.__class__.__name__), {"component": self.__class__.__name__})
        self.ca_cert = None
        self.ca_private_key = None
        self._load_ca_credentials()
        self.logger.info("gRPC InsecureGreeterServicer initialized.")

    def _load_ca_credentials(self):
        """Loads the CA certificate and private key for signing client certificates."""
        try:
            with open(os.path.join(CERTS_DIR, 'ca.crt'), 'rb') as f:
                ca_cert_pem = f.read()
            with open(os.path.join(CERTS_DIR, 'ca.key'), 'rb') as f:
                ca_key_pem = f.read()

            self.ca_cert = load_pem_x509_certificate(ca_cert_pem, default_backend())
            self.ca_private_key = load_pem_private_key(ca_key_pem, password=None, backend=default_backend())
            self.logger.info("CA credentials loaded successfully for signing.")
        except FileNotFoundError as e:
            self.logger.critical(f"CA certificate or key file not found: {e}. Cannot sign client certificates.")
            raise
        except Exception as e:
            self.logger.critical(f"An error occurred loading CA credentials: {e}", exc_info=True)
            raise

    async def RegisterClient(self, request: client_service_pb2.ClientRegistrationRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.ClientRegistrationResponse:
        """
        Handles client registration on the insecure channel.
        Signs the client's Certificate Signing Request (CSR) and returns the signed certificate.
        """
        self.logger.info(f"Received registration request from client '{request.client_id}' on insecure channel.")
        if request.registration_token != 'secure-one-time-token':
            self.logger.warning(f"Registration request from '{request.client_id}' with invalid token.")
            return client_service_pb2.ClientRegistrationResponse(
                success=False,
                message="Invalid registration token."
            )

        try:
            csr = x509.load_pem_x509_csr(request.certificate_signing_request, default_backend())

            common_name = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            if common_name != request.client_id:
                self.logger.error(f"CSR Common Name '{common_name}' does not match client_id '{request.client_id}'.")
                return client_service_pb2.ClientRegistrationResponse(
                    success=False,
                    message="CSR Common Name mismatch."
                )

            if not csr.is_signature_valid:
                self.logger.error(f"Invalid signature on CSR from client '{request.client_id}'.")
                return client_service_pb2.ClientRegistrationResponse(
                    success=False,
                    message="Invalid CSR signature."
                )

            builder = x509.CertificateBuilder().subject_name(
                csr.subject
            ).issuer_name(
                self.ca_cert.subject
            ).public_key(
                csr.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.utcnow()
            ).not_valid_after(
                datetime.datetime.utcnow() + datetime.timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName(request.client_id),
                ]),
                critical=False,
            ).add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True, content_commitment=False, key_encipherment=True,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False,
                    crl_sign=False, encipher_only=False, decipher_only=False
                ), critical=True
            )

            signed_certificate = builder.sign(
                private_key=self.ca_private_key, algorithm=hashes.SHA256(), backend=default_backend()
            )

            signed_cert_pem = signed_certificate.public_bytes(serialization.Encoding.PEM)
            ca_cert_pem = self.ca_cert.public_bytes(serialization.Encoding.PEM)
            self.logger.info(f"Successfully signed certificate for client '{request.client_id}'.")
            
            return client_service_pb2.ClientRegistrationResponse(
                success=True,
                message="Registration successful. Signed certificate issued.",
                signed_certificate=signed_cert_pem,
                ca_certificate=ca_cert_pem
            )
        except Exception as e:
            self.logger.error(f"Error during insecure registration for client '{request.client_id}': {e}", exc_info=True)
            return client_service_pb2.ClientRegistrationResponse(
                success=False,
                message=f"Server error during registration: {str(e)}"
            )


class ClientServicer(client_service_pb2_grpc.ClientServiceServicer):
    """
    gRPC service implementation for client-server communication on the secure channel.
    This handles all ongoing communication like heartbeats and model updates.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager', orchestrator: 'Orchestrator'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.orchestrator = orchestrator
        self.logger = ContextAdapter(logging.getLogger(self.__class__.__name__), {"component": self.__class__.__name__})
        self.logger.info("gRPC ClientServicer initialized.")

    def _extract_cn_from_cert(self, context: grpc.aio.ServicerContext) -> Union[str, None]:
        """Extracts the Common Name (CN) from the peer's certificate."""
        try:
            auth_context = context.auth_context()
            if 'x509_common_name' in auth_context:
                cn = auth_context['x509_common_name'][0]
                if isinstance(cn, bytes):
                    cn = cn.decode('utf-8')
                self.logger.debug(f"Successfully extracted CN from auth context: {cn}")
                return cn
            
            self.logger.error("Could not find Common Name in gRPC auth context.")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to extract Common Name from certificate: {e}", exc_info=True)
            return None

    async def RegisterClient(self, request: client_service_pb2.RegisterClientRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.RegisterClientResponse:
        """Handles client registration on the secure channel after mTLS authentication."""
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.RegisterClientResponse(success=False, message="Could not determine client ID from certificate.")

        if client_id != request.client_id:
            self.logger.error(f"Certificate CN '{client_id}' does not match requested client ID '{request.client_id}'.")
            return client_service_pb2.RegisterClientResponse(success=False, message="Client ID mismatch.")

        try:
            peer_info = context.peer()
            ip_address = peer_info.split(':')[1] if peer_info.startswith("ipv4:") else "unknown"
            
            await self.client_manager.add_or_update_client(client_id, ip_address, "gRPC")
            self.logger.info(f"Client '{client_id}' successfully registered with ClientManager via secure channel.")
            return client_service_pb2.RegisterClientResponse(success=True, message="Client successfully registered via mTLS.")
        except Exception as e:
            self.logger.error(f"Error registering client '{client_id}' with ClientManager: {e}", exc_info=True)
            return client_service_pb2.RegisterClientResponse(success=False, message=f"Registration error: {str(e)}")

    async def SendHeartbeat(self, request: client_service_pb2.HeartbeatRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.HeartbeatResponse:
        """Handles a heartbeat message from a client."""
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.HeartbeatResponse(success=False, message="Client ID could not be determined from certificate.")

        if not await self.client_manager.update_client_heartbeat(client_id):
            return client_service_pb2.HeartbeatResponse(success=False, message="Client ID not recognized.")

        self.logger.debug(f"Received heartbeat from client '{client_id}'.")
        
        new_round_available = self.orchestrator.is_client_in_current_round(client_id)
        
        self.scpm.update_client_count(self.client_manager.get_connected_clients_count())
        
        return client_service_pb2.HeartbeatResponse(
            success=True, 
            server_timestamp=int(time.time()), 
            message="Heartbeat received.",
            new_round_available=new_round_available
        )

    async def FetchModel(self, request: client_service_pb2.FetchModelRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.FetchModelResponse:
        """Provides the latest global model to a client."""
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.FetchModelResponse(success=False, message="Could not determine client ID from certificate.")

        if not self.orchestrator.is_client_in_current_round(client_id):
            return client_service_pb2.FetchModelResponse(
                success=False,
                message="Client not selected for the current training round."
            )

        try:
            model_bytes = self.orchestrator.prepare_model_for_client(client_id)
            
            return client_service_pb2.FetchModelResponse(
                success=True,
                model_data=model_bytes,
                message="Global model fetched successfully."
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch global model for client '{client_id}': {e}", exc_info=True)
            return client_service_pb2.FetchModelResponse(
                success=False,
                message="Internal server error."
            )

    # <<< THIS ENTIRE METHOD IS THE FIX >>>
    async def SendModelUpdate(self, request: client_service_pb2.SendModelUpdateRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.SendModelUpdateResponse:
        """
        Receives a model update from a client and routes it based on the privacy method.
        This single RPC handles both HE and Normal updates.
        """
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.SendModelUpdateResponse(success=False, message="Could not determine client ID from certificate.")

        privacy_method = request.privacy_method
        model_update_data = request.model_update
        
        self.logger.info(f"Received model update from '{client_id}' with declared method: '{privacy_method}'.")

        try:
            if privacy_method == "HE":
                await self.orchestrator.receive_he_update(client_id, model_update_data)
                self.logger.info(f"HE update from '{client_id}' forwarded to orchestrator.")
                return client_service_pb2.SendModelUpdateResponse(success=True, message="HE update received.")

            elif privacy_method == "Normal":
                # Ensure you have a 'receive_normal_update' method in your Orchestrator class
                await self.orchestrator.receive_normal_update(client_id, model_update_data)
                self.logger.info(f"Normal update from '{client_id}' forwarded to orchestrator.")
                return client_service_pb2.SendModelUpdateResponse(success=True, message="Normal update received.")
            
            else:
                self.logger.error(f"Received update from '{client_id}' with unknown or missing privacy method: '{privacy_method}'.")
                return client_service_pb2.SendModelUpdateResponse(
                    success=False, 
                    message=f"Unknown privacy method: '{privacy_method}'"
                )
        except Exception as e:
            self.logger.error(f"Failed to process update from '{client_id}' with method '{privacy_method}': {e}", exc_info=True)
            return client_service_pb2.SendModelUpdateResponse(success=False, message="Internal server error while processing update.")

    async def SendModelUpdateShares(self, request: client_service_pb2.SendModelUpdateSharesRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.SendModelUpdateSharesResponse:
        """Receives a single Secret Sharing share from a client."""
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.SendModelUpdateSharesResponse(success=False, message="Could not determine client ID from certificate.")
        if not self.orchestrator.is_client_in_current_round(client_id):
            return client_service_pb2.SendModelUpdateSharesResponse(
                success=False,
                message="Client not part of the current training round."
            )
        try:
            await self.orchestrator.receive_sss_share(
                client_id=client_id,
                share_index=request.share_index,
                share_data=request.share_data,
                total_shares=request.total_shares
            )
            
            self.logger.info(f"Received SSS share {request.share_index + 1}/{request.total_shares} from client '{client_id}'.")
            
            return client_service_pb2.SendModelUpdateSharesResponse(
                success=True,
                message="Secret sharing share received successfully."
            )
        except Exception as e:
            self.logger.error(f"Failed to process SSS share from client '{client_id}': {e}", exc_info=True)
            return client_service_pb2.SendModelUpdateSharesResponse(
                success=False,
                message="Internal server error while processing share."
            )


class GrpcHandler(BaseCommunicationHandler):
    """Manages the gRPC server instances."""
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager', orchestrator: 'Orchestrator'):
        super().__init__(client_manager, scpm)
        self.orchestrator = orchestrator
        self.client_servicer = ClientServicer(client_manager, scpm, self.orchestrator)
        self.insecure_greeter_servicer = InsecureGreeterServicer(client_manager, scpm)
        self.secure_server = None
        self.insecure_server = None
        self.logger.info("GrpcHandler initialized.")

    async def start_listener(self):
        """Starts both the insecure and secure gRPC servers."""
        self.logger.info("Starting gRPC listeners...")
        try:
            root_certificates, server_certificate, server_private_key = self._load_server_credentials()

            server_credentials = grpc.ssl_server_credentials(
                private_key_certificate_chain_pairs=[(server_private_key, server_certificate)],
                root_certificates=root_certificates,
                require_client_auth=True
            )

            self.secure_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
            client_service_pb2_grpc.add_ClientServiceServicer_to_server(self.client_servicer, self.secure_server)
            self.secure_server.add_secure_port('[::]:50051', server_credentials)
            self.logger.info("Secure gRPC server configured on port 50051 with mTLS.")

            self.insecure_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
            client_service_pb2_grpc.add_GreeterServicer_to_server(self.insecure_greeter_servicer, self.insecure_server)
            self.insecure_server.add_insecure_port('[::]:50052')
            self.logger.info("Insecure gRPC server for registration configured on port 50052.")
            
            await self.insecure_server.start()
            await self.secure_server.start()
            self.logger.info("Both gRPC servers are running.")

            await self.insecure_server.wait_for_termination()
            await self.secure_server.wait_for_termination()
        except Exception as e:
            self.logger.critical(f"An error occurred during gRPC server startup: {e}", exc_info=True)
            await self.stop_listener()
            raise

    def _load_server_credentials(self) -> tuple[bytes, bytes, bytes]:
        """Loads the CA, server cert, and server key for mTLS."""
        try:
            with open(os.path.join(CERTS_DIR, 'ca.crt'), 'rb') as f: root_certificates = f.read()
            with open(os.path.join(CERTS_DIR, 'server.crt'), 'rb') as f: server_certificate = f.read()
            with open(os.path.join(CERTS_DIR, 'server.key'), 'rb') as f: server_private_key = f.read()
            self.logger.info("gRPC server credentials loaded.")
            return root_certificates, server_certificate, server_private_key
        except FileNotFoundError as e:
            self.logger.critical(f"gRPC server certificate file not found: {e}. Ensure certs are in '{CERTS_DIR}'.")
            raise

    async def stop_listener(self):
        """Stops the gRPC servers gracefully."""
        self.logger.info("Stopping gRPC servers...")
        if self.insecure_server:
            await self.insecure_server.stop(5)
            self.logger.info("Insecure gRPC server stopped.")
        if self.secure_server:
            await self.secure_server.stop(5)
            self.logger.info("Secure gRPC server stopped.")