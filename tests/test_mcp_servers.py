"""
==============================================================================
Test Suite: FastMCP Tool Servers & Dynamic Discovery Client
==============================================================================
Validates:
1. reminder_server: create, list, and delete SQLite reminders.
2. calendar_server: create RFC 5545 .ics calendar event, list, and delete.
3. email_server: preview email (Human-in-the-Loop token) and send email.
4. pdf_server: compile structured document into PDF via ReportLab.
5. client.py: dynamic runtime discovery of all 9 MCP tools.
"""

import datetime
from pathlib import Path
import pytest

from mcp_servers.reminder_server import create_reminder, list_reminders, delete_reminder
from mcp_servers.calendar_server import create_event, list_events, delete_event
from mcp_servers.email_server import preview_email, send_email
from mcp_servers.pdf_server import generate_pdf
from mcp_servers.client import get_mcp_client


def test_reminder_mcp_lifecycle():
    """Verify create, list, and delete on reminder_server."""
    future_dt = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%Y-%m-%d 10:00:00")
    res = create_reminder(
        title="Unit Test Reminder",
        due_datetime=future_dt,
        note="Pytest automated reminder check",
    )
    assert res.get("status") == "success"
    rem_id = res.get("reminder_id")
    assert rem_id is not None

    rems = list_reminders()
    assert any(r["id"] == rem_id for r in rems)

    del_res = delete_reminder(rem_id)
    assert del_res.get("status") == "success"


def test_reminder_rejects_past_date():
    """Verify reminder server strictly rejects due dates in the past."""
    res = create_reminder(
        title="Past Reminder",
        due_datetime="2020-01-01 10:00:00",
        note="Should fail",
    )
    assert res.get("status") == "error"
    assert "Cannot schedule reminder in the past" in res.get("message", "")


def test_reminder_tomorrow_at_6pm():
    """Verify scheduling for tomorrow at 6 PM."""
    tomorrow_6pm = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d 18:00:00")
    res = create_reminder(
        title="Revise Unit 3",
        due_datetime=tomorrow_6pm,
        note="Study revision",
    )
    assert res.get("status") == "success"
    rem_id = res.get("reminder_id")
    assert rem_id is not None
    # Cleanup
    delete_reminder(rem_id)


def test_reminder_day_before_exam_grounding():
    """Verify chained executor derives 'day before the exam' from timetable text."""
    from agents.graph import executor_node, AgentState

    state: AgentState = {
        "session_id": "test_exam_reminder",
        "user_message": "Check my exam date and remind me the day before the CS402 internal exam",
        "plan": [
            {
                "step": 1,
                "action": "rag_retrieve",
                "description": "Check CS402 internal exam date",
                "args": {"query": "When is the CS402 internal exam?"},
            },
            {
                "step": 2,
                "action": "create_reminder",
                "description": "Set reminder on the day before the CS402 internal exam",
                "args": {"title": "CS402 Exam Tomorrow - Final Revision"},
            },
        ],
        "user_preferences": {},
        "user_confirmed_actions": False,
    }

    result = executor_node(state)
    assert len(result["action_receipts"]) == 1
    receipt = result["action_receipts"][0]["receipt"]
    assert receipt["status"] == "success"
    # Exam is on 14 November 2026 -> day before is 2026-11-13
    assert receipt.get("arguments", {}).get("due_datetime") == "2026-11-13 18:00:00"
    
    # Cleanup
    rem_id = receipt.get("result", {}).get("reminder_id")
    if rem_id:
        delete_reminder(rem_id)


def test_calendar_mcp_lifecycle():
    """Verify create, .ics file generation, list, and delete on calendar_server."""
    res = create_event(
        title="Pytest Review Meeting",
        start="2026-03-25 09:30:00",
        end="2026-03-25 11:30:00",
        attendees="student@ktu.ac.in",
        description="Viva preparation event",
    )
    assert res.get("status") == "success"
    event_id = res.get("event_id")
    ics_path = res.get("ics_path")
    assert event_id is not None
    assert ics_path is not None
    assert Path(ics_path).exists(), f"Generated .ics file not found at {ics_path}"

    events = list_events()
    assert any(e["id"] == event_id for e in events)

    del_res = delete_event(event_id)
    assert del_res.get("status") == "success"


def test_email_mcp_hitl_and_send():
    """Verify Human-in-the-Loop preview and confirmation safeguards."""
    preview = preview_email(
        to="hod.cse@gec.ac.in",
        subject="Project Phase 1 Submission",
        body="Dear Professor, please find the project report attached.",
    )
    assert preview.get("status") == "ready_for_confirmation"
    assert preview.get("requires_confirmation") is True
    assert preview.get("to") == "hod.cse@gec.ac.in"

    # 1. Unconfirmed send MUST fail with explicit confirmation error
    unconfirmed_res = send_email(
        to="hod.cse@gec.ac.in",
        subject="Project Phase 1 Submission",
        body="Report body",
        confirmed=False,
    )
    assert unconfirmed_res.get("status") == "error"
    assert "confirmation is required" in unconfirmed_res.get("message", "").lower()

    # 2. Confirmed send with unconfigured credentials returns honest unconfigured error
    confirmed_res = send_email(
        to="hod.cse@gec.ac.in",
        subject="Project Phase 1 Submission",
        body="Report body",
        confirmed=True,
    )
    assert confirmed_res.get("status") == "error"
    assert "not configured" in confirmed_res.get("message", "").lower()


def test_pdf_mcp_generation():
    """Verify PDF compilation using ReportLab in outputs directory."""
    res = generate_pdf(
        title="Pytest Academic Summary",
        content="## Module 3 Notes\n- Demand Paging\n- Belady's Anomaly",
        filename="test_academic_summary.pdf",
    )
    assert res.get("status") == "success"
    pdf_path = res.get("file_path")
    assert pdf_path is not None
    assert Path(pdf_path).exists()
    assert Path(pdf_path).stat().st_size > 0


def test_dynamic_mcp_discovery():
    """Verify MCP client dynamically discovers all 9 tools across the 4 servers."""
    client = get_mcp_client()
    tools = client.get_tool_definitions()
    tool_names = {t["name"] for t in tools}

    expected_tools = {
        "create_reminder",
        "list_reminders",
        "delete_reminder",
        "create_event",
        "list_events",
        "delete_event",
        "preview_email",
        "send_email",
        "generate_pdf",
    }
    assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"
