
"""
==============================================================================
Module: llm.gemini_client
Role: Google Gemini API Provider Implementation
==============================================================================
Uses the google-genai SDK while preserving the project's LLMClient interface,
conversation history, system instructions, and function calling.
"""

from __future__ import annotations

import time
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from app.config import settings
from llm.base import LLMClient, LLMResponse, Message, ToolCall


def mask_key(key: str) -> str:
    """Safely masks an API key for logs and debug output."""
    if not key or len(key) < 8:
        return "key_***"
    return f"{key[:4]}...{key[-4:]}"


class GeminiKeyManager:
    """
    Manages a pool of Gemini API keys with thread-safe rotation,
    per-key cooldown tracking on quota exhaustion (HTTP 429), and permanent error isolation.
    """

    def __init__(self, api_keys: List[str], cooldown_seconds: float = 60.0):
        # Filter placeholders and empty values
        self.keys = [
            k.strip() for k in api_keys
            if k.strip() and not k.strip().startswith("your_")
        ]
        self.cooldown_seconds = cooldown_seconds
        self.cooldowns: Dict[str, float] = {}
        self.invalid_keys: set[str] = set()
        self.current_index: int = 0
        self._lock = threading.Lock()
        self._clients: Dict[str, genai.Client] = {}

    @property
    def has_keys(self) -> bool:
        return len(self.keys) > 0

    @property
    def key_count(self) -> int:
        return len(self.keys)

    def get_eligible_client(self) -> Tuple[Optional[genai.Client], Optional[str]]:
        """
        Returns the next eligible genai.Client instance and its masked key.
        Iterates round-robin while skipping keys currently on cooldown or marked invalid.
        """
        with self._lock:
            if not self.keys:
                return None, None

            now = time.time()
            # Attempt to find an active key starting from current_index
            for i in range(len(self.keys)):
                idx = (self.current_index + i) % len(self.keys)
                candidate_key = self.keys[idx]

                if candidate_key in self.invalid_keys:
                    continue

                if self.cooldowns.get(candidate_key, 0) > now:
                    continue

                # Found an eligible key
                self.current_index = idx
                if candidate_key not in self._clients:
                    self._clients[candidate_key] = genai.Client(api_key=candidate_key)

                return self._clients[candidate_key], candidate_key

            return None, None

    def mark_exhausted(self, key: str, custom_cooldown: Optional[float] = None) -> None:
        """Marks a key as temporarily exhausted due to HTTP 429 / quota limit."""
        with self._lock:
            cooldown = custom_cooldown or self.cooldown_seconds
            self.cooldowns[key] = time.time() + cooldown
            masked = mask_key(key)
            print(f"[GEMINI ROTATION] Key '{masked}' rate-limited. Placed on {int(cooldown)}s cooldown.")
            if self.keys:
                self.current_index = (self.current_index + 1) % len(self.keys)

    def mark_invalid(self, key: str) -> None:
        """Marks a key as permanently invalid (bad key, deleted, or unauthenticated)."""
        with self._lock:
            self.invalid_keys.add(key)
            masked = mask_key(key)
            print(f"[GEMINI ERROR] Key '{masked}' is permanently invalid. Removed from pool.")
            if self.keys:
                self.current_index = (self.current_index + 1) % len(self.keys)


class GeminiClient(LLMClient):
    """
    LLM client using Google's Gemini API with multi-key pool rotation,
    quota recovery, model fallback, and function calling support.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        model_name: Optional[str] = None,
        cooldown_seconds: float = 60.0,
    ):
        # Build key pool from explicit arguments or application settings
        configured_keys: List[str] = []
        if api_keys:
            configured_keys.extend(api_keys)
        elif api_key:
            configured_keys.append(api_key)
        else:
            configured_keys.extend(settings.get_gemini_api_keys())

        self.key_manager = GeminiKeyManager(configured_keys, cooldown_seconds=cooldown_seconds)
        self.model_name = model_name or settings.GEMINI_MODEL

        if not self.key_manager.has_keys:
            print(
                "[WARNING] No valid Gemini API keys found. "
                "Configure GEMINI_API_KEY or GEMINI_API_KEYS in your .env file."
            )
        else:
            print(f"[GEMINI] Initialized key pool with {self.key_manager.key_count} configured key(s).")

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
        max_quota_retries: int = 0,
    ) -> LLMResponse:
        """
        Generate a response with automatic multi-key rotation and cooldown retry on HTTP 429 quota exhaustion.
        """
        if not self.key_manager.has_keys:
            return LLMResponse(
                content=(
                    "[Configuration Error] GEMINI_API_KEY is missing. "
                    "Configure GEMINI_API_KEY or GEMINI_API_KEYS in the .env file."
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

        # Bounded rotation loop: Try each eligible key in pool with optional cooldown wait-retries
        total_attempts = max(1, self.key_manager.key_count) + max_quota_retries
        last_error = None

        for attempt in range(total_attempts):
            client, active_key = self.key_manager.get_eligible_client()
            if client is None or active_key is None:
                if attempt < max_quota_retries and self.key_manager.keys:
                    now = time.time()
                    cooldowns = [
                        self.key_manager.cooldowns[k] - now
                        for k in self.key_manager.keys
                        if k not in self.key_manager.invalid_keys and k in self.key_manager.cooldowns
                    ]
                    wait_time = min(cooldowns) if cooldowns else (2.0 ** attempt)
                    wait_time = max(1.0, min(wait_time, 15.0))
                    print(f"[GEMINI RETRY] All keys rate-limited. Waiting {wait_time:.1f}s before retry ({attempt + 1}/{max_quota_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    # All configured keys are currently exhausted or on cooldown
                    return LLMResponse(
                        content=(
                            "[Quota Error] All configured Gemini API keys are currently rate-limited or on cooldown. "
                            "Please wait for cooldown or configure local Ollama."
                        ),
                        tool_calls=[],
                    )

            # Try models on the active key
            for current_model in models_to_try:
                try:
                    response = client.models.generate_content(
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

                    # Check for permanent invalid key
                    if "API_KEY_INVALID" in err_str or "INVALID_ARGUMENT" in err_str:
                        self.key_manager.mark_invalid(active_key)
                        break  # Break model loop to rotate key immediately

                    # Check for quota exhaustion / rate limit (HTTP 429)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate limit" in err_str.lower():
                        self.key_manager.mark_exhausted(active_key)
                        break  # Break model loop to rotate key immediately

                    # Temporary server issues (503 / 404 / unavailable) can try next fallback model on same key
                    if ("503" in err_str or "404" in err_str or "UNAVAILABLE" in err_str) and current_model != models_to_try[-1]:
                        continue

                    # Other unknown fatal error
                    break

        error_message = f"Gemini API invocation failed: {last_error}"
        print(f"[ERROR] {error_message}")
        return LLMResponse(
            content=f"Error: {error_message}",
            tool_calls=[],
        )

