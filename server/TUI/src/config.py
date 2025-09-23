API_URL = "http://127.0.0.1:8080/api"

# Global data cache to reduce API calls
DATA_CACHE = {}
CACHE_LIFETIME = 2  # seconds

# Fixed and complete mapping from API names to friendly names and vice-versa
MODULE_NAME_MAPPING = {
    'mm': 'Model_Manager',
    'sam': 'Secure_Aggrigation_Module',
    'adrm': 'Attack_Defense_and_Resillence_Module',
    'ppm': 'Privacy_Preserving_Module',
    'scpm': 'Server_Communication_and_Protocol_Enforcement_Module',
    'orchestrator': 'Orchestrator' # ADDED
}

# Create a reverse mapping for easy lookup
FRIENDLY_NAME_MAPPING = {v: k for k, v in MODULE_NAME_MAPPING.items()}

