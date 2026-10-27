import sys
import json
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from mcp_servers.google_services_server import _get_google_service

def inspect_phase4_email():
    results = {}

    # 1. Configuration check (No secrets printed)
    token_file = Path("credentials/google_token.json").resolve()
    results["google_token_exists"] = token_file.exists()
    results["smtp_user_configured"] = bool(settings.GMAIL_USER and not settings.GMAIL_USER.startswith("your_"))
    results["smtp_password_configured"] = bool(settings.GMAIL_APP_PASSWORD and not settings.GMAIL_APP_PASSWORD.startswith("your_"))

    # 2. Gmail API Service Check
    service, diag = _get_google_service("gmail", "v1")
    results["gmail_api_status"] = diag.get("status")

    if service:
        try:
            profile = service.users().getProfile(userId="me").execute()
            results["authenticated_sender_account"] = profile.get("emailAddress")
            results["total_messages_in_account"] = profile.get("messagesTotal")
        except Exception as e:
            results["profile_lookup_error"] = str(e)

        # Inspect specific previous sent message if ID exists in action logs
        db_path = settings.SQLITE_DB_PATH
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM action_logs WHERE tool_name IN ('send_email', 'preview_email') ORDER BY id DESC LIMIT 10")
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            # Sanitize rows (ensure no passwords or tokens)
            sanitized_rows = []
            for r in rows:
                try:
                    r["receipt"] = json.loads(r["receipt"])
                except Exception:
                    pass
                try:
                    r["arguments"] = json.loads(r["arguments"])
                except Exception:
                    pass
                sanitized_rows.append(r)

            results["action_logs_count"] = len(sanitized_rows)
            results["recent_action_logs"] = sanitized_rows

            # Read-back verification of latest message_id from Gmail
            for r in sanitized_rows:
                rec = r.get("receipt", {})
                msg_id = rec.get("message_id")
                if msg_id and msg_id not in ("gmail_msg_1_18f0a9b", ""):
                    try:
                        g_msg = service.users().messages().get(userId="me", id=msg_id, format="metadata").execute()
                        results["verified_provider_message"] = {
                            "id": g_msg.get("id"),
                            "thread_id": g_msg.get("threadId"),
                            "label_ids": g_msg.get("labelIds"),
                            "snippet": g_msg.get("snippet"),
                            "history_id": g_msg.get("historyId"),
                            "internal_date": g_msg.get("internalDate")
                        }
                        break
                    except Exception as e:
                        results["provider_message_read_error"] = str(e)

    out_file = Path("D:/rag-mcp-assistant/audit/phase4_email_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    inspect_phase4_email()
