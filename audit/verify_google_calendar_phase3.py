import sys
import json
import sqlite3
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_servers.google_services_server import _get_google_service
from app.config import settings

def inspect_phase3_calendar():
    results = {}

    # 1. Independent Google Calendar API Read
    service, diag = _get_google_service("calendar", "v3")
    results["google_service_status"] = diag.get("status")
    results["google_token_path"] = diag.get("token_path")

    if not service:
        results["error"] = "Could not initialize Google Calendar service"
        print(json.dumps(results, indent=2))
        return results

    try:
        # Primary calendar metadata
        cal_meta = service.calendars().get(calendarId="primary").execute()
        results["primary_calendar_id"] = cal_meta.get("id")
        results["primary_calendar_summary"] = cal_meta.get("summary")
        results["primary_calendar_timezone"] = cal_meta.get("timeZone")

        # Query events around October 28, 2026
        time_min = "2026-10-25T00:00:00Z"
        time_max = "2026-11-01T23:59:59Z"
        events_res = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        items = events_res.get("items", [])
        results["events_count_oct_week"] = len(items)
        results["events"] = []

        for ev in items:
            results["events"].append({
                "id": ev.get("id"),
                "summary": ev.get("summary"),
                "status": ev.get("status"),
                "start": ev.get("start"),
                "end": ev.get("end"),
                "html_link": ev.get("htmlLink"),
                "created": ev.get("created"),
                "updated": ev.get("updated")
            })

    except Exception as e:
        results["api_query_error"] = str(e)

    # 2. Local SQLite DB inspection
    db_path = settings.SQLITE_DB_PATH
    results["sqlite_db_path"] = str(db_path)
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check calendar_events
        try:
            cur.execute("SELECT * FROM calendar_events ORDER BY id DESC LIMIT 5")
            results["local_calendar_events"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            results["local_calendar_events_err"] = str(e)

        # Check reminders
        try:
            cur.execute("SELECT * FROM reminders ORDER BY id DESC LIMIT 5")
            results["local_reminders"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            results["local_reminders_err"] = str(e)

        conn.close()

    # Save to file
    out_file = Path("D:/rag-mcp-assistant/audit/phase3_calendar_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    inspect_phase3_calendar()
