import subprocess

def generate_private_key(key_name):
    """Generate a private RSA key for the client."""
    command = ["openssl", "genpkey", "-algorithm", "RSA", "-out", key_name]
    subprocess.run(command, check=True)
    print(f"Private key generated: {key_name}")

def generate_self_signed_certificate(key_name, cert_name, subject):
    """Generate a self-signed certificate using the private key for the client."""
    command = [
        "openssl", "req", "-new", "-x509", "-key", key_name, 
        "-out", cert_name, "-days", "365", "-subj", subject
    ]
    subprocess.run(command, check=True)
    print(f"Self-signed certificate generated: {cert_name}")

if __name__ == "__main__":
    # Step 1: Generate the client private key
    generate_private_key("client_key.pem")
    
    # Step 2: Generate the client self-signed certificate
    generate_self_signed_certificate("client_key.pem", "client_cert.pem", "/CN=client")
