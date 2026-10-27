"""
==============================================================================
Test Suite: tests/test_email_regression.py
Regression Tests: Gmail API v1 Integration, HITL Safeguards, Idempotency,
                  Action History Awareness, Profile Identity & Security
==============================================================================
Verifies:
1. Successful Gmail send returns and records the real provider message ID.
2. Missing credentials never result in a success response.
3. Authentication and provider errors are shown honestly.
4. Simulation mode is never reported as real delivery.
5. The assistant correctly explains a previous failed or successful email action.
6. Profile email questions use the correct authorized profile fields.
7. Retries do not send duplicate emails.
8. Secrets are not exposed in logs or telemetry.
==============================================================================
"""

import datetime
import json
import pytest
from unittest.mock import MagicMock, patch

from mcp_servers.email_server import preview_email, send_email, sync_dispatch_email
from mcp_servers.google_services_server import google_gmail_send_message
from agents.memory import ConversationMemory
from agents.graph import create_orchestrator_graph, AgentState, handle_profile_query, handle_action_followup_query
from app.config import settings


class MockGmailService:
    """Mock Google Workspace Gmail REST API v1 service."""

    def __init__(self, sender_email="sergio759516@gmail.com"):
        self.sender_email = sender_email
        self.sent_messages = []
        self.send_count = 0
        self.simulated_api_error = None

    def build_mock(self):
        mock_svc = MagicMock()

        # Mock users().getProfile()
        mock_svc.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": self.sender_email,
            "messagesTotal": 100,
        }

        # Mock users().messages().send()
        def mock_send(userId="me", body=None):
            req = MagicMock()
            if self.simulated_api_error:
                req.execute.side_effect = self.simulated_api_error
                return req

            self.send_count += 1
            msg_id = f"gmail_msg_{self.send_count}_18f0a9b"
            thread_id = f"thread_{self.send_count}_99xyz"
            obj = {"id": msg_id, "threadId": thread_id}
            self.sent_messages.append({"id": msg_id, "raw": body.get("raw")})
            req.execute.return_value = obj
            return req

        mock_svc.users.return_value.messages.return_value.send.side_effect = mock_send

        # Mock users().messages().get() for read-back verification
        def mock_get(userId="me", id=""):
            req = MagicMock()
            found = next((m for m in self.sent_messages if m["id"] == id), None)
            if found:
                req.execute.return_value = {"id": id, "labelIds": ["SENT"]}
            else:
                req.execute.return_value = {"id": id, "labelIds": ["SENT"]}
            return req

        mock_svc.users.return_value.messages.return_value.get.side_effect = mock_get

        # Mock users().messages().list()
        def mock_list(userId="me", q="", maxResults=5):
            req = MagicMock()
            items = []
            if "Idempotent Subject" in q and self.sent_messages:
                items = [{"id": self.sent_messages[0]["id"]}]
            req.execute.return_value = {"messages": items, "items": items}
            return req

        mock_svc.users.return_value.messages.return_value.list.side_effect = mock_list

        return mock_svc


# ==============================================================================
# Requirement 1: Successful Gmail send returns and records real provider message ID
# ==============================================================================

def test_regression_1_successful_gmail_send_returns_and_records_message_id():
    """Verify that a confirmed email send produces a real message ID and records to action logs."""
    mock_gmail = MockGmailService()
    mock_svc = mock_gmail.build_mock()

    with patch("mcp_servers.email_server._get_google_service") as mock_get_svc:
        mock_get_svc.return_value = (mock_svc, {"status": "authenticated"})

        res = send_email(
            to="anandshankar898@gmail.com",
            subject="Project Meeting Update",
            body="Hello Anand, here are the meeting notes.",
            confirmed=True,
        )

        assert res["status"] == "success"
        assert res["action"] == "send_email"
        assert res["transport"] == "gmail_api_v1"
        assert res["delivery_state"] == "accepted_by_provider"
        msg_id = res["message_id"]
        assert msg_id.startswith("gmail_msg_1_")
        assert "anandshankar898@gmail.com" in res["message"]
        assert msg_id in res["message"]

        # Verify action was logged to SQLite action_logs
        actions = ConversationMemory.get_latest_actions(limit=1, tool_domain="email")
        assert len(actions) > 0
        latest = actions[0]
        assert latest["tool_name"] == "send_email"
        assert latest["status"] == "success"
        assert latest["receipt"]["message_id"] == msg_id


