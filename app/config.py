"""
==============================================================================
Module: app.config
Role in Architecture: Central Configuration & Environment Manager
==============================================================================
This module loads and validates all system settings from the environment or .env
file. Following the 12-factor app methodology, secrets (API keys) and configurable
hyperparameters (chunk size, retrieval threshold) are kept out of the source code.

Design Choice:
We use a centralized Settings class with fallback defaults. If an environment
variable is missing, sensible defaults are applied, and paths are automatically
converted to absolute paths to prevent Windows/Linux path resolution discrepancies.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the repository (parent of the app directory)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _resolve_path(raw: str | Path) -> Path:
    """Helper to convert any relative path into an absolute path anchored at PROJECT_ROOT."""
    p = Path(raw)
    if not p.is_absolute():
        return (PROJECT_ROOT / p).resolve()
    return p.resolve()

# Load .env file from project root if it exists
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    # Also attempt loading from default environment
    load_dotenv()


class Settings:
    """
    Centralized configuration container.
    Every setting is documented so students can easily adjust hyperparameters
    during testing and defend them during the final project review.
    """

    # --- Project Paths ---
    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = _resolve_path(os.getenv("DATA_DIR", "data/documents"))
    OUTPUTS_DIR: Path = _resolve_path(os.getenv("OUTPUTS_DIR", "outputs"))
    DB_DIR: Path = _resolve_path(os.getenv("DB_DIR", "db"))
    CHROMA_PERSIST_DIR: Path = _resolve_path(os.getenv("CHROMA_PERSIST_DIR", "db/chroma"))
    SQLITE_DB_PATH: Path = _resolve_path(os.getenv("SQLITE_DB_PATH", "db/assistant.db"))

    # --- LLM Provider Selection ---
    # Supported values: "gemini" (primary), "claude", "ollama"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    # Google Gemini Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

    # Anthropic Claude Settings
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # Ollama Local LLM Settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # --- RAG Hyperparameters ---
    # Minimum cosine similarity score required for a retrieved chunk to be considered relevant.
    # If no chunk meets this threshold, RAG Agent triggers a graceful refusal.
    RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.30"))
    # Number of top chunks to retrieve from ChromaDB
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))
    # Token chunk size and sliding window overlap
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "500"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
    # Sentence Transformer embedding model (384-dimensional, local CPU inference)
    EMBEDDING_MODEL_NAME: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # --- Student User Preferences ---
    USER_NAME: str = os.getenv("USER_NAME", "Alex")
    USER_DEFAULT_EMAIL: str = os.getenv("USER_DEFAULT_EMAIL", "alex.student@ktu.edu.in")
    DEFAULT_REMINDER_LEAD_HOURS: int = int(os.getenv("DEFAULT_REMINDER_LEAD_HOURS", "24"))

    # --- Email MCP Tool Configuration ---
    GMAIL_USER: str = os.getenv("GMAIL_USER", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required persistent data directories exist on disk."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DB_DIR.mkdir(parents=True, exist_ok=True)
        cls.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)


# Initialize directories immediately upon import
Settings.ensure_directories()

# Singleton settings instance for imports across the project
settings = Settings()
