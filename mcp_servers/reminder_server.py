"""
==============================================================================
MCP Server: reminder_server.py
Domain: Task Scheduling & Desktop Notifications
Protocol: Model Context Protocol (FastMCP) over stdio
==============================================================================
Provides tools to schedule alarms and reminders:
- `create_reminder`: Schedules a background alert and desktop notification.
- `list_reminders`: Returns all active and scheduled student reminders.
- `delete_reminder`: Cancels and removes a reminder by ID.

Technical Stack:
- APScheduler: Non-blocking in-process background job scheduler.
- Plyer: OS-native desktop notification abstraction (Windows Toast).
- SQLite: Persistent state storage in `db/assistant.db`.
"""

from __future__ import annotations
import datetime
import sqlite3
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from apscheduler.schedulers.background import BackgroundScheduler
import plyer

from mcp_servers.db import get_db_connection

# Initialize FastMCP Server
mcp = FastMCP("reminder_server")

# Global Background Scheduler
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """Lazy initializer for background thread scheduler."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    return _scheduler


def trigger_desktop_notification(reminder_id: int, title: str, note: str) -> None:
    """Callback fired by APScheduler when reminder due timestamp is reached."""
    print(f"\n[ALARM FIRED] Reminder #{reminder_id}: {title} - {note}")
    try:
        plyer.notification.notify(
            title=f"Assistant Reminder: {title}",
            message=note or "Your scheduled reminder is due now!",
            app_name="RAG-MCP Assistant",
            timeout=10,
        )
    except Exception as e:
        print(f"[NOTIFICATION WARNING] Desktop notification error: {e}")

    # Mark as completed in SQLite
    try:
        conn = get_db_connection()
        conn.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Could not update reminder #{reminder_id} status: {e}")


def parse_datetime(dt_str: str) -> datetime.datetime:
    """
    Parses flexible date/time strings into a timezone-naive datetime object.
    Supports formats:
      - 2026-03-14T10:00:00
      - 2026-03-14 10:00:00
      - 2026-03-14 10:00
      - 2026-03-14
    """
    dt_clean = dt_str.strip().replace("T", " ")
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(dt_clean, fmt)
        except ValueError:
            continue
    # Fallback to ISO format parsing
    return datetime.datetime.fromisoformat(dt_clean)


@mcp.tool()
def create_reminder(title: str, due_datetime: str, note: str = "") -> Dict[str, Any]:
    """
    Creates a new reminder and schedules a desktop notification at the due time.

    Args:
        title: Short summary of the reminder (e.g. "Revise OS Unit 3").
        due_datetime: When the reminder should trigger (e.g. "2026-03-14 18:00:00").
        note: Optional extra details or notes.

    Returns:
        Confirmation dictionary with reminder ID, title, and scheduled time.
    """
    try:
        target_dt = parse_datetime(due_datetime)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid datetime format '{due_datetime}'. Please use 'YYYY-MM-DD HH:MM:SS'. Details: {e}",
        }

    # 1. Save to SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (title, due_datetime, note, status) VALUES (?, ?, ?, 'pending')",
        (title, target_dt.strftime("%Y-%m-%d %H:%M:%S"), note),
    )
    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # 2. Schedule alert with APScheduler
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    
    # If the time is in the future, schedule job; if in the past, schedule for 2 seconds from now
    run_date = target_dt
    if run_date <= datetime.datetime.now():
        run_date = datetime.datetime.now() + datetime.timedelta(seconds=2)

    scheduler.add_job(
        trigger_desktop_notification,
        "date",
        run_date=run_date,
        args=[reminder_id, title, note],
        id=job_id,
        replace_existing=True,
    )

    return {
        "status": "success",
        "action": "create_reminder",
        "reminder_id": reminder_id,
        "title": title,
        "due_datetime": target_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "message": f"Reminder '{title}' successfully scheduled for {target_dt.strftime('%Y-%m-%d %H:%M:%S')}.",
    }


@mcp.tool()
def list_reminders(status_filter: str = "all") -> List[Dict[str, Any]]:
    """
    Lists reminders stored in the assistant database.

    Args:
        status_filter: "all", "pending", or "completed".

    Returns:
        List of reminder records.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if status_filter.lower() in ("pending", "completed"):
        cursor.execute("SELECT * FROM reminders WHERE status = ? ORDER BY due_datetime ASC", (status_filter.lower(),))
    else:
        cursor.execute("SELECT * FROM reminders ORDER BY due_datetime ASC")

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


@mcp.tool()
def delete_reminder(reminder_id: int) -> Dict[str, Any]:
    """
    Cancels and removes a reminder by ID.

    Args:
        reminder_id: Integer ID of the reminder to cancel.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    # Remove from scheduler
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if deleted > 0:
        return {"status": "success", "action": "delete_reminder", "reminder_id": reminder_id, "message": f"Reminder #{reminder_id} canceled and deleted."}
    return {"status": "not_found", "action": "delete_reminder", "reminder_id": reminder_id, "message": f"Reminder #{reminder_id} not found."}


if __name__ == "__main__":
    # Standard MCP stdio entry point
    mcp.run()
