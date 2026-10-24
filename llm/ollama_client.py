"""
==============================================================================
Module: llm.ollama_client
Role in Architecture: Local Offline LLM Provider (Ollama API Stub/Client)
==============================================================================
Implements the LLMClient interface connecting to a locally hosted Ollama instance
(e.g., Llama 3.2, Mistral, Qwen).

Why this matters for the B.Tech review:
Demonstrates privacy preservation. When dealing with highly sensitive university
documents, students can configure LLM_PROVIDER=ollama to guarantee that no document
chunks ever leave the local machine.
"""

from __future__ import annotations
import json
import uuid
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from app.config import settings
from llm.base import LLMClient, LLMResponse, Message, ToolCall


class OllamaClient(LLMClient):
    """Client for querying local LLMs served via Ollama REST API."""

    def __init__(self, base_url: Optional[str] = None, model_name: Optional[str] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.OLLAMA_MODEL

    def generate(
        self,
        messages: List[Dict[str, str] | Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """
        Sends a standard chat request to the Ollama endpoint:
        POST {base_url}/api/chat
        """
        formatted_messages: List[Dict[str, str]] = []
        for msg in messages:
            role = msg.role if isinstance(msg, Message) else msg.get("role", "user")
            content = msg.content if isinstance(msg, Message) else msg.get("content", "")
            # Map role
            if role == "model":
                role = "assistant"
            formatted_messages.append({"role": role, "content": content})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        # Include tools in payload if supported by local model
        if tools:
            payload["tools"] = tools

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                msg = body.get("message", {})
                content = msg.get("content", "")

                # Parse tool calls if returned by Ollama
                extracted_tools: List[ToolCall] = []
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    extracted_tools.append(
                        ToolCall(
                            id=f"call_{uuid.uuid4().hex[:8]}",
                            name=fn.get("name", ""),
                            arguments=fn.get("arguments", {}),
                        )
                    )

                return LLMResponse(
                    content=content.strip(),
                    tool_calls=extracted_tools,
                    raw_response=body,
                )

        except urllib.error.URLError as e:
            return LLMResponse(
                content=f"[Local LLM Offline] Could not connect to Ollama at {self.base_url}. "
                f"Ensure Ollama is running (`ollama serve`). Details: {str(e)}",
                tool_calls=[],
            )
        except Exception as e:
            return LLMResponse(
                content=f"[Ollama Error] Unexpected failure: {str(e)}",
                tool_calls=[],
            )
