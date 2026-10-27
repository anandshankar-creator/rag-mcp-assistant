"""
==============================================================================
MCP Server: calendar_server.py
Domain: Calendar Event Management & RFC 5545 iCalendar (.ics) Generation
Protocol: Model Context Protocol (FastMCP) over stdio
==============================================================================
Provides tools to manage student timetable and personal calendar events:
- `create_event`: Saves event to SQLite and writes a double-clickable .ics file.
- `list_events`: Lists upcoming scheduled events.
- `delete_event`: Cancels event and removes its .ics file.

Academic Review Rationale:
Standards-compliant .ics generation allows the assistant to integrate with ANY
calendar application (Google Calendar, Apple Calendar, Microsoft Outlook)
without needing vendor-specific OAuth token configurations or cloud lock-in.
"""

from __future__ import annotations
import datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
import ics

from app.config import settings
from mcp_servers.db import get_db_connection
from mcp_servers.google_services_server import (
    _get_google_service,
    sync_create_google_calendar_event,
    google_calendar_list_events,
    parse_and_localize_datetime,
)

mcp = FastMCP("calendar_server")

# Directory where generated .ics files are stored
EVENTS_DIR = settings.OUTPUTS_DIR / "events"
EVENTS_DIR.mkdir(parents=True, exist_ok=True)


