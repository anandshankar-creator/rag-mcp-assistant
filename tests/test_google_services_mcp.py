"""
==============================================================================
Test Suite: tests/test_google_services_mcp.py
Role: Unit Tests for Authentic Google Services FastMCP Server and Discovery
==============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch
from mcp_servers.client import MCPClientController
from mcp_servers.google_services_server import (
    google_calendar_create_event,
    google_gmail_send_message,
    google_tasks_create,
    google_keep_note,
)


def test_mcp_discovery_includes_google_services():
    """Verify MCPClientController discovers Google Workspace tools dynamically."""
    controller = MCPClientController()
    tools = controller.get_tool_definitions()
    tool_names = [t["name"] for t in tools]

    assert "google_calendar_create_event" in tool_names
    assert "google_calendar_list_events" in tool_names
    assert "google_gmail_send_message" in tool_names
    assert "google_gmail_list_messages" in tool_names
    assert "google_tasks_create" in tool_names
    assert "google_tasks_list" in tool_names
    assert "google_drive_search" in tool_names
    assert "google_keep_note" in tool_names


def test_google_gmail_hitl_enforcement():
    """Verify Gmail MCP tool enforces explicit confirmation before dispatch."""
    res = google_gmail_send_message(
        to="colleague@example.com",
        subject="Meeting Notes",
        body="Here are the notes.",
        confirmed=False,
    )
    assert res["status"] == "error"
    assert res.get("requires_confirmation") is True
    assert "User confirmation is strictly required" in res["message"]


def test_google_services_unconfigured_honest_diagnostics():
    """Verify tools return honest diagnostic status when OAuth credentials are absent."""
    with patch("mcp_servers.google_services_server.get_google_auth_manager") as mock_auth:
        mock_mgr = MagicMock()
        mock_mgr.get_credentials.return_value = (
            None,
            {"status": "unconfigured", "message": "Credentials missing in credentials/credentials.json"},
        )
        mock_auth.return_value = mock_mgr

        res = google_calendar_create_event(
            title="Design Review",
            start_time="2026-11-01 10:00:00",
            end_time="2026-11-01 11:00:00",
        )
        assert res["status"] == "unconfigured"
        assert "credentials" in res["message"].lower()


def test_google_services_mock_live_execution():
    """Verify tools properly invoke Google API client methods when credentials exist."""
    mock_service = MagicMock()
    mock_events = MagicMock()
    mock_events.insert.return_value.execute.return_value = {
        "id": "gcal_event_12345",
        "htmlLink": "https://calendar.google.com/event?eid=12345",
        "summary": "AI Team Sync",
        "start": {"dateTime": "2026-11-01T10:00:00Z"},
    }
    mock_service.events.return_value = mock_events

    with patch("mcp_servers.google_services_server._get_google_service") as mock_get_svc:
        mock_get_svc.return_value = (mock_service, {"status": "authenticated"})

        res = google_calendar_create_event(
            title="AI Team Sync",
            start_time="2026-11-01 10:00:00",
            end_time="2026-11-01 11:00:00",
        )
        assert res["status"] == "success"
        assert res["event_id"] == "gcal_event_12345"
        assert "html_link" in res
