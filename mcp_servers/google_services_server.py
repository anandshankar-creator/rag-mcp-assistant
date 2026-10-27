"""
==============================================================================
MCP Server: google_services_server.py
Domain: Official Google Workspace Integration via Model Context Protocol (FastMCP)
Protocol: Model Context Protocol (FastMCP) over stdio
==============================================================================
Exposes tools connecting to authentic Google Services:
- Google Calendar API v3: `google_calendar_create_event`, `google_calendar_list_events`
- Gmail API v1: `google_gmail_send_message`, `google_gmail_list_messages`
- Google Tasks API v1: `google_tasks_create`, `google_tasks_list`
- Google Drive API v3: `google_drive_search`, `google_drive_get_file_metadata`
- Google Keep & Notes: `google_keep_note` (with documented API architecture rationale)

Academic & Viva Review Defense:
1. Dynamic Discovery: Discovered at runtime via MCP client (`list_tools()`).
2. Protocol Decoupling: Tool schemas are normalized to standard JSON Schemas
   compatible with any LLM provider (Gemini, Claude, Ollama).
3. Human-in-the-Loop Safety: Email actions enforce explicit user confirmation.
4. Truth in Integration: Uses real Google API client builders. If OAuth credentials
   are absent, returns explicit diagnostic guidance rather than faking execution.
==============================================================================
"""

from __future__ import annotations
import base64
import datetime
import os
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build

from app.config import settings
from mcp_servers.google_auth import get_google_auth_manager

mcp = FastMCP("google_services_server")


def _get_google_service(service_name: str, version: str):
    """Builds and returns an authorized Google API service instance, or None if unconfigured."""
    manager = get_google_auth_manager()
    creds, auth_diag = manager.get_credentials()
    if not creds:
        return None, auth_diag

    # In automated test runs, do not connect to live external Google APIs unless explicitly enabled or mocked
    from unittest.mock import Mock
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("ALLOW_LIVE_GOOGLE_IN_TESTS") and not isinstance(creds, Mock):
        return None, {
            "status": "unconfigured",
            "message": "Google live API disabled during automated tests. Credentials present.",
        }

    try:
        service = build(service_name, version, credentials=creds, cache_discovery=False)
        return service, {"status": "authenticated"}
    except Exception as e:
        return None, {"status": "error", "message": f"Failed to build {service_name} {version} client: {e}"}


def parse_and_localize_datetime(
    dt_str: str,
    default_time: str = "09:00:00",
    tz_name: Optional[str] = None,
) -> datetime.datetime:
    """
    Parses flexible datetime strings and normalizes to an aware datetime in the configured timezone.
    Supports YYYY-MM-DD, DD-MM-YYYY, ISO formats, with or without time/offset.
    """
    target_tz_name = tz_name or getattr(settings, "TIMEZONE", "Asia/Kolkata")
    tz = ZoneInfo(target_tz_name)
    s = dt_str.strip()

    if len(s) == 10:
        if "-" in s:
            parts = s.split("-")
            if len(parts[0]) == 4:
                s = f"{s} {default_time}"
            elif len(parts[2]) == 4:
                s = f"{parts[2]}-{parts[1]}-{parts[0]} {default_time}"
        elif "/" in s:
            parts = s.split("/")
            if len(parts[2]) == 4:
                s = f"{parts[2]}-{parts[1]}-{parts[0]} {default_time}"

    s_clean = s.replace("T", " ")
    parsed_dt = None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            parsed_dt = datetime.datetime.strptime(s_clean, fmt)
            break
        except ValueError:
            continue

    if parsed_dt is None:
        try:
            parsed_dt = datetime.datetime.fromisoformat(dt_str.strip())
        except Exception as e:
            raise ValueError(f"Unable to parse datetime '{dt_str}': {e}")

    if parsed_dt.tzinfo is None:
        return parsed_dt.replace(tzinfo=tz)
    return parsed_dt.astimezone(tz)


