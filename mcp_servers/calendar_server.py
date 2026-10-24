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
    end: str,
    attendees: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """
    Creates a calendar event, persists it in SQLite, and generates an .ics iCalendar file.

    Args:
        title: Title of the event (e.g. "CS402 Internal Exam 2").
        start: Start date and time (e.g. "2026-03-14 10:00:00").
        end: End date and time (e.g. "2026-03-14 12:00:00").
        attendees: Comma-separated list of attendees or email addresses.
        description: Detailed description or venue information.

    Returns:
        Event details including database ID and path to the generated .ics file.
    """
    try:
        norm_start = parse_event_datetime(start)
        norm_end = parse_event_datetime(end)
    except Exception as e:
        return {"status": "error", "message": f"Invalid date format: {e}"}

    # 1. Save to SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO calendar_events (title, start_datetime, end_datetime, attendees, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, norm_start, norm_end, attendees, description),
    )
    event_id = cursor.lastrowid

    # 2. Generate standard RFC 5545 .ics file using ics library
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
    except Exception as e:
        # Fallback raw RFC 5545 format if library serialization encounters any issue
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

    # Update database with .ics file path
    cursor.execute("UPDATE calendar_events SET ics_path = ? WHERE id = ?", (str(ics_path), event_id))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "action": "create_event",
        "event_id": event_id,
        "title": title,
        "start": norm_start,
        "end": norm_end,
        "attendees": attendees,
        "description": description,
        "ics_path": str(ics_path),
        "message": f"Event '{title}' scheduled. iCalendar file saved to {ics_path.name}.",
    }


@mcp.tool()
def list_events(date_range: str = "all") -> List[Dict[str, Any]]:
    """
    Lists calendar events from the assistant database.

    Args:
        date_range: Optional filter ("all", or specific date "YYYY-MM-DD").

    Returns:
        List of event records with their .ics file locations.
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

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@mcp.tool()
def delete_event(event_id: int) -> Dict[str, Any]:
    """
    Deletes a calendar event and deletes its .ics file from disk.

    Args:
        event_id: Integer ID of the event to delete.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ics_path FROM calendar_events WHERE id = ?", (event_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"status": "not_found", "event_id": event_id, "message": f"Event #{event_id} not found."}

    ics_path_str = row["ics_path"]
    cursor.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
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
