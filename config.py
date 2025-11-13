import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from the .env file (if present).
load_dotenv()

# --- CRITICAL: Define the project's absolute root directory ---
# This gives us a 100% reliable anchor for finding files like templates.
BASE_DIR = Path(__file__).resolve().parent

# Helpful default for OUTPUT_DIR (can be overridden in .env)
DEFAULT_OUTPUT_DIR = str(Path.home() / "Desktop")

class Settings:
    """Centralized configuration for the entire project.

    Environment variables supported (see `.env.example`):
      - GOOGLE_API_KEY (required)
      - DEBUG (optional, true/false)
      - OUTPUT_DIR (optional)
    """
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", DEFAULT_OUTPUT_DIR)

    # Validate required settings and give a helpful error message
    if not GOOGLE_API_KEY:
        raise ValueError(
            "FATAL ERROR: GOOGLE_API_KEY is not set.\n"
            "Create a `.env` file (you can copy `.env.example`) and set GOOGLE_API_KEY=your_key"
        )


settings = Settings()