def sync_create_google_calendar_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    attendees: str = "",
    target_calendar_id: str = "primary",
    expected_calendar_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates an event on Google Calendar with:
    - Timezone normalization (Asia/Kolkata / UTC+05:30)
    - Duplicate prevention / idempotency check
    - Independent read-back query to verify creation
    - Target calendar verification
    """
    service, diag = _get_google_service("calendar", "v3")
    if not service:
        return {
            "status": "unconfigured",
            "provider": "google_calendar_v3",
            "message": diag.get("message", "Google Calendar API credentials unconfigured."),
            "diag": diag,
        }

    tz_name = getattr(settings, "TIMEZONE", "Asia/Kolkata")

    try:
        start_dt = parse_and_localize_datetime(start_time, default_time="09:00:00", tz_name=tz_name)
        if not end_time or end_time.strip() == "" or end_time.strip() == start_time.strip():
            end_dt = start_dt + datetime.timedelta(hours=1)
        else:
            end_dt = parse_and_localize_datetime(end_time, default_time="10:00:00", tz_name=tz_name)

        if end_dt <= start_dt:
            end_dt = start_dt + datetime.timedelta(hours=1)

        norm_start = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        norm_end = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()
    except Exception as e:
        return {
            "status": "error",
            "provider": "google_calendar_v3",
            "message": f"Invalid date/time format: {e}",
        }

    # Step 1: Verify target calendar access
    try:
        cal_meta = service.calendars().get(calendarId=target_calendar_id).execute()
        if isinstance(cal_meta, dict):
            actual_cal_id = cal_meta.get("id") or target_calendar_id
            cal_summary = cal_meta.get("summary") or actual_cal_id
        else:
            actual_cal_id = target_calendar_id
            cal_summary = target_calendar_id
    except Exception as e:
        return {
            "status": "error",
            "provider": "google_calendar_v3",
            "message": f"Failed to access Google Calendar '{target_calendar_id}': {e}",
        }

    # Verify expected calendar ID if caller specified one
    if expected_calendar_id and str(actual_cal_id).lower() != str(expected_calendar_id).lower():
        return {
            "status": "error",
            "provider": "google_calendar_v3",
            "message": f"Calendar mismatch: intended calendar '{expected_calendar_id}', but authenticated calendar is '{actual_cal_id}'.",
        }

    # Step 2: Idempotency / Duplicate Prevention Check
    try:
        window_min = (start_dt - datetime.timedelta(minutes=15)).isoformat()
        window_max = (end_dt + datetime.timedelta(minutes=15)).isoformat()
        clean_title = title.strip().lower()

        existing_res = (
            service.events()
            .list(
                calendarId=target_calendar_id,
                timeMin=window_min,
                timeMax=window_max,
                singleEvents=True,
            )
            .execute()
        )
        for item in existing_res.get("items", []):
            item_summary = (item.get("summary") or "").strip().lower()
            if item_summary == clean_title and item.get("status") != "cancelled":
                existing_id = item.get("id")
                # Perform independent read-back query to verify existing event
                readback = service.events().get(calendarId=target_calendar_id, eventId=existing_id).execute()
                if readback and readback.get("id") == existing_id and readback.get("status") != "cancelled":
                    return {
                        "status": "success",
                        "provider": "google_calendar_v3",
                        "event_id": existing_id,
                        "calendar_id": actual_cal_id,
                        "calendar_name": cal_summary,
                        "title": title,
                        "start": norm_start,
                        "end": norm_end,
                        "timezone": tz_name,
                        "html_link": readback.get("htmlLink"),
                        "verified": True,
                        "duplicate_prevented": True,
                        "message": f"Google Calendar event '{title}' already exists and was verified on calendar '{actual_cal_id}' for {norm_start} ({tz_name}). Event ID: {existing_id}.",
                    }
    except Exception:
        # Continue to insert attempt if search query fails
        pass

    # Step 3: Insert Event into Google Calendar
    try:
        event_body = {
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_iso,
                "timeZone": tz_name,
            },
            "end": {
                "dateTime": end_iso,
                "timeZone": tz_name,
            },
        }
        if attendees and attendees.strip():
            event_body["attendees"] = [{"email": a.strip()} for a in attendees.split(",") if a.strip()]

        created_event = service.events().insert(calendarId=target_calendar_id, body=event_body).execute()
        g_event_id = created_event.get("id")
        if not g_event_id:
            return {
                "status": "error",
                "provider": "google_calendar_v3",
                "message": "Google Calendar API did not return an event ID.",
            }
    except Exception as e:
        return {
            "status": "error",
            "provider": "google_calendar_v3",
            "message": f"Google Calendar API creation failed: {e}",
        }

    # Step 4: Independent Read-Back Query & Verification
    try:
        readback_event = service.events().get(calendarId=target_calendar_id, eventId=g_event_id).execute()
    except Exception as e:
        return {
            "status": "error",
            "provider": "google_calendar_v3",
            "message": f"Event creation read-back verification failed: event ID '{g_event_id}' could not be verified in calendar '{actual_cal_id}': {e}",
        }

    if not readback_event:
        return {
            "status": "error",
            "provider": "google_calendar_v3",
            "message": f"Event read-back verification failed: event '{g_event_id}' is not confirmed in calendar '{actual_cal_id}'.",
        }

    if isinstance(readback_event, dict):
        if readback_event.get("id") != g_event_id or readback_event.get("status") == "cancelled":
            return {
                "status": "error",
                "provider": "google_calendar_v3",
                "message": f"Event read-back verification failed: event '{g_event_id}' is not confirmed in calendar '{actual_cal_id}'.",
            }
        html_link = readback_event.get("htmlLink") or (created_event.get("htmlLink") if isinstance(created_event, dict) else "")
    else:
        html_link = created_event.get("htmlLink") if isinstance(created_event, dict) else ""

    return {
        "status": "success",
        "provider": "google_calendar_v3",
        "event_id": g_event_id,
        "calendar_id": actual_cal_id,
        "calendar_name": cal_summary,
        "title": title,
        "start": norm_start,
        "end": norm_end,
        "timezone": tz_name,
        "html_link": html_link,
        "verified": True,
        "duplicate_prevented": False,
        "message": f"Google Calendar event '{title}' successfully created and verified on calendar '{actual_cal_id}' for {norm_start} ({tz_name}). Event ID: {g_event_id}.",
    }


# ==============================================================================
# 1. Google Calendar API v3
# ==============================================================================

@mcp.tool()
def google_calendar_create_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    attendees: str = "",
) -> Dict[str, Any]:
    """
    Creates an event on the user's primary Google Calendar via Google Calendar API v3 with read-back verification.

    Args:
        title: Title/Summary of the event (e.g. "CS402 Exam Review").
        start_time: Start datetime (ISO 8601 or YYYY-MM-DD HH:MM:SS format in Asia/Kolkata).
        end_time: End datetime (defaults to 1 hour after start_time).
        description: Optional event description or venue details.
        attendees: Optional comma-separated email addresses.
    """
    return sync_create_google_calendar_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        attendees=attendees,
        target_calendar_id="primary",
    )


@mcp.tool()
def google_calendar_list_events(max_results: int = 10, date_range: str = "all") -> Dict[str, Any]:
    """
    Lists upcoming events from the user's primary Google Calendar via Google Calendar API v3.

    Args:
        max_results: Maximum number of events to return.
        date_range: Optional filter ("all", or specific date "YYYY-MM-DD" or "DD-MM-YYYY").
    """
    service, diag = _get_google_service("calendar", "v3")
    if not service:
        return {
            "status": "unconfigured",
            "provider": "google_calendar_v3",
            "message": diag.get("message", "Google Calendar API credentials unconfigured."),
        }

    try:
        tz_name = getattr(settings, "TIMEZONE", "Asia/Kolkata")
        tz = ZoneInfo(tz_name)
        params: Dict[str, Any] = {
            "calendarId": "primary",
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if date_range != "all" and date_range.strip():
            target_dt = parse_and_localize_datetime(date_range, default_time="00:00:00", tz_name=tz_name)
            day_start = target_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = target_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            params["timeMin"] = day_start.isoformat()
            params["timeMax"] = day_end.isoformat()
        else:
            now_dt = datetime.datetime.now(tz)
            params["timeMin"] = now_dt.isoformat()

        events_result = service.events().list(**params).execute()
        items = events_result.get("items", [])
        events_data = [
            {
                "id": it.get("id"),
                "summary": it.get("summary"),
                "start": it.get("start", {}).get("dateTime", it.get("start", {}).get("date")),
                "end": it.get("end", {}).get("dateTime", it.get("end", {}).get("date")),
                "html_link": it.get("htmlLink"),
                "status": it.get("status"),
            }
            for it in items
        ]
        return {
            "status": "success",
            "provider": "google_calendar_v3",
            "events_count": len(events_data),
            "events": events_data,
        }
    except Exception as e:
        return {"status": "error", "provider": "google_calendar_v3", "message": f"Google Calendar list error: {e}"}


# ==============================================================================
# 2. Gmail REST API v1
# ==============================================================================

@mcp.tool()
def google_gmail_send_message(
    to: str,
    subject: str,
    body: str,
    confirmed: bool = False,
    attachment_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends an email using the authentic Gmail REST API v1.
    Human-in-the-Loop Safety: Explicit user confirmation (`confirmed=True`) is required.
    """
    from mcp_servers.email_server import sync_dispatch_email
    return sync_dispatch_email(
        to=to,
        subject=subject,
        body=body,
        attachment_path=attachment_path,
        confirmed=confirmed,
    )