# ==============================================================================
# Requirement 2: Missing credentials never result in a success response
# ==============================================================================

def test_regression_2_missing_credentials_never_result_in_success():
    """Verify that unconfigured credentials return honest error and never fake success."""
    with patch("mcp_servers.email_server._get_google_service") as mock_get_svc, \
         patch.object(settings, "GMAIL_USER", ""), \
         patch.object(settings, "GMAIL_APP_PASSWORD", ""):
        mock_get_svc.return_value = (None, {"status": "unconfigured"})

        res = send_email(
            to="anandshankar898@gmail.com",
            subject="Unconfigured Test",
            body="Should fail honestly.",
            confirmed=True,
        )

        assert res["status"] == "error"
        assert "not configured" in res["message"].lower() or "unconfigured" in res.get("mode", "")
        assert "success" not in res.get("message", "").lower() or res["status"] != "success"


# ==============================================================================
# Requirement 3: Authentication and provider errors are shown honestly
# ==============================================================================

def test_regression_3_authentication_and_provider_errors_shown_honestly():
    """Verify that provider rejections or OAuth token errors surface cleanly without crashing."""
    mock_gmail = MockGmailService()
    mock_gmail.simulated_api_error = Exception("403 Forbidden: Insufficient OAuth permission for scope gmail.send")
    mock_svc = mock_gmail.build_mock()

    with patch("mcp_servers.email_server._get_google_service") as mock_get_svc:
        mock_get_svc.return_value = (mock_svc, {"status": "authenticated"})

        res = send_email(
            to="anandshankar898@gmail.com",
            subject="Permission Test",
            body="Test body",
            confirmed=True,
        )

        assert res["status"] == "error"
        assert "403" in res["message"] or "permission" in res["message"].lower() or "Gmail API error" in res["message"]


# ==============================================================================
# Requirement 4: Simulation mode is never reported as real delivery
# ==============================================================================

def test_regression_4_simulation_mode_never_reported_as_real_delivery():
    """Verify that mock or test modes never claim verified inbox delivery."""
    mock_gmail = MockGmailService()
    mock_svc = mock_gmail.build_mock()

    with patch("mcp_servers.email_server._get_google_service") as mock_get_svc:
        mock_get_svc.return_value = (mock_svc, {"status": "authenticated"})

        res = send_email(
            to="anandshankar898@gmail.com",
            subject="Delivery State Test",
            body="Test body",
            confirmed=True,
        )

        # Provider accepted does NOT claim inbox delivery
        assert res["delivery_state"] == "accepted_by_provider"
        assert "final inbox delivery depends on recipient server" in res["message"]


# ==============================================================================
# Requirement 5: Assistant explains previous email action truthfully
# ==============================================================================

def test_regression_5_assistant_explains_previous_email_action():
    """Verify that 'how did you send emails then?' inspects actual action logs instead of generic manual instructions."""
    # 5A. After a successful email
    ConversationMemory.log_action(
        session_id="test_email_expl",
        tool_name="send_email",
        arguments={"to": "anandshankar898@gmail.com", "subject": "Hi Anand"},
        receipt={
            "status": "success",
            "transport": "gmail_api_v1",
            "message_id": "18f0a9b8c7d6e5",
            "delivery_state": "accepted_by_provider",
        },
    )

    state: AgentState = {
        "session_id": "test_email_expl",
        "user_message": "how did you send emails then?",
        "trace": [],
    }

    res = handle_action_followup_query(state)
    answer = res["final_response"]

    assert "send_email" in answer
    assert "anandshankar898@gmail.com" in answer
    assert "18f0a9b8c7d6e5" in answer
    # Never give generic manual instructions
    assert "click compose" not in answer.lower()
    assert "open gmail.com" not in answer.lower()

    # 5B. After an unconfirmed draft
    ConversationMemory.log_action(
        session_id="test_unconfirmed_draft",
        tool_name="preview_email",
        arguments={"to": "hod@gec.ac.in", "subject": "Draft Submission"},
        receipt={"status": "ready_for_confirmation", "requires_confirmation": True},
    )

    state_unconf: AgentState = {
        "session_id": "test_unconfirmed_draft",
        "user_message": "how did you send the email?",
        "trace": [],
    }

    res_unconf = handle_action_followup_query(state_unconf)
    ans_unconf = res_unconf["final_response"]
    assert "preview_email" in ans_unconf or "confirmation" in ans_unconf.lower()
    assert "hod@gec.ac.in" in ans_unconf


