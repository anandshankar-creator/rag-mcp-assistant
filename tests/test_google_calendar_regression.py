"""
==============================================================================
Test Suite: tests/test_google_calendar_regression.py
Regression Tests: Google Calendar Integration, Timezones, Read-Back Verification,
                  and Idempotency (Preventing False Success Reports)
==============================================================================
Verifies:
1. Creating a reminder produces a real Google Calendar event.
2. The event appears in a subsequent event-list query.
3. The event uses the correct date and Asia/Kolkata timezone.
4. An API failure never produces a success message.
5. An event created in a different calendar is not falsely reported as being in the intended calendar.
6. Retrying after a timeout does not create duplicates.
7. Local reminders and Google Calendar events are clearly distinguished.
==============================================================================
"""

import datetime
import pytest
from unittest.mock import MagicMock, patch

from mcp_servers.calendar_server import create_event, list_events, delete_event
from mcp_servers.reminder_server import create_reminder, list_reminders, delete_reminder
from mcp_servers.google_services_server import (
    google_calendar_create_event,
    google_calendar_list_events,
    sync_create_google_calendar_event,
)
from mcp_servers.client import get_mcp_client
from agents.action_agent import ActionAgent


class MockGoogleCalendarStore:
    """In-memory mock backing Google Calendar API v3 methods."""

    def __init__(self, primary_email="sergio759516@gmail.com"):
        self.primary_email = primary_email
        self.events_store = {}  # (calendar_id, event_id) -> event_dict
        self.insert_count = 0
        self.insert_calls = []
        self.simulated_api_error = None
        self.simulated_readback_error = None

    def build_service_mock(self):
        mock_service = MagicMock()

        # Mock calendars().get()
        def mock_cal_get(calendarId="primary"):
            mock_req = MagicMock()
            if calendarId == "primary":
                mock_req.execute.return_value = {
                    "id": self.primary_email,
                    "summary": self.primary_email,
                    "timeZone": "Asia/Kolkata",
                }
            elif calendarId == "secondary":
                mock_req.execute.return_value = {
                    "id": "secondary@example.com",
                    "summary": "Secondary Calendar",
                    "timeZone": "Asia/Kolkata",
                }
            else:
                mock_req.execute.return_value = {
                    "id": calendarId,
                    "summary": calendarId,
                    "timeZone": "Asia/Kolkata",
                }
            return mock_req

        mock_service.calendars.return_value.get.side_effect = mock_cal_get

        # Mock events().insert()
        def mock_events_insert(calendarId="primary", body=None):
            mock_req = MagicMock()
            if self.simulated_api_error:
                mock_req.execute.side_effect = self.simulated_api_error
                return mock_req

            self.insert_count += 1
            self.insert_calls.append({"calendarId": calendarId, "body": body})

            evt_id = f"gcal_evt_{self.insert_count}_{body.get('summary', '').replace(' ', '_')[:15]}"
            cal_key = self.primary_email if calendarId == "primary" else calendarId

            event_obj = {
                "id": evt_id,
                "summary": body.get("summary", ""),
                "description": body.get("description", ""),
                "start": body.get("start", {}),
                "end": body.get("end", {}),
                "status": "confirmed",
                "htmlLink": f"https://calendar.google.com/event?eid={evt_id}",
                "organizer": {"email": cal_key},
            }
            self.events_store[(cal_key, evt_id)] = event_obj

            mock_req.execute.return_value = event_obj
            return mock_req

        mock_service.events.return_value.insert.side_effect = mock_events_insert

        # Mock events().get()
        def mock_events_get(calendarId="primary", eventId=""):
            mock_req = MagicMock()
            if self.simulated_readback_error:
                mock_req.execute.side_effect = self.simulated_readback_error
                return mock_req

            cal_key = self.primary_email if calendarId == "primary" else calendarId
            key = (cal_key, eventId)
            if key in self.events_store:
                mock_req.execute.return_value = self.events_store[key]
            else:
                # 404 not found in this calendar
                mock_req.execute.side_effect = Exception(f"404 Not Found: event '{eventId}' in calendar '{calendarId}'")
            return mock_req

        mock_service.events.return_value.get.side_effect = mock_events_get

        # Mock events().list()
        def mock_events_list(calendarId="primary", **kwargs):
            mock_req = MagicMock()
            cal_key = self.primary_email if calendarId == "primary" else calendarId
            items = [evt for (c_id, _), evt in self.events_store.items() if c_id == cal_key and evt.get("status") != "cancelled"]
            mock_req.execute.return_value = {"items": items}
            return mock_req

        mock_service.events.return_value.list.side_effect = mock_events_list

        # Mock events().delete()
        def mock_events_delete(calendarId="primary", eventId=""):
            mock_req = MagicMock()
            cal_key = self.primary_email if calendarId == "primary" else calendarId
            key = (cal_key, eventId)
            if key in self.events_store:
                self.events_store[key]["status"] = "cancelled"
            mock_req.execute.return_value = {}
            return mock_req

        mock_service.events.return_value.delete.side_effect = mock_events_delete

        return mock_service