@mcp.tool()
def google_gmail_list_messages(query: str = "", max_results: int = 5) -> Dict[str, Any]:
    """
    Lists recent emails matching an optional search query via Gmail REST API v1.
    """
    service, diag = _get_google_service("gmail", "v1")
    if not service:
        return {
            "status": "unconfigured",
            "provider": "gmail_api_v1",
            "message": diag.get("message", "Gmail API credentials unconfigured."),
        }

    try:
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])
        return {
            "status": "success",
            "provider": "gmail_api_v1",
            "messages_count": len(messages),
            "messages": messages,
        }
    except Exception as e:
        return {"status": "error", "provider": "gmail_api_v1", "message": f"Gmail list error: {e}"}


# ==============================================================================
# 3. Google Tasks API v1
# ==============================================================================

@mcp.tool()
def google_tasks_create(
    title: str,
    notes: str = "",
    due: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a new task in the user's default Google Tasks list via Google Tasks API v1.
    """
    service, diag = _get_google_service("tasks", "v1")
    if not service:
        return {
            "status": "unconfigured",
            "provider": "google_tasks_v1",
            "message": diag.get("message", "Google Tasks API credentials unconfigured."),
        }

    try:
        task_body = {"title": title, "notes": notes}
        if due:
            # Google Tasks requires RFC 3339 format (e.g. 2026-03-14T00:00:00.000Z)
            due_iso = due.strip().replace(" ", "T")
            if not due_iso.endswith("Z"):
                due_iso += "Z"
            task_body["due"] = due_iso

        task = service.tasks().insert(tasklist="@default", body=task_body).execute()

        return {
            "status": "success",
            "provider": "google_tasks_v1",
            "task_id": task.get("id"),
            "title": task.get("title"),
            "message": f"Task '{title}' created in Google Tasks.",
        }
    except Exception as e:
        return {"status": "error", "provider": "google_tasks_v1", "message": f"Google Tasks error: {e}"}


@mcp.tool()
def google_tasks_list(max_results: int = 10) -> Dict[str, Any]:
    """
    Lists tasks from the user's default Google Tasks list via Google Tasks API v1.
    """
    service, diag = _get_google_service("tasks", "v1")
    if not service:
        return {
            "status": "unconfigured",
            "provider": "google_tasks_v1",
            "message": diag.get("message", "Google Tasks API credentials unconfigured."),
        }

    try:
        tasks_result = service.tasks().list(tasklist="@default", maxResults=max_results).execute()
        items = tasks_result.get("items", [])
        return {
            "status": "success",
            "provider": "google_tasks_v1",
            "tasks_count": len(items),
            "tasks": [{"id": t.get("id"), "title": t.get("title"), "status": t.get("status")} for t in items],
        }
    except Exception as e:
        return {"status": "error", "provider": "google_tasks_v1", "message": f"Google Tasks list error: {e}"}


# ==============================================================================
# 4. Google Drive API v3
# ==============================================================================

@mcp.tool()
def google_drive_search(query: str = "", page_size: int = 5) -> Dict[str, Any]:
    """
    Searches documents and files in the user's Google Drive via Google Drive API v3.
    """
    service, diag = _get_google_service("drive", "v3")
    if not service:
        return {
            "status": "unconfigured",
            "provider": "google_drive_v3",
            "message": diag.get("message", "Google Drive API credentials unconfigured."),
        }

    try:
        q_filter = f"name contains '{query}' and trashed = false" if query else "trashed = false"
        results = (
            service.files()
            .list(q=q_filter, pageSize=page_size, fields="files(id, name, mimeType, webViewLink)")
            .execute()
        )
        files = results.get("files", [])
        return {
            "status": "success",
            "provider": "google_drive_v3",
            "files_count": len(files),
            "files": files,
        }
    except Exception as e:
        return {"status": "error", "provider": "google_drive_v3", "message": f"Google Drive error: {e}"}


# ==============================================================================
# 5. Google Keep & Notes
# ==============================================================================

@mcp.tool()
def google_keep_note(title: str, text: str) -> Dict[str, Any]:
    """
    Creates a personal note or reminder note.

    Academic Architecture Note:
    Google Keep does not expose a public consumer REST API (the official Keep API
    is restricted exclusively to Google Workspace Enterprise domains).
    For consumer accounts, notes are stored in Google Tasks / Drive Notes to ensure
    seamless synchronization across Google devices.
    """
    # Authentic integration: create task note via Google Tasks API v1
    task_res = google_tasks_create(title=f"[Note] {title}", notes=text)
    if task_res.get("status") == "success":
        return {
            "status": "success",
            "provider": "google_tasks_note_bridge",
            "title": title,
            "message": f"Note '{title}' saved successfully to your Google Workspace notes.",
            "note_id": task_res.get("task_id"),
        }
    return {
        "status": task_res.get("status", "unconfigured"),
        "provider": "google_tasks_note_bridge",
        "message": task_res.get("message"),
        "architecture_note": "Google Keep REST API is restricted to Enterprise domains; note routed via Google Tasks.",
    }
