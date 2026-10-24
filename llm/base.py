"""
==============================================================================
Module: llm.base
Role in Architecture: LLM Provider Abstraction Layer (Core Interface)
==============================================================================
This module defines the provider-agnostic contract for LLM communication.
Our research architecture claims that the system is LLM-agnostic: the agent
logic, RAG grounding, and MCP tool execution are completely decoupled from
the underlying model vendor.

Students can explain this design pattern (Strategy / Factory Pattern) at review:
Swapping from Google Gemini to Anthropic Claude or a local Ollama model requires
zero changes to the RAG Agent, Planner, or Action Agent.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """Represents a structured function call requested by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Message:
    """Represents a standardized chat message in a conversation turn."""
    role: str  # "system", "user", or "assistant"
    content: str


@dataclass
class LLMResponse:
    """
    Standardized response returned by any LLM provider.
    Guarantees that downstream agents receive identical data structures
    regardless of whether Gemini, Claude, or Ollama generated the response.
    """
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_response: Optional[Any] = None

    @property
    def has_tool_calls(self) -> bool:
        """Helper to quickly check if the model requested any tool executions."""
        return len(self.tool_calls) > 0


class LLMClient(ABC):
    """
    Abstract Base Class defining the universal interface for LLM providers.
    Every provider (Gemini, Claude, Ollama) must implement `generate`.
    """

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str] | Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """
        Generate a text response or tool calls given a message history and optional tools.

        Args:
            messages: List of message objects or dicts with 'role' and 'content'.
            tools: Optional list of tool specifications in JSON schema format.
            temperature: Sampling temperature (low temperature = 0.2 for deterministic QA).

        Returns:
            LLMResponse containing text content and/or structured tool calls.
        """
        pass