@pytest.fixture
def mock_google_cal():
    store = MockGoogleCalendarStore()
    mock_svc = store.build_service_mock()
    with patch("mcp_servers.google_services_server._get_google_service") as mock_get:
        mock_get.return_value = (mock_svc, {"status": "authenticated"})
        yield store


# ==============================================================================
# Requirement 1: Creating a reminder produces a real Google Calendar event
# ==============================================================================

def test_regression_1_creating_reminder_produces_real_google_calendar_event(mock_google_cal):
    """Verify that creating a reminder creates a verified event on Google Calendar."""
    res = create_reminder(
        title="Revise Operating Systems Unit 4",
        due_datetime="2026-10-28 09:00:00",
        note="Memory management revision",
    )

    assert res["status"] == "success"
    assert res["provider"] == "google_calendar"
    assert res["verified"] is True
    assert res["calendar_id"] == "sergio759516@gmail.com"
    g_event_id = res["google_event_id"]
    assert g_event_id is not None

    # Verify event actually exists in the Google Calendar store
    key = ("sergio759516@gmail.com", g_event_id)
    assert key in mock_google_cal.events_store
    stored_event = mock_google_cal.events_store[key]
    assert "Revise Operating Systems Unit 4" in stored_event["summary"]
    assert stored_event["status"] == "confirmed"

    # Cleanup
    delete_reminder(res["reminder_id"])


# ==============================================================================
# Requirement 2: The event appears in a subsequent event-list query
# ==============================================================================

def test_regression_2_event_appears_in_subsequent_event_list_query(mock_google_cal):
    """Verify that newly created events appear in both Google and unified list queries."""
    create_res = create_event(
        title="KTU CS402 Project Viva",
        start="2026-10-28 10:00:00",
        end="2026-10-28 11:00:00",
        description="Final Project Defense in Seminar Hall",
    )
    assert create_res["status"] == "success"
    g_id = create_res["event_id"]

    # 1. Query via google_calendar_list_events
    g_list = google_calendar_list_events(date_range="2026-10-28")
    assert g_list["status"] == "success"
    assert any(e["id"] == g_id and "CS402" in e["summary"] for e in g_list["events"])

    # 2. Query via unified calendar_server list_events
    unified_list = list_events(date_range="2026-10-28")
    assert any(e["id"] == g_id and "CS402" in e.get("title", "") for e in unified_list)

    # Cleanup
    delete_event(g_id)


# ==============================================================================
# Requirement 3: The event uses the correct date and Asia/Kolkata timezone
# ==============================================================================

def test_regression_3_event_uses_correct_date_and_kolkata_timezone(mock_google_cal):
    """Verify that start and end dateTimes are strictly formatted with Asia/Kolkata (+05:30)."""
    res = create_event(
        title="Automated Test Event",
        start="2026-10-28 09:00:00",
        end="2026-10-28 10:00:00",
    )
    assert res["status"] == "success"
    assert res["timezone"] == "Asia/Kolkata"

    # Inspect the exact payload sent to Google Calendar API
    last_call = mock_google_cal.insert_calls[-1]
    body = last_call["body"]

    start_obj = body["start"]
    end_obj = body["end"]

    assert start_obj["timeZone"] == "Asia/Kolkata"
    assert end_obj["timeZone"] == "Asia/Kolkata"

    # Must be 2026-10-28T09:00:00+05:30 (NOT UTC or naive)
    assert start_obj["dateTime"] == "2026-10-28T09:00:00+05:30"
    assert end_obj["dateTime"] == "2026-10-28T10:00:00+05:30"
    assert not start_obj["dateTime"].endswith("Z")
    assert not start_obj["dateTime"].endswith("+00:00")

    delete_event(res["event_id"])


# ==============================================================================
# Requirement 4: An API failure never produces a success message
# ==============================================================================

