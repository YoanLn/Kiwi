from pydantic_settings import BaseSettings
from typing import List, Optional
from dotenv import load_dotenv
from pathlib import Path
import os

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


class Settings(BaseSettings):
    # Project
    PROJECT_NAME: str = "LunatiX Insurance Platform"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # Google Cloud
    GOOGLE_CLOUD_PROJECT: str = ""
    VERTEX_AI_LOCATION: str = "europe-west1"  # EU region for Vertex AI
    GCS_BUCKET_NAME: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # Database
    DATABASE_URL: str = "sqlite:///./insurance.db"

    # Security
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    # Vertex AI Models - Using EU endpoints
    VERTEX_AI_MODEL_VISION: str = "gemini-2.5-flash"
    VERTEX_AI_MODEL_TEXT: str = "gemini-2.5-flash"
    VERTEX_AI_EMBEDDING_MODEL: str = "text-embedding-004"

    # Gemini API (Google AI Studio) for Live voice
    GEMINI_API_KEY: str = ""
    GEMINI_LIVE_MODEL: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    VERTEX_AI_LIVE_MODEL: str = ""  # Deprecated fallback for older envs

    # Vertex AI Search Configuration (EU multi-region for data residency)
    VERTEX_AI_SEARCH_LOCATION: str = "eu"  # EU multi-region for data residency
    VERTEX_AI_SEARCH_DATASTORE_ID: str = ""  # Set via env var
    VERTEX_AI_SEARCH_ENGINE_ID: str = ""  # Set via env var

    # Feature flags for Vertex AI Search
    ENABLE_VERTEX_SEARCH: bool = True  # Toggle to enable/disable Vertex AI Search
    ENABLE_DOCUMENT_INDEXING: bool = True  # Toggle to enable/disable auto-indexing

    # Demo mode (relaxes auth and verification for local demos)
    DEMO_MODE: bool = False
    DEMO_USER_ID: str = "demo-user"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Ensure Google client libraries can discover ADC in local dev.
if settings.GOOGLE_APPLICATION_CREDENTIALS:
    os.environ.setdefault(
        "GOOGLE_APPLICATION_CREDENTIALS",
        settings.GOOGLE_APPLICATION_CREDENTIALS,
    )
if settings.GOOGLE_CLOUD_PROJECT:
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.GOOGLE_CLOUD_PROJECT)
