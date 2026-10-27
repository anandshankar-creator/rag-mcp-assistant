"""
==============================================================================
Script: test_phase3.py
Role: Phase 3 Automated Verification & Standalone Server Test Harness
==============================================================================
Validates:
1. `reminder_server`: create, list, and delete reminders.
2. `calendar_server`: create event, verify .ics generation, list, and delete event.
3. `email_server`: preview email (HITL) and send email (simulation/live).
4. `pdf_server`: generate formatted PDF and verify on-disk compilation.
5. `mcp_servers.client`: dynamic tool discovery and tool dispatch.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_servers.reminder_server import create_reminder, list_reminders, delete_reminder
from mcp_servers.calendar_server import create_event, list_events, delete_event
from mcp_servers.email_server import preview_email, send_email
from mcp_servers.pdf_server import generate_pdf
from mcp_servers.client import get_mcp_client


def test_reminder_server():
    print("\n--- 1. Testing Reminder Server ---")
    res = create_reminder(
        title="Revise Virtual Memory Paging",
        due_datetime="2026-03-14 18:00:00",
        note="Focus on Belady's Anomaly and LRU stack implementation",
    )
    print(f"create_reminder output: {res.get('message')}")
    assert res.get("status") == "success", f"create_reminder failed: {res}"
    rem_id = res["reminder_id"]

    all_rems = list_reminders()
    print(f"list_reminders count: {len(all_rems)}")
    assert any(r["id"] == rem_id for r in all_rems), "Created reminder not found in list."

    del_res = delete_reminder(rem_id)
    print(f"delete_reminder output: {del_res.get('message')}")
    assert del_res.get("status") == "success"
    print("Reminder server PASSED.")


def test_calendar_server():
    print("\n--- 2. Testing Calendar Server & .ics Generation ---")
    res = create_event(
        title="CS402 Operating Systems Internal 2",
        start="2026-03-14 10:00:00",
        end="2026-03-14 12:00:00",
        attendees="alex.student@ktu.edu.in, radhika.prof@ktu.edu.in",
        description="Internal Exam 2 covering Modules 3 and 4 in Room 304.",
    )
    print(f"create_event output: {res.get('message')}")
    assert res.get("status") == "success", f"create_event failed: {res}"
    event_id = res["event_id"]
    ics_file = Path(res["ics_path"])

    assert ics_file.exists(), f"Generated .ics file not found: {ics_file}"
    ics_size = ics_file.stat().st_size
    print(f"Verified .ics file: {ics_file.name} ({ics_size} bytes)")
    assert ics_size > 50, ".ics file is suspiciously small."

    all_events = list_events()
    print(f"list_events count: {len(all_events)}")
    assert any(e["id"] == event_id for e in all_events), "Event not found in list."

    del_res = delete_event(event_id)
    print(f"delete_event output: {del_res.get('message')}")
    assert del_res.get("status") == "success"
    assert not ics_file.exists(), "Deleted event's .ics file was not cleaned up."
    print("Calendar server PASSED.")


def test_email_server():
    print("\n--- 3. Testing Email Server & Human-in-the-Loop Preview ---")
    preview = preview_email(
        to="prof.radhika@ktu.edu.in",
        subject="Assignment Submission - CS402 Operating Systems",
        body="Dear Professor, please find attached my module notes summary.",
        attachment_path=None,
    )
    print(f"preview_email output: To={preview.get('to')} | Valid={preview.get('valid_recipient')}")
    assert preview.get("valid_recipient") is True
    assert preview.get("requires_confirmation") is True

    # Test unconfirmed send (must be safely rejected by HITL guard)
    unconfirmed_res = send_email(
        to="student@ktu.edu.in",
        subject="Test Alert",
        body="This is an automated test from RAG-MCP Assistant.",
        confirmed=False,
    )
    print(f"unconfirmed send_email output: {unconfirmed_res.get('message')}")
    assert unconfirmed_res.get("status") == "error"
    assert "confirmation is required" in unconfirmed_res.get("message", "").lower()

    # Test confirmed send (either live SMTP success or unconfigured diagnostic)
    send_res = send_email(
        to="student@ktu.edu.in",
        subject="Test Alert",
        body="This is an automated test from RAG-MCP Assistant.",
        confirmed=True,
    )
    print(f"confirmed send_email output: {send_res.get('message')}")
    assert send_res.get("status") in ("success", "error")
    if send_res.get("status") == "error":
        assert send_res.get("mode") == "unconfigured"
    print("Email server PASSED.")


def test_pdf_server():
    print("\n--- 4. Testing PDF Server (ReportLab Document Compilation) ---")
    markdown_content = (
        "# Operating Systems: Module 3 Quick Revision\n\n"
        "## Key Topics\n"
        "- Demand Paging mechanism and Page Fault Trap sequence\n"
        "- **Belady's Anomaly**: FIFO frame increase causing fault spike\n"
        "- Least Recently Used (LRU) stack and counter architectures\n"
        "- Thrashing and Peter Denning's Working Set Model\n\n"
        "## Important Formulae\n"
        "Total frame demand: D = sum(WSS_i). If D > m, system undergoes thrashing."
    )
    res = generate_pdf(
        title="CS402 Module 3 Revision Sheet",
        content=markdown_content,
        filename="CS402_Module3_Revision.pdf",
    )
    print(f"generate_pdf output: {res.get('message')}")
    assert res.get("status") == "success", f"generate_pdf failed: {res}"
    pdf_path = Path(res["file_path"])
    assert pdf_path.exists(), f"Compiled PDF not found: {pdf_path}"
    print(f"Verified PDF file on disk: {pdf_path.name} ({pdf_path.stat().st_size} bytes)")
    assert pdf_path.stat().st_size > 1000
    print("PDF server PASSED.")


def test_mcp_client_controller():
    print("\n--- 5. Testing Dynamic Tool Discovery via MCP Client Controller ---")
    client = get_mcp_client()
    tools = client.get_tool_definitions()
    print(f"Total tools discovered dynamically: {len(tools)}")
    tool_names = [t["name"] for t in tools]
    print(f"Discovered Tool Names: {tool_names}")

    expected_tools = [
        "create_reminder",
        "list_reminders",
        "delete_reminder",
        "create_event",
        "list_events",
        "delete_event",
        "preview_email",
        "send_email",
        "generate_pdf",
    ]
    for exp in expected_tools:
        assert exp in tool_names, f"Expected tool '{exp}' not discovered dynamically!"

    # Test executing a tool through the MCP Client Controller interface
    print("Testing dynamic execution through MCP Client Controller...")
    dispatch_res = client.execute_tool(
        tool_name="generate_pdf",
        arguments={
            "title": "Dynamic Tool Dispatch Verification",
            "content": "This PDF was compiled through dynamic MCP client routing.",
            "filename": "mcp_client_verification.pdf",
        },
    )
    assert dispatch_res.get("status") == "success", f"Dynamic tool dispatch failed: {dispatch_res}"
    print(f"Dynamic Tool Dispatch output: {dispatch_res.get('result', {}).get('message')}")
    print("MCP Client Controller PASSED.")


if __name__ == "__main__":
    print("==================================================================")
    print("  RUNNING PHASE 3 VERIFICATION: MCP TOOL SERVERS & CONTROLLER")
    print("==================================================================")
    try:
        test_reminder_server()
        test_calendar_server()
        test_email_server()
        test_pdf_server()
        test_mcp_client_controller()
        print("\n==================================================================")
        print("  ALL PHASE 3 CHECKS PASSED SUCCESSFULLY!")
        print("==================================================================")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        sys.exit(1)