def parse_event_datetime(dt_str: str) -> str:
    """Normalizes date string to YYYY-MM-DD HH:MM:SS format."""
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
            dt = datetime.datetime.strptime(dt_clean, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # Try ISO
    dt = datetime.datetime.fromisoformat(dt_clean)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def create_event(
    title: str,
    start: str,
    end: str = "",
    attendees: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """
    Creates a calendar event on Google Calendar (if configured) with read-back verification,
    persists it in SQLite, and generates an .ics iCalendar file.

    Args:
        title: Title of the event (e.g. "CS402 Internal Exam 2").
        start: Start date and time (e.g. "2026-10-28 09:00:00" in Asia/Kolkata).
        end: End date and time (defaults to 1 hour after start).
        attendees: Comma-separated list of attendees or email addresses.
        description: Detailed description or venue information.

    Returns:
        Event details including verified Google event ID (if synced), local ID, and path to .ics file.
    """
    try:
        norm_start = parse_event_datetime(start)
        norm_end = parse_event_datetime(end) if end and end.strip() else ""
        if not norm_end or norm_end == norm_start:
            dt_s = datetime.datetime.strptime(norm_start, "%Y-%m-%d %H:%M:%S")
            norm_end = (dt_s + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return {"status": "error", "message": f"Invalid date format: {e}"}

    # Attempt Google Calendar creation & independent read-back verification
    g_res = sync_create_google_calendar_event(
        title=title,
        start_time=start,
        end_time=end or norm_end,
        description=description,
        attendees=attendees,
        target_calendar_id="primary",
    )

    # CRITICAL: If Google Calendar is authenticated but encountered an API/read-back error,
    # DO NOT report false success!
    if g_res.get("status") == "error":
        return {
            "status": "error",
            "provider": "google_calendar",
            "message": g_res.get("message", "Failed to create/verify Google Calendar event."),
        }

    is_google_synced = (g_res.get("status") == "success")
    g_event_id = g_res.get("event_id", "") if is_google_synced else ""
    cal_id = g_res.get("calendar_id", "") if is_google_synced else ""

    # Save to SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO calendar_events (title, start_datetime, end_datetime, attendees, description, google_event_id, calendar_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (title, norm_start, norm_end, attendees, description, g_event_id, cal_id),
    )
    event_id = cursor.lastrowid

    # Generate standard RFC 5545 .ics file using ics library
    slug = re.sub(r"[^\w\-]", "_", title.lower())[:30]
    ics_filename = f"event_{event_id}_{slug}.ics"
    ics_path = EVENTS_DIR / ics_filename

    try:
        cal = ics.Calendar()
        event = ics.Event()
        event.name = title
        event.begin = norm_start
        event.end = norm_end
        event.description = description
        if attendees:
            for att in attendees.split(","):
                clean_att = att.strip()
                if clean_att:
                    event.add_attendee(clean_att)

        cal.events.add(event)
        ics_content = cal.serialize()
        ics_path.write_text(ics_content, encoding="utf-8")
    except Exception:
        dt_start_clean = norm_start.replace("-", "").replace(":", "").replace(" ", "T")
        dt_end_clean = norm_end.replace("-", "").replace(":", "").replace(" ", "T")
        raw_ics = (
            "BEGIN:VCALENDAR\n"
            "VERSION:2.0\n"
            "PRODID:-//RAG-MCP Assistant//Student Calendar//EN\n"
            "BEGIN:VEVENT\n"
            f"UID:event_{event_id}@assistant.local\n"
            f"SUMMARY:{title}\n"
            f"DTSTART:{dt_start_clean}\n"
            f"DTEND:{dt_end_clean}\n"
            f"DESCRIPTION:{description}\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n"
        )
        ics_path.write_text(raw_ics, encoding="utf-8")

    cursor.execute("UPDATE calendar_events SET ics_path = ? WHERE id = ?", (str(ics_path), event_id))
    conn.commit()
    conn.close()

    if is_google_synced:
        return {
            "status": "success",
            "action": "create_event",
            "provider": "google_calendar",
            "event_id": g_event_id,
            "local_id": event_id,
            "calendar_id": cal_id,
            "calendar_name": g_res.get("calendar_name", cal_id),
            "title": title,
            "start": g_res.get("start", norm_start),
            "end": g_res.get("end", norm_end),
            "timezone": g_res.get("timezone", "Asia/Kolkata"),
            "attendees": attendees,
            "description": description,
            "html_link": g_res.get("html_link"),
            "ics_path": str(ics_path),
            "verified": True,
            "duplicate_prevented": g_res.get("duplicate_prevented", False),
            "message": g_res.get("message"),
        }
    else:
        return {
            "status": "success",
            "action": "create_event",
            "provider": "local_calendar",
            "event_id": event_id,
            "local_id": event_id,
            "title": title,
            "start": norm_start,
            "end": norm_end,
            "attendees": attendees,
            "description": description,
            "ics_path": str(ics_path),
            "message": f"Scheduled as a local calendar reminder: '{title}' for {norm_start}. (Note: Stored locally in assistant database; Google Calendar is not configured.)",
        }


@mcp.tool()
def list_events(date_range: str = "all") -> List[Dict[str, Any]]:
    """
    Lists calendar events from Google Calendar (if configured) and the assistant database.

    Args:
        date_range: Optional filter ("all", or specific date "YYYY-MM-DD").

    Returns:
        List of event records with their details.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if date_range != "all" and re.match(r"^\d{4}-\d{2}-\d{2}$", date_range.strip()):
        cursor.execute(
            "SELECT * FROM calendar_events WHERE start_datetime LIKE ? ORDER BY start_datetime ASC",
            (f"{date_range.strip()}%",),
        )
    else:
        cursor.execute("SELECT * FROM calendar_events ORDER BY start_datetime ASC")

    local_rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # If Google Calendar is authenticated, fetch and merge Google Calendar events
    g_res = google_calendar_list_events(max_results=20, date_range=date_range)
    if g_res.get("status") == "success":
        g_events = g_res.get("events", [])
        combined = []
        seen_summaries = set()
        for ge in g_events:
            combined.append({
                "id": ge.get("id"),
                "title": ge.get("summary"),
                "start": ge.get("start"),
                "end": ge.get("end"),
                "provider": "google_calendar",
                "html_link": ge.get("html_link"),
            })
            seen_summaries.add((ge.get("summary") or "").strip().lower())
        for le in local_rows:
            if (le.get("title") or "").strip().lower() not in seen_summaries:
                le_dict = dict(le)
                le_dict["provider"] = "local_calendar"
                combined.append(le_dict)
        return combined

    return local_rows


@mcp.tool()
def delete_event(event_id: Any) -> Dict[str, Any]:
    """
    Deletes a calendar event and its .ics file from disk. Also deletes from Google Calendar if synced.

    Args:
        event_id: Integer ID or Google Calendar string event ID to delete.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    row = None

    try:
        int_id = int(event_id)
        cursor.execute("SELECT * FROM calendar_events WHERE id = ?", (int_id,))
        row = cursor.fetchone()
    except (ValueError, TypeError):
        pass

    if not row:
        cursor.execute("SELECT * FROM calendar_events WHERE google_event_id = ?", (str(event_id),))
        row = cursor.fetchone()

    # If Google Calendar is authenticated, delete from Google Calendar
    g_id = ""
    if row and "google_event_id" in row.keys() and row["google_event_id"]:
        g_id = row["google_event_id"]
    elif not str(event_id).isdigit():
        g_id = str(event_id)

    if g_id:
        service, _ = _get_google_service("calendar", "v3")
        if service:
            try:
                service.events().delete(calendarId="primary", eventId=g_id).execute()
            except Exception:
                pass

    if not row:
        conn.close()
        return {"status": "not_found", "event_id": event_id, "message": f"Event #{event_id} not found."}

    ics_path_str = row["ics_path"]
    db_id = row["id"]
    cursor.execute("DELETE FROM calendar_events WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()

    # Delete file if exists
    if ics_path_str:
        p = Path(ics_path_str)
        if p.exists():
            p.unlink(missing_ok=True)

    return {"status": "success", "action": "delete_event", "event_id": event_id, "message": f"Event #{event_id} deleted."}


if __name__ == "__main__":
    mcp.run()
