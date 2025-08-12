# server/scpm/handlers/grpc_handler.py

import grpc
import os
import ssl
import time
import hashlib
import logging
import datetime
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

if TYPE_CHECKING:
    from client_manager import ClientManager
    from scpm.scpm import ServerControlPlaneManager
    from orchestrator import Orchestrator


# Logger for the entire module
logger = logging.getLogger(__name__)

# Corrected path to the certifications directory
# This path now correctly navigates from 'server/scpm/handlers' up one level to 'scpm'
# and then down into the 'certifications' directory.
CERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "certifications")


class InsecureGreeterServicer(client_service_pb2_grpc.GreeterServicer):
    """
    gRPC service implementation for the insecure registration channel.
    This is specifically for the one-time registration handshake.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.ca_cert = None
        self.ca_private_key = None
        self._load_ca_credentials()
        logger.info("gRPC InsecureGreeterServicer initialized.")

    def _load_ca_credentials(self):
        """Loads the CA certificate and private key for signing client certificates."""
        try:
            with open(os.path.join(CERTS_DIR, 'ca.crt'), 'rb') as f:
                ca_cert_pem = f.read()
            with open(os.path.join(CERTS_DIR, 'ca.key'), 'rb') as f:
                ca_key_pem = f.read()

            self.ca_cert = load_pem_x509_certificate(ca_cert_pem, default_backend())
            self.ca_private_key = load_pem_private_key(ca_key_pem, password=None, backend=default_backend())
            logger.info("CA credentials loaded successfully for signing.")
        except FileNotFoundError as e:
            logger.critical(f"CA certificate or key file not found: {e}. Cannot sign client certificates.")
            raise
        except Exception as e:
            logger.critical(f"An error occurred loading CA credentials: {e}", exc_info=True)
            raise

    async def RegisterClient(self, request: client_service_pb2.ClientRegistrationRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.ClientRegistrationResponse:
        """
        Handles client registration on the insecure channel.
        Signs the client's Certificate Signing Request (CSR) and returns the signed certificate.
        """
        logger.info(f"Received registration request from client '{request.client_id}' on insecure channel.")
        if request.registration_token != 'secure-one-time-token':
            logger.warning(f"Registration request from '{request.client_id}' with invalid token.")
            return client_service_pb2.ClientRegistrationResponse(
                success=False,
                message="Invalid registration token."
            )

        try:
            csr = x509.load_pem_x509_csr(request.certificate_signing_request, default_backend())

            # Check if the CSR's common name matches the provided client_id
            common_name = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            if common_name != request.client_id:
                logger.error(f"CSR Common Name '{common_name}' does not match client_id '{request.client_id}'.")
                return client_service_pb2.ClientRegistrationResponse(
                    success=False,
                    message="CSR Common Name mismatch."
                )

            if not csr.is_signature_valid:
                logger.error(f"Invalid signature on CSR from client '{request.client_id}'.")
                return client_service_pb2.ClientRegistrationResponse(
                    success=False,
                    message="Invalid CSR signature."
                )

            # Generate the signed certificate with proper extensions
            builder = x509.CertificateBuilder()
            builder = builder.subject_name(csr.subject)
            builder = builder.issuer_name(self.ca_cert.subject)
            builder = builder.public_key(csr.public_key())
            builder = builder.serial_number(x509.random_serial_number())
            builder = builder.not_valid_before(datetime.datetime.utcnow())
            builder = builder.not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            
            # Add SubjectAlternativeName extension
            builder = builder.add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName(request.client_id),
                ]),
                critical=False,
            )
            
            # Add Extended Key Usage for client authentication
            builder = builder.add_extension(x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.CLIENT_AUTH
            ]), critical=True)  # Make this critical
            
            # Add proper Key Usage
            builder = builder.add_extension(x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ), critical=True)  # Make this critical

            signed_certificate = builder.sign(
                private_key=self.ca_private_key,
                algorithm=hashes.SHA256(),
                backend=default_backend()
            )

            signed_cert_pem = signed_certificate.public_bytes(serialization.Encoding.PEM)
            ca_cert_pem = self.ca_cert.public_bytes(serialization.Encoding.PEM) # Get the CA cert PEM
            logger.info(f"Successfully signed certificate for client '{request.client_id}' with SAN extension.")
            
            return client_service_pb2.ClientRegistrationResponse(
                success=True,
                message="Registration successful. Signed certificate issued.",
                signed_certificate=signed_cert_pem,
                ca_certificate=ca_cert_pem # <--- ADDED THIS LINE
            )
        except Exception as e:
            logger.error(f"Error during insecure registration for client '{request.client_id}': {e}", exc_info=True)
            return client_service_pb2.ClientRegistrationResponse(
                success=False,
                message=f"Server error during registration: {str(e)}"
            )


class ClientServicer(client_service_pb2_grpc.ClientServiceServicer):
    """
    gRPC service implementation for client-server communication on the secure channel.
    This handles all ongoing communication like heartbeats.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager', orchestrator: 'Orchestrator'):
        self.client_manager = client_manager
        self.scpm = scpm
        self.orchestrator = orchestrator # Added orchestrator
        self.ca_cert = None
        self.ca_private_key = None
        self._load_ca_credentials()
        logger.info("gRPC ClientServicer initialized.")

    def _load_ca_credentials(self):
        """Loads the CA certificate and private key from the certifications directory."""
        try:
            with open(os.path.join(CERTS_DIR, 'ca.crt'), 'rb') as f:
                ca_cert_pem = f.read()
            with open(os.path.join(CERTS_DIR, 'ca.key'), 'rb') as f:
                ca_key_pem = f.read()

            self.ca_cert = load_pem_x509_certificate(ca_cert_pem, default_backend())
            self.ca_private_key = load_pem_private_key(ca_key_pem, password=None, backend=default_backend())

            logger.info("CA certificate and private key loaded successfully for client registration.")

        except FileNotFoundError as e:
            logger.critical(f"CA certificate or key file not found: {e}. Cannot sign client certificates.")
            raise
        except Exception as e:
            logger.critical(f"An error occurred loading CA credentials: {e}", exc_info=True)
            raise

    def _extract_cn_from_cert(self, context: grpc.aio.ServicerContext) -> Union[str, None]:
        """
        Extracts the Common Name (CN) from the peer's leaf certificate from the gRPC context.
        Enhanced version with better error handling and debugging.
        """
        try:
            # Access the certificate data from the auth_context
            auth_context = context.auth_context()
            
            # Debug: Print all available auth context keys
            logger.debug(f"Auth context keys: {list(auth_context.keys())}")
            
            # Try to get the PEM certificate directly
            peer_cert_pem = auth_context.get('x509_pem_cert')
            if peer_cert_pem:
                # The PEM certificate is already in string format
                cert_pem_str = peer_cert_pem[0] if isinstance(peer_cert_pem, list) else peer_cert_pem
                if isinstance(cert_pem_str, bytes):
                    cert_pem_str = cert_pem_str.decode('utf-8')
                
                client_cert = x509.load_pem_x509_certificate(cert_pem_str.encode('utf-8'), default_backend())
                
                # Extract the common name
                common_name_attrs = client_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                if common_name_attrs:
                    cn = common_name_attrs[0].value
                    logger.debug(f"Successfully extracted CN from PEM cert: {cn}")
                    return cn
                else:
                    logger.error("No Common Name found in client certificate")
                    return None
            
            # Fallback: Try binary certificate format
            peer_certs_bin = auth_context.get('x509_certificate_bin')
            if not peer_certs_bin:
                # Try alternative key names
                peer_certs_bin = auth_context.get('x509_certificate')
                if not peer_certs_bin:
                    peer_certs_bin = auth_context.get('certificate')
                    
            if peer_certs_bin:
                # The certificate is the first item in the list of binary data
                client_cert_der = peer_certs_bin[0]
                client_cert = load_der_x509_certificate(client_cert_der, default_backend())

                # Extract the common name
                common_name_attrs = client_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                if common_name_attrs:
                    cn = common_name_attrs[0].value
                    logger.debug(f"Successfully extracted CN from DER cert: {cn}")
                    return cn
                else:
                    logger.error("No Common Name found in client certificate")
                    return None
            
            # If we still don't have the certificate, try the common name directly
            x509_common_name = auth_context.get('x509_common_name')
            if x509_common_name:
                cn = x509_common_name[0] if isinstance(x509_common_name, list) else x509_common_name
                if isinstance(cn, bytes):
                    cn = cn.decode('utf-8')
                logger.debug(f"Successfully extracted CN directly from auth context: {cn}")
                return cn
            
            logger.error("No peer certificates or common name found in gRPC context's auth_context. Available keys: %s", list(auth_context.keys()))
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract Common Name from certificate: {e}", exc_info=True)
            return None

    async def RegisterClient(self, request: client_service_pb2.RegisterClientRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.RegisterClientResponse:
        """
        Handles client registration on the secure channel.
        This method is called after the client has been authenticated via mTLS.
        """
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.RegisterClientResponse(success=False, message="Could not determine client ID from certificate.")

        # Check if the ID from the cert matches the ID in the request
        if client_id != request.client_id:
            logger.error(f"Certificate CN '{client_id}' does not match requested client ID '{request.client_id}'.")
            return client_service_pb2.RegisterClientResponse(success=False, message="Client ID mismatch.")

        # The client is already authenticated by the mTLS handshake.
        # Now we just register it in the client manager using the correct method.
        try:
            # Extract IP address from the peer string (format: "ipv4:127.0.0.1:port" or "ipv6:[::1]:port")
            peer_info = context.peer()
            ip_address = "unknown"
            if peer_info:
                # Parse the peer string to extract IP address
                if peer_info.startswith("ipv4:"):
                    ip_address = peer_info.split(":")[1]
                elif peer_info.startswith("ipv6:"):
                    # For IPv6, the format is "ipv6:[address]:port"
                    ip_address = peer_info.split("]:")[0].replace("ipv6:[", "")
                else:
                    ip_address = peer_info
            
            # Use the correct method name from ClientManager
            self.client_manager.add_or_update_client(client_id, ip_address, "gRPC")
            logger.info(f"Client '{client_id}' successfully registered with ClientManager via secure channel.")
            return client_service_pb2.RegisterClientResponse(success=True, message="Client successfully registered via mTLS.")
        except Exception as e:
            logger.error(f"Error registering client '{client_id}' with ClientManager: {e}", exc_info=True)
            return client_service_pb2.RegisterClientResponse(success=False, message=f"Registration error: {str(e)}")


    async def SendHeartbeat(self, request: client_service_pb2.HeartbeatRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.HeartbeatResponse:
        """
        Handles a heartbeat message from a client on the secure channel,
        using the client ID extracted from the certificate for security.
        """
        # The client ID should be extracted from the authenticated certificate, not the request.
        # This prevents a client from spoofing another client's ID.
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            logger.error("Heartbeat received on secure channel without a valid client certificate.")
            return client_service_pb2.HeartbeatResponse(success=False, message="Client ID could not be determined from certificate.")

        # Update the client's heartbeat timestamp
        if not self.client_manager.update_client_heartbeat(client_id):
            logger.warning(f"Heartbeat received from unknown client ID '{client_id}'.")
            return client_service_pb2.HeartbeatResponse(success=False, message="Client ID not recognized.")

        logger.debug(f"Received heartbeat from client '{client_id}'.")
        
        # FIXED: Check if a new training round is available for this client
        # Calls the new method on the orchestrator to check if the client is selected
        new_round_available = self.orchestrator.is_client_in_current_round(client_id)
        
        # Update client count in SCPM for monitoring
        self.scpm.update_client_count(len(self.client_manager.get_connected_clients_ids()))
        
        return client_service_pb2.HeartbeatResponse(
            success=True, 
            server_timestamp=int(time.time()), 
            message="Heartbeat received.",
            new_round_available=new_round_available  # This flag tells the client to start training
        )

    async def FetchModel(self, request: client_service_pb2.FetchModelRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.FetchModelResponse:
        """
        Provides the latest global model to a client if they are selected for the current round.
        """
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.FetchModelResponse(success=False, message="Could not determine client ID from certificate.")

        if not self.orchestrator.is_client_in_current_round(client_id):
            return client_service_pb2.FetchModelResponse(
                success=False,
                message="Client not selected for the current training round."
            )

        try:
            # FIXED: Call the correct method on the Orchestrator to get the model data.
            global_model_data = self.orchestrator.prepare_model_for_client(client_id)
            logger.info(f"Provided global model to client '{client_id}'.")
            return client_service_pb2.FetchModelResponse(
                success=True,
                model_data=global_model_data,
                message="Global model fetched successfully."
            )
        except Exception as e:
            logger.error(f"Failed to fetch global model for client '{client_id}': {e}", exc_info=True)
            return client_service_pb2.FetchModelResponse(
                success=False,
                message="Internal server error."
            )

    async def SendModelUpdate(self, request: client_service_pb2.SendModelUpdateRequest, context: grpc.aio.ServicerContext) -> client_service_pb2.SendModelUpdateResponse:
        """
        Receives model updates from a client and forwards them to the Orchestrator.
        """
        client_id = self._extract_cn_from_cert(context)
        if not client_id:
            return client_service_pb2.SendModelUpdateResponse(success=False, message="Could not determine client ID from certificate.")
        
        if not self.orchestrator.is_client_in_current_round(client_id):
            return client_service_pb2.SendModelUpdateResponse(
                success=False,
                message="Client not part of the current training round."
            )

        try:
            # FIXED: Use the orchestrator's receive_client_update method instead of directly queuing
            # This ensures proper deserialization, validation, and anomaly detection
            await self.orchestrator.receive_client_update(client_id, request.model_update)
            
            logger.info(f"Received model update from client '{client_id}' and forwarded to orchestrator.")
            self.scpm.update_updates_in_queue(self.orchestrator.update_queue.qsize())
            
            return client_service_pb2.SendModelUpdateResponse(
                success=True,
                message="Model update received."
            )
        except Exception as e:
            logger.error(f"Failed to process model update from client '{client_id}': {e}", exc_info=True)
            return client_service_pb2.SendModelUpdateResponse(
                success=False,
                message="Internal server error."
            )


class GrpcHandler(BaseCommunicationHandler):
    """
    Manages the gRPC server instances for both insecure registration and secure communication.
    """
    def __init__(self, client_manager: 'ClientManager', scpm: 'ServerControlPlaneManager', orchestrator: 'Orchestrator'):
        super().__init__(client_manager, scpm)
        self.orchestrator = orchestrator
        self.client_servicer = ClientServicer(client_manager, scpm, self.orchestrator)
        self.insecure_greeter_servicer = InsecureGreeterServicer(client_manager, scpm) # New servicer for insecure channel
        self.secure_server = None
        self.insecure_server = None
        self.logger.info("GrpcHandler initialized.")


    async def start_listener(self):
        """Starts both the insecure and secure gRPC servers."""
        self.logger.info("Starting gRPC listeners...")
        try:
            # Load server credentials for the secure server
            root_certificates, server_certificate, server_private_key = self._load_server_credentials()

            server_credentials = grpc.ssl_server_credentials(
                private_key_certificate_chain_pairs=[(server_private_key, server_certificate)],
                root_certificates=root_certificates,
                require_client_auth=True
            )
            self.logger.info("gRPC server credentials loaded for secure port.")

            # Create and start the SECURE server
            self.secure_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
            client_service_pb2_grpc.add_ClientServiceServicer_to_server(self.client_servicer, self.secure_server)
            secure_listen_addr = '[::]:50051'
            
            # Wrap the port binding in a try-except to catch AddressInUseError
            try:
                self.secure_server.add_secure_port(secure_listen_addr, server_credentials)
                self.logger.info(f"Secure gRPC server created on secure port {secure_listen_addr} with mTLS.")
            except Exception as e:
                self.logger.critical(f"Failed to bind to secure port {secure_listen_addr}: {e}", exc_info=True)
                raise # Re-raise to stop the listener from continuing to start

            # Create and start the INSECURE server for initial registration only
            self.insecure_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
            client_service_pb2_grpc.add_GreeterServicer_to_server(self.insecure_greeter_servicer, self.insecure_server)
            insecure_listen_addr = '[::]:50052'
            
            try:
                self.insecure_server.add_insecure_port(insecure_listen_addr)
                self.logger.info(f"Insecure gRPC server created on port {insecure_listen_addr} for initial registration.")
            except Exception as e:
                self.logger.critical(f"Failed to bind to insecure port {insecure_listen_addr}: {e}", exc_info=True)
                # Note: We don't re-raise here to allow the secure server to still be started
            
            # Start both servers
            self.logger.info("Starting gRPC server tasks...")
            await self.insecure_server.start()
            await self.secure_server.start()
            self.logger.info("Both gRPC servers are running.")

            # Keep the servers running until termination
            await self.insecure_server.wait_for_termination()
            await self.secure_server.wait_for_termination()

        except Exception as e:
            self.logger.critical(f"An error occurred during gRPC server startup: {e}", exc_info=True)
            # Stop any servers that might have started before the failure
            await self.stop_listener()
            raise


    def _load_server_credentials(self) -> tuple[bytes, bytes, bytes]:
        """Loads the CA, server cert, and server key for mTLS."""
        certs_dir = os.path.join(CERTS_DIR)
        try:
            with open(os.path.join(certs_dir, 'ca.crt'), 'rb') as f:
                root_certificates = f.read()
            with open(os.path.join(certs_dir, 'server.crt'), 'rb') as f:
                server_certificate = f.read()
            with open(os.path.join(certs_dir, 'server.key'), 'rb') as f:
                server_private_key = f.read()
            self.logger.info("gRPC server credentials files loaded.")
            return root_certificates, server_certificate, server_private_key
        except FileNotFoundError as e:
            self.logger.critical(f"gRPC server certificate file not found: {e}. Ensure 'ca.crt', 'server.crt', 'server.key' are in '{certs_dir}'.")
            raise
        except Exception as e:
            self.logger.critical(f"An unexpected error occurred loading gRPC credentials: {e}")
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
        self.logger.info("All gRPC servers have been shut down.")