"""
==============================================================================
Test Suite: tests/test_gemini_key_rotation.py
Role: Unit Tests for Gemini API Key Rotation & Quota Management
==============================================================================
Validates:
1. Key parsing from single and multi-key configuration.
2. Round-robin rotation upon quota exhaustion (HTTP 429).
3. Cooldown tracking and skipping of temporarily exhausted keys.
4. Permanent error isolation for invalid keys.
5. Clean error handling when all keys in the pool are exhausted.
6. Masking of API keys in logs and diagnostics.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from llm.gemini_client import GeminiKeyManager, GeminiClient, mask_key
from llm.base import Message


def test_mask_key():
    """Verify that API keys are safely masked for logging."""
    assert mask_key("AQ1234567890XYZW") == "AQ12...XYZW"
    assert mask_key("") == "key_***"
    assert mask_key("short") == "key_***"


def test_key_manager_initialization():
    """Verify that key manager filters empty keys and placeholders."""
    raw_keys = ["key_alpha", "", "your_gemini_key", "key_beta"]
    km = GeminiKeyManager(raw_keys, cooldown_seconds=10.0)
    assert km.key_count == 2
    assert km.keys == ["key_alpha", "key_beta"]


def test_key_manager_rotation_on_exhaustion():
    """Verify that marking a key exhausted switches to the next eligible key."""
    km = GeminiKeyManager(["key_1", "key_2"], cooldown_seconds=5.0)

    # First key
    _, active_key1 = km.get_eligible_client()
    assert active_key1 == "key_1"

    # Mark key_1 exhausted (simulate 429)
    km.mark_exhausted("key_1")

    # Second key must now be selected
    _, active_key2 = km.get_eligible_client()
    assert active_key2 == "key_2"


def test_key_manager_all_exhausted():
    """Verify that when all keys are on cooldown, get_eligible_client returns None."""
    km = GeminiKeyManager(["key_1", "key_2"], cooldown_seconds=10.0)
    km.mark_exhausted("key_1")
    km.mark_exhausted("key_2")

    client, active_key = km.get_eligible_client()
    assert client is None
    assert active_key is None


def test_key_manager_invalid_key_permanent_removal():
    """Verify that permanently invalid keys are never re-selected."""
    km = GeminiKeyManager(["bad_key", "good_key"], cooldown_seconds=5.0)
    km.mark_invalid("bad_key")

    # Only good_key should be selected
    _, active_key = km.get_eligible_client()
    assert active_key == "good_key"

    # Even after multiple calls, bad_key is permanently skipped
    _, active_key_again = km.get_eligible_client()
    assert active_key_again == "good_key"


def test_gemini_client_all_keys_exhausted_response():
    """Verify that GeminiClient returns clean error response when all keys are exhausted."""
    client = GeminiClient(api_keys=["key_exhausted_1", "key_exhausted_2"], cooldown_seconds=30.0)
    # Manually exhaust all keys
    client.key_manager.mark_exhausted("key_exhausted_1")
    client.key_manager.mark_exhausted("key_exhausted_2")

    resp = client.generate([Message(role="user", content="Hello")])
    assert "Quota Error" in resp.content
    assert "rate-limited" in resp.content
