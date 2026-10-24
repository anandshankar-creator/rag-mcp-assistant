"""
==============================================================================
Module: llm.claude_client
Role in Architecture: Anthropic Claude API Provider Implementation
==============================================================================
Implements the LLMClient interface using the Anthropic Python SDK.
Serves as an alternate provider in the multi-provider architecture to demonstrate
that the agent orchestration and RAG retrieval pipelines are strictly vendor-agnostic.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from app.config import settings
from llm.base import LLMClient, LLMResponse, Message, ToolCall


class ClaudeClient(LLMClient):
    """Concrete LLM client connecting to Anthropic Claude (e.g., Claude 3.5 Sonnet)."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model_name = model_name or settings.ANTHROPIC_MODEL
        self._client = None

        if self.api_key and not self.api_key.startswith("your_"):
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                print("[WARNING] 'anthropic' package not installed. Run `pip install anthropic`.")
        else:
            print("[INFO] ANTHROPIC_API_KEY is not configured. Claude client initialized in dormant state.")

    def generate(
        self,
        messages: List[Dict[str, str] | Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Execute chat completion using Anthropic Claude API."""
        if not self._client:
            return LLMResponse(
                content="[Configuration Error] Claude client is not configured or ANTHROPIC_API_KEY is missing.",
                tool_calls=[],
            )

        # 1. Separate system message
        system_text: str = ""
        claude_messages: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.role if isinstance(msg, Message) else msg.get("role", "user")
            content = msg.content if isinstance(msg, Message) else msg.get("content", "")

            if role == "system":
                system_text = content
            elif role in ("assistant", "model"):
                claude_messages.append({"role": "assistant", "content": content})
            else:
                claude_messages.append({"role": "user", "content": content})

        # 2. Format tools for Claude (input_schema convention)
        claude_tools = None
        if tools:
            claude_tools = []
            for t in tools:
                schema = t.get("parameters") or t.get("input_schema") or {"type": "object", "properties": {}}
                claude_tools.append({
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "input_schema": schema,
                })

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model_name,
                "messages": claude_messages,
                "max_tokens": 2048,
                "temperature": temperature,
            }
            if system_text:
                kwargs["system"] = system_text
            if claude_tools:
                kwargs["tools"] = claude_tools

            response = self._client.messages.create(**kwargs)

            # 3. Extract text content and tool use blocks
            text_blocks: List[str] = []
            extracted_tools: List[ToolCall] = []

            for block in response.content:
                if block.type == "text":
                    text_blocks.append(block.text)
                elif block.type == "tool_use":
                    extracted_tools.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input,
                        )
                    )

            return LLMResponse(
                content="".join(text_blocks).strip(),
                tool_calls=extracted_tools,
                raw_response=response,
            )

        except Exception as e:
            error_message = f"Anthropic Claude API invocation failed: {str(e)}"
            print(f"[ERROR] {error_message}")
            return LLMResponse(content=f"Error: {error_message}", tool_calls=[])
