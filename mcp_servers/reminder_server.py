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
from zoneinfo import ZoneInfo
from mcp.server.fastmcp import FastMCP
from apscheduler.schedulers.background import BackgroundScheduler
import plyer

from app.config import settings
from mcp_servers.db import get_db_connection
from mcp_servers.google_services_server import (
    _get_google_service,
    sync_create_google_calendar_event,
    parse_and_localize_datetime,
)

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
    Creates a new reminder, syncs to Google Calendar (if configured) with read-back verification,
    and schedules a local desktop notification at the due time.

    Args:
        title: Short summary of the reminder (e.g. "Revise OS Unit 3").
        due_datetime: When the reminder should trigger (e.g. "2026-10-28 09:00:00" in Asia/Kolkata).
        note: Optional extra details or notes.

    Returns:
        Confirmation dictionary with reminder ID, title, and scheduled time.
    """
    tz_name = getattr(settings, "TIMEZONE", "Asia/Kolkata")
    try:
        target_dt = parse_and_localize_datetime(due_datetime, default_time="09:00:00", tz_name=tz_name)
        norm_due = target_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid datetime format '{due_datetime}'. Please use 'YYYY-MM-DD HH:MM:SS'. Details: {e}",
        }

    now = datetime.datetime.now(ZoneInfo(tz_name))
    if target_dt < now:
        return {
            "status": "error",
            "message": f"Cannot schedule reminder in the past: '{due_datetime}' is earlier than the current time ({now.strftime('%Y-%m-%d %H:%M:%S')}).",
        }

    # Attempt Google Calendar creation & independent read-back verification
    g_res = sync_create_google_calendar_event(
        title=f"Reminder: {title}",
        start_time=norm_due,
        description=note or f"Reminder: {title}",
        target_calendar_id="primary",
    )

    # CRITICAL: If Google Calendar is authenticated but encountered an API/read-back error,
    # DO NOT report false success!
    if g_res.get("status") == "error":
        return {
            "status": "error",
            "provider": "google_calendar",
            "message": g_res.get("message", "Failed to create/verify Google Calendar reminder."),
        }

    is_google_synced = (g_res.get("status") == "success")
    g_event_id = g_res.get("event_id", "") if is_google_synced else ""
    cal_id = g_res.get("calendar_id", "") if is_google_synced else ""

    # 1. Save to SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (title, due_datetime, note, status, google_event_id, calendar_id) VALUES (?, ?, ?, 'pending', ?, ?)",
        (title, norm_due, note, g_event_id, cal_id),
    )
    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # 2. Schedule alert with APScheduler (using naive dt matching scheduler convention)
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    run_date = target_dt.replace(tzinfo=None)

    try:
        scheduler.add_job(
            trigger_desktop_notification,
            "date",
            run_date=run_date,
            args=[reminder_id, title, note],
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        print(f"[SCHEDULER WARNING] Could not add in-process job: {e}")

    if is_google_synced:
        return {
            "status": "success",
            "action": "create_reminder",
            "provider": "google_calendar",
            "reminder_id": reminder_id,
            "google_event_id": g_event_id,
            "calendar_id": cal_id,
            "calendar_name": g_res.get("calendar_name", cal_id),
            "title": title,
            "due_datetime": norm_due,
            "timezone": tz_name,
            "note": note,
            "verified": True,
            "duplicate_prevented": g_res.get("duplicate_prevented", False),
            "message": f"Reminder '{title}' successfully scheduled for {norm_due} ({tz_name}) and verified on Google Calendar '{cal_id}'. (Event ID: {g_event_id})",
        }
    else:
        return {
            "status": "success",
            "action": "create_reminder",
            "provider": "local_reminder",
            "reminder_id": reminder_id,
            "title": title,
            "due_datetime": norm_due,
            "note": note,
            "message": f"Local desktop reminder '{title}' successfully scheduled for {norm_due}. (Note: Stored locally in assistant database; Google Calendar is not configured.)",
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
def delete_reminder(reminder_id: Any) -> Dict[str, Any]:
    """
    Cancels and removes a reminder by ID. Also removes from Google Calendar if synced.

    Args:
        reminder_id: Integer ID or Google Calendar string event ID to cancel.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    row = None

    try:
        int_id = int(reminder_id)
        cursor.execute("SELECT * FROM reminders WHERE id = ?", (int_id,))
        row = cursor.fetchone()
    except (ValueError, TypeError):
        pass

    if not row:
        cursor.execute("SELECT * FROM reminders WHERE google_event_id = ?", (str(reminder_id),))
        row = cursor.fetchone()

    # If Google Calendar is authenticated, delete from Google Calendar
    g_id = ""
    if row and "google_event_id" in row.keys() and row["google_event_id"]:
        g_id = row["google_event_id"]
    elif not str(reminder_id).isdigit():
        g_id = str(reminder_id)

    if g_id:
        service, _ = _get_google_service("calendar", "v3")
        if service:
            try:
                service.events().delete(calendarId="primary", eventId=g_id).execute()
            except Exception:
                pass

    if row:
        db_id = row["id"]
        cursor.execute("DELETE FROM reminders WHERE id = ?", (db_id,))
        deleted = cursor.rowcount
        conn.commit()
        # Remove from scheduler
        scheduler = get_scheduler()
        job_id = f"reminder_{db_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    else:
        deleted = 0

    conn.close()

    if deleted > 0:
        return {"status": "success", "action": "delete_reminder", "reminder_id": reminder_id, "message": f"Reminder #{reminder_id} canceled and deleted."}
    return {"status": "not_found", "action": "delete_reminder", "reminder_id": reminder_id, "message": f"Reminder #{reminder_id} not found."}


if __name__ == "__main__":
    # Standard MCP stdio entry point
    mcp.run()