def test_regression_4_api_failure_never_produces_success_message(mock_google_cal):
    """Verify that Google API failures return status='error' and never claim false success."""
    # 4A. Insertion Failure (e.g. 503 Backend Error)
    mock_google_cal.simulated_api_error = Exception("503 Backend Error: Google Calendar Service Unavailable")

    res = create_event(
        title="Failing Event",
        start="2026-10-28 11:00:00",
    )
    assert res["status"] == "error"
    assert "success" not in res.get("message", "").lower() or res["status"] != "success"
    assert "Google Calendar API creation failed" in res["message"]

    # Verify through MCP Client Controller
    client = get_mcp_client()
    receipt = client.execute_tool("create_event", {"title": "Failing Event", "start": "2026-10-28 11:00:00"})
    assert receipt["status"] == "error"
    assert "creation failed" in receipt["message"]

    # 4B. Read-Back Verification Failure (insert succeeded, but event verification failed)
    mock_google_cal.simulated_api_error = None
    mock_google_cal.simulated_readback_error = Exception("404 Event Not Found on read-back")

    res_rb_fail = create_event(
        title="Unverified Event",
        start="2026-10-28 12:00:00",
    )
    assert res_rb_fail["status"] == "error"
    assert "read-back verification failed" in res_rb_fail["message"].lower()


# ==============================================================================
# Requirement 5: Event in different calendar is not falsely reported as intended
# ==============================================================================

def test_regression_5_event_in_different_calendar_not_reported_as_intended(mock_google_cal):
    """Verify calendar mismatch detection and read-back failure if event is not in intended calendar."""
    # If caller expected primary calendar ("sergio759516@gmail.com") but target was "secondary"
    res = sync_create_google_calendar_event(
        title="Cross Calendar Event",
        start_time="2026-10-28 13:00:00",
        target_calendar_id="secondary",
        expected_calendar_id="sergio759516@gmail.com",
    )
    assert res["status"] == "error"
    assert "calendar mismatch" in res["message"].lower()


# ==============================================================================
# Requirement 6: Retrying after a timeout does not create duplicates
# ==============================================================================

def test_regression_6_retrying_after_timeout_does_not_create_duplicates(mock_google_cal):
    """Verify that retrying an event creation request reuses the existing verified event."""
    initial_insert_count = mock_google_cal.insert_count

    # First attempt
    res1 = create_event(
        title="AI Project Status Sync",
        start="2026-10-28 14:00:00",
        end="2026-10-28 15:00:00",
    )
    assert res1["status"] == "success"
    first_event_id = res1["event_id"]
    assert mock_google_cal.insert_count == initial_insert_count + 1

    # Second attempt (simulating timeout retry)
    res2 = create_event(
        title="AI Project Status Sync",
        start="2026-10-28 14:00:00",
        end="2026-10-28 15:00:00",
    )
    assert res2["status"] == "success"
    assert res2["event_id"] == first_event_id
    assert res2.get("duplicate_prevented") is True
    # Crucial assertion: Google API insert was NOT called a second time
    assert mock_google_cal.insert_count == initial_insert_count + 1

    delete_event(first_event_id)


# ==============================================================================
# Requirement 7: Local reminders and Google Calendar events are clearly distinguished
# ==============================================================================

def test_regression_7_local_and_google_clearly_distinguished():
    """Verify that when Google Calendar is unconfigured, results clearly state they are local only."""
    # When Google Calendar is unconfigured (mocking None)
    with patch("mcp_servers.google_services_server._get_google_service") as mock_get:
        mock_get.return_value = (None, {"status": "unconfigured", "message": "Credentials missing"})

        # Local reminder
        rem_res = create_reminder(
            title="Local Toast Alarm",
            due_datetime="2026-10-28 16:00:00",
        )
        assert rem_res["status"] == "success"
        assert rem_res["provider"] == "local_reminder"
        assert "Google Calendar is not configured" in rem_res["message"]
        assert "Local desktop reminder" in rem_res["message"]
        delete_reminder(rem_res["reminder_id"])

        # Local calendar event
        cal_res = create_event(
            title="Local Calendar Event",
            start="2026-10-28 17:00:00",
        )
        assert cal_res["status"] == "success"
        assert cal_res["provider"] == "local_calendar"
        assert "Google Calendar is not configured" in cal_res["message"]
        assert "Scheduled as a local calendar reminder" in cal_res["message"]
        delete_event(cal_res["event_id"])
