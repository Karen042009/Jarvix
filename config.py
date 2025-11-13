import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from the .env file.
load_dotenv()

# --- CRITICAL: Define the project's absolute root directory ---
# This gives us a 100% reliable anchor for finding files like templates.
BASE_DIR = Path(__file__).resolve().parent

class Settings:
    """Centralized configuration for the entire project."""
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY")

    if not GOOGLE_API_KEY:
        raise ValueError("FATAL ERROR: GOOGLE_API_KEY is not set in the .env file.")

settings = Settings()