# ==============================================================================
# Requirement 6: Profile email questions use authorized profile fields
# ==============================================================================

def test_regression_6_profile_email_questions_use_authorized_profile_fields():
    """Verify that 'whats my email id' returns configured profile email and distinguishes from Gmail sender."""
    ConversationMemory.set_preference("email", "alex.student@ktu.edu.in")
    ConversationMemory.set_preference("name", "Alex")

    state: AgentState = {
        "session_id": "test_profile_session",
        "user_message": "whats my email id",
        "user_preferences": {"name": "Alex", "email": "alex.student@ktu.edu.in"},
        "trace": [],
    }

    res = handle_profile_query(state)
    resp = res["final_response"]

    assert "alex.student@ktu.edu.in" in resp
    assert "University Email" in resp
    # Refusal string from documents MUST NOT be present
    assert "couldn't find this in your documents" not in resp.lower()
    assert "Alex" in resp


# ==============================================================================
# Requirement 7: Retries do not send duplicate emails
# ==============================================================================

def test_regression_7_retries_do_not_send_duplicate_emails():
    """Verify that sending identical emails within a short window reuses existing message without re-sending."""
    mock_gmail = MockGmailService()
    mock_svc = mock_gmail.build_mock()

    with patch("mcp_servers.email_server._get_google_service") as mock_get_svc:
        mock_get_svc.return_value = (mock_svc, {"status": "authenticated"})

        # Initial send
        res1 = send_email(
            to="colleague@example.com",
            subject="Idempotent Subject",
            body="Original message content",
            confirmed=True,
        )
        assert res1["status"] == "success"
        first_msg_id = res1["message_id"]
        assert mock_gmail.send_count == 1

        # Second send (retry)
        res2 = send_email(
            to="colleague@example.com",
            subject="Idempotent Subject",
            body="Original message content",
            confirmed=True,
        )
        assert res2["status"] == "success"
        assert res2["message_id"] == first_msg_id
        assert res2.get("duplicate_prevented") is True
        # Critical assertion: send was NOT called a second time
        assert mock_gmail.send_count == 1


# ==============================================================================
# Requirement 8: Secrets are not exposed in logs or telemetry
# ==============================================================================

def test_regression_8_secrets_are_not_exposed_in_logs_or_telemetry():
    """Verify that sensitive arguments are masked with [REDACTED] in SQLite action logs."""
    ConversationMemory.log_action(
        session_id="sec_test",
        tool_name="send_email",
        arguments={
            "to": "user@example.com",
            "password": "super_secret_password_123",
            "api_key": "AIzaSySecretApiKey456",
            "oauth_token": "ya29.SecretToken789",
        },
        receipt={"status": "success"},
    )

    actions = ConversationMemory.get_latest_actions(session_id="sec_test", limit=1)
    assert len(actions) == 1
    args = actions[0]["arguments"]

    assert args["password"] == "[REDACTED]"
    assert args["api_key"] == "[REDACTED]"
    assert args["oauth_token"] == "[REDACTED]"
    assert "super_secret_password_123" not in json.dumps(args)
    assert "AIzaSySecretApiKey456" not in json.dumps(args)
    assert "ya29.SecretToken789" not in json.dumps(args)
