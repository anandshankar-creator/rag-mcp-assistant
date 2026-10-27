import sys
import json
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from mcp_servers.client import get_mcp_client
from mcp_servers.pdf_server import generate_pdf
from mcp_servers.reminder_server import create_reminder
from mcp_servers.email_server import send_email

def inspect_phase5_mcp():
    results = {}

    # 1. MCP Servers and Tools Discovery
    mcp_client = get_mcp_client()
    tools = mcp_client.get_tool_definitions()
    results["discovered_tools_count"] = len(tools)
    results["tools"] = [{"name": t["name"], "description": t["description"][:100]} for t in tools]

    # 2. PDF Creation Verification
    pdf_res = generate_pdf(
        title="Audit Test Academic Notes",
        content="## Module 1: OS Concepts\n- Process Synchronization\n- Critical Section Problem\n- Peterson's Solution",
        filename="audit_test_academic_notes.pdf"
    )
    results["pdf_generation_receipt"] = pdf_res
    pdf_path = Path(pdf_res.get("file_path", ""))
    results["pdf_file_exists"] = pdf_path.exists()
    results["pdf_file_size_bytes"] = pdf_path.stat().st_size if pdf_path.exists() else 0
    if pdf_path.exists():
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            results["valid_pdf_magic_bytes"] = (header == b"%PDF-")
    else:
        results["valid_pdf_magic_bytes"] = False

    # 3. Persistence Verification across DB Reconnect
    test_title = "Audit Persistence Check Reminder"
    db_path = settings.SQLITE_DB_PATH
    
    # Insert via tool
    rem_res = create_reminder(
        title=test_title,
        due_datetime="2026-11-15 10:00:00",
        note="Verifying SQLite disk persistence across connection closures",
    )
    results["reminder_creation_receipt"] = rem_res
    rem_id = rem_res.get("reminder_id")

    # Simulate restart by establishing an entirely new independent connection
    conn2 = sqlite3.connect(str(db_path))
    conn2.row_factory = sqlite3.Row
    cur2 = conn2.cursor()
    cur2.execute("SELECT * FROM reminders WHERE id = ?", (rem_id,))
    row = cur2.fetchone()
    conn2.close()

    results["persisted_reminder_found"] = bool(row)
    if row:
        results["persisted_reminder_data"] = dict(row)

    # 4. Failure Handling Verification (Anti-False-Success)
    # A. Unconfirmed email
    unconfirmed = send_email(to="test@example.com", subject="Test", body="Body", confirmed=False)
    results["failure_handling_unconfirmed_email"] = {
        "status": unconfirmed.get("status"),
        "error_prevented_success": unconfirmed.get("status") == "error",
        "requires_confirmation": unconfirmed.get("requires_confirmation", False)
    }

    # B. Missing attachment
    missing_att = send_email(to="test@example.com", subject="Test", body="Body", attachment_path="nonexistent_audit_file.xyz", confirmed=True)
    results["failure_handling_missing_attachment"] = {
        "status": missing_att.get("status"),
        "error_prevented_success": missing_att.get("status") == "error",
        "message": missing_att.get("message")
    }

    # Save to file
    out_file = Path("D:/rag-mcp-assistant/audit/phase5_mcp_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    inspect_phase5_mcp()
