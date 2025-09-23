# api_handler.py

from fastapi import FastAPI
from pydantic import BaseModel
import logging
from typing import Literal

app = FastAPI()
logger = logging.getLogger(__name__)

# A simple in-memory store for the client's preference.
class PrivacyPreferences:
    def __init__(self):
        # FIX: Default to "NONE" to wait for user selection via the TUI.
        self.privacy_method: Literal["HE", "SSS", "Normal", "NONE"] = "NONE"

    def set_method(self, method: Literal["HE", "SSS", "Normal"]):
        self.privacy_method = method
        logger.info(f"Privacy method set to: {self.privacy_method}")

preferences = PrivacyPreferences()

class Preference(BaseModel):
    # FIX: Add "Normal" to the list of allowed methods for the API endpoint.
    method: Literal["HE", "SSS", "Normal"]

@app.post("/set_privacy_preference")
def set_privacy_preference(preference: Preference):
    """
    API endpoint to set the client's preferred privacy method.
    The method can be 'HE', 'SSS', or 'Normal'.
    """
    try:
        preferences.set_method(preference.method)
        return {"status": "success", "message": f"Privacy method updated to {preference.method}"}
    except Exception as e:
        logger.error(f"Failed to set privacy preference: {e}")
        return {"status": "error", "message": "Failed to update preference."}

@app.get("/get_privacy_preference")
def get_privacy_preference():
    """
    API endpoint to retrieve the current privacy method.
    """
    return {"status": "success", "method": preferences.privacy_method}