
"""
==============================================================================
Module: llm.gemini_client
Role: Google Gemini API Provider Implementation
==============================================================================
Uses the google-genai SDK while preserving the project's LLMClient interface,
conversation history, system instructions, and function calling.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.config import settings
from llm.base import LLMClient, LLMResponse, Message, ToolCall


class GeminiClient(LLMClient):
    """LLM client using Google's Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client = None

        if not self.api_key or self.api_key.startswith("your_"):
            print(
                "[WARNING] GEMINI_API_KEY is missing or is a placeholder. "
                "Configure it in your .env file or environment variables."
            )
        else:
            self.client = genai.Client(api_key=self.api_key)

    def _convert_tool_to_gemini(
        self, tool_def: Dict[str, Any]
    ) -> types.FunctionDeclaration:
        """Convert a standard JSON Schema tool definition for Gemini."""

        name = tool_def.get("name", "")
        description = tool_def.get("description", "")
        parameters = (
            tool_def.get("parameters")
            or tool_def.get("input_schema")
            or {"type": "object", "properties": {}}
        )

        return types.FunctionDeclaration(
            name=name,
            description=description,
            parameters_json_schema=parameters,
        )

    def generate(
        self,
        messages: List[Dict[str, str] | Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Generate a response and extract any requested tool calls."""

        if self.client is None:
            return LLMResponse(
                content=(
                    "[Configuration Error] GEMINI_API_KEY is missing. "
                    "Configure it in the .env file."
                ),
                tool_calls=[],
            )

        system_instruction: Optional[str] = None
        gemini_contents: List[types.Content] = []

        for msg in messages:
            if isinstance(msg, Message):
                role = msg.role
                content = msg.content
            else:
                role = msg.get("role", "user")
                content = msg.get("content", "")

            if role == "system":
                system_instruction = content

            elif role in ("assistant", "model"):
                gemini_contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

            else:
                gemini_contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        if not gemini_contents:
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Hello")],
                )
            )

        gemini_tools = None

        if tools:
            declarations = [
                self._convert_tool_to_gemini(tool_def)
                for tool_def in tools
            ]

            gemini_tools = [
                types.Tool(function_declarations=declarations)
            ]

        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            tools=gemini_tools,
        )

        models_to_try = [self.model_name]
        for fallback_m in ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        last_error = None
        for current_model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=gemini_contents,
                    config=generation_config,
                )

                text_chunks: List[str] = []
                extracted_tool_calls: List[ToolCall] = []

                for candidate in response.candidates or []:
                    if not candidate.content or not candidate.content.parts:
                        continue

                    for part in candidate.content.parts:
                        if part.text:
                            text_chunks.append(part.text)

                        function_call = part.function_call

                        if function_call and function_call.name:
                            extracted_tool_calls.append(
                                ToolCall(
                                    id=f"call_{uuid.uuid4().hex[:8]}",
                                    name=function_call.name,
                                    arguments=dict(function_call.args or {}),
                                )
                            )

                return LLMResponse(
                    content="".join(text_chunks).strip(),
                    tool_calls=extracted_tool_calls,
                    raw_response=response,
                )

            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                if ("503" in err_str or "404" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and current_model != models_to_try[-1]:
                    next_model = models_to_try[models_to_try.index(current_model) + 1]
                    print(f"[RETRY] Model '{current_model}' quota/rate-limited, trying fallback model '{next_model}'...")
                    continue
                break

        error_message = f"Gemini API invocation failed: {last_error}"
        print(f"[ERROR] {error_message}")

        return LLMResponse(
            content=f"Error: {error_message}",
            tool_calls=[],
        )

