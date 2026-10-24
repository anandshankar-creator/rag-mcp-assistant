"""
==============================================================================
Module: llm.__init__
Role in Architecture: LLM Factory & Provider Resolver
==============================================================================
Provides the `get_llm_client()` factory function. This allows any component
(RAG Generator, Router, Planner, Action Agent) to request an LLM instance
without hardcoding which vendor is providing the model.
"""

from typing import Optional
from app.config import settings
from llm.base import LLMClient, LLMResponse, Message, ToolCall
from llm.gemini_client import GeminiClient
from llm.claude_client import ClaudeClient
from llm.ollama_client import OllamaClient


def get_llm_client(provider: Optional[str] = None) -> LLMClient:
    """
    Factory function returning the configured LLM client instance.

    Args:
        provider: "gemini", "claude", or "ollama". If None, reads from settings.LLM_PROVIDER.

    Returns:
        Subclass of LLMClient configured for the requested provider.
    """
    target_provider = (provider or settings.LLM_PROVIDER).lower().strip()

    if target_provider in ("gemini", "google"):
        return GeminiClient()
    elif target_provider in ("claude", "anthropic"):
        return ClaudeClient()
    elif target_provider in ("ollama", "local"):
        return OllamaClient()
    else:
        print(f"[WARNING] Unknown provider '{target_provider}', defaulting to GeminiClient.")
        return GeminiClient()


__all__ = [
    "LLMClient",
    "LLMResponse",
    "Message",
    "ToolCall",
    "GeminiClient",
    "ClaudeClient",
    "OllamaClient",
    "get_llm_client",
]
