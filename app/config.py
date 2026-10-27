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

def _get_config_value(key: str, default: str = "") -> str:
    """Retrieves configuration from environment variables or streamlit.secrets with fallback."""
    val = os.getenv(key)
    if val is not None and str(val).strip():
        return str(val).strip()

    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None:
            if key in st.secrets:
                return str(st.secrets[key]).strip()
            if key.lower() in st.secrets:
                return str(st.secrets[key.lower()]).strip()
    except Exception:
        pass

    return default

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
    DATA_DIR: Path = _resolve_path(_get_config_value("DATA_DIR", "data/documents"))
    OUTPUTS_DIR: Path = _resolve_path(_get_config_value("OUTPUTS_DIR", "outputs"))
    DB_DIR: Path = _resolve_path(_get_config_value("DB_DIR", "db"))
    CHROMA_PERSIST_DIR: Path = _resolve_path(_get_config_value("CHROMA_PERSIST_DIR", "db/chroma"))
    SQLITE_DB_PATH: Path = _resolve_path(_get_config_value("SQLITE_DB_PATH", "db/assistant.db"))

    # --- LLM Provider Selection ---
    # Supported values: "gemini" (primary), "claude", "ollama"
    LLM_PROVIDER: str = _get_config_value("LLM_PROVIDER", "gemini").lower().strip()

    # Google Gemini Settings (Supports single key or multiple keys for quota rotation)
    GEMINI_API_KEY: str = _get_config_value("GEMINI_API_KEY", "")
    GEMINI_API_KEYS_RAW: str = _get_config_value("GEMINI_API_KEYS", "")
    GEMINI_MODEL: str = _get_config_value("GEMINI_MODEL", "gemini-flash-lite-latest")

    @classmethod
    def get_gemini_api_keys(cls) -> list[str]:
        """Returns the list of configured Gemini API keys for rotation."""
        keys: list[str] = []
        if cls.GEMINI_API_KEYS_RAW:
            keys.extend([k.strip() for k in cls.GEMINI_API_KEYS_RAW.split(",") if k.strip()])
        if cls.GEMINI_API_KEY:
            for k in cls.GEMINI_API_KEY.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in keys:
                    keys.append(k_clean)
        return keys

    # Anthropic Claude Settings
    ANTHROPIC_API_KEY: str = _get_config_value("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = _get_config_value("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # Ollama Local LLM Settings
    OLLAMA_BASE_URL: str = _get_config_value("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = _get_config_value("OLLAMA_MODEL", "llama3.2")

    # --- RAG Hyperparameters ---
    # Minimum cosine similarity score required for a retrieved chunk to be considered relevant.
    # If no chunk meets this threshold, RAG Agent triggers a graceful refusal.
    RAG_SIMILARITY_THRESHOLD: float = float(_get_config_value("RAG_SIMILARITY_THRESHOLD", "0.30"))
    # Number of top chunks to retrieve from ChromaDB
    RAG_TOP_K: int = int(_get_config_value("RAG_TOP_K", "4"))
    # Token chunk size and sliding window overlap
    RAG_CHUNK_SIZE: int = int(_get_config_value("RAG_CHUNK_SIZE", "500"))
    RAG_CHUNK_OVERLAP: int = int(_get_config_value("RAG_CHUNK_OVERLAP", "50"))
    # Sentence Transformer embedding model (384-dimensional, local CPU inference)
    EMBEDDING_MODEL_NAME: str = _get_config_value(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # --- Web Fallback & Research Settings ---
    ENABLE_WEB_FALLBACK: bool = _get_config_value("ENABLE_WEB_FALLBACK", "true").lower() in ("true", "1", "yes")
    WEB_SEARCH_MIN_TRUST: float = float(_get_config_value("WEB_SEARCH_MIN_TRUST", "0.45"))

    # --- User Preferences & Persona ---
    USER_NAME: str = _get_config_value("USER_NAME", "Student")
    USER_DEFAULT_EMAIL: str = _get_config_value("USER_DEFAULT_EMAIL", "")
    TIMEZONE: str = _get_config_value("TIMEZONE", "Asia/Kolkata")
    DEFAULT_REMINDER_LEAD_HOURS: int = int(_get_config_value("DEFAULT_REMINDER_LEAD_HOURS", "24"))

    # --- Email MCP Tool Configuration ---
    GMAIL_USER: str = _get_config_value("GMAIL_USER", "")
    GMAIL_APP_PASSWORD: str = _get_config_value("GMAIL_APP_PASSWORD", "")

    # --- Administrator Authentication & Security Settings ---
    ADMIN_EMAIL: str = _get_config_value("ADMIN_EMAIL", "admin@assistant.local").strip().lower()
    ADMIN_PASSWORD_HASH: str = _get_config_value("ADMIN_PASSWORD_HASH", "").strip()
    ADMIN_INITIAL_PASSWORD: str = _get_config_value("ADMIN_INITIAL_PASSWORD", "AdminSecurePass2026!").strip()
    JWT_SECRET_KEY: str = _get_config_value("JWT_SECRET_KEY", "rag-mcp-assistant-jwt-secret-key-prod-2026").strip()
    JWT_ALGORITHM: str = _get_config_value("JWT_ALGORITHM", "HS256").strip()
    SESSION_EXPIRE_MINUTES: int = int(_get_config_value("SESSION_EXPIRE_MINUTES", "120"))
    RESET_TOKEN_EXPIRE_MINUTES: int = int(_get_config_value("RESET_TOKEN_EXPIRE_MINUTES", "15"))
    APP_BASE_URL: str = _get_config_value("APP_BASE_URL", "http://localhost:8501").rstrip("/")
    MAX_LOGIN_ATTEMPTS: int = int(_get_config_value("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_MINUTES: int = int(_get_config_value("LOCKOUT_MINUTES", "15"))
    MAX_RESET_ATTEMPTS: int = int(_get_config_value("MAX_RESET_ATTEMPTS", "3"))

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
