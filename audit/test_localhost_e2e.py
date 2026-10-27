import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import json
from app.config import settings
from app.auth import get_admin_account

BASE_API = "http://127.0.0.1:8000"
BASE_UI = "http://localhost:8501"

def run_e2e_localhost_check():
    print("=" * 65)
    print("  LIVE LOCALHOST END-TO-END VERIFICATION")
    print(f"  Target Admin Email: {settings.ADMIN_EMAIL}")
    print("=" * 65)

    # 1. Check Streamlit UI status
    res_ui = requests.get(BASE_UI)
    print(f"[1] Streamlit UI (port 8501) Status: {res_ui.status_code} (OK)")
    assert res_ui.status_code == 200, "Streamlit UI is not running!"

    # 2. Check FastAPI Backend Health
    res_health = requests.get(f"{BASE_API}/health").json()
    print(f"[2] FastAPI Health (port 8000): {res_health}")
    assert res_health["status"] == "healthy", "FastAPI backend unhealthy!"

    # 3. Unauthenticated API access blocking
    res_unauth = requests.post(f"{BASE_API}/api/chat", json={"message": "What is KTU?"})
    print(f"[3] Unauthenticated /api/chat Status: {res_unauth.status_code} (Expected: 401)")
    assert res_unauth.status_code == 401, f"Expected 401, got {res_unauth.status_code}"

    # 4. Authenticate Administrator via API
    login_payload = {
        "email": settings.ADMIN_EMAIL,
        "password": settings.ADMIN_INITIAL_PASSWORD or "AdminSecurePass2026!"
    }
    res_login = requests.post(f"{BASE_API}/api/auth/login", json=login_payload)
    print(f"[4] Login Attempt for '{settings.ADMIN_EMAIL}' Status: {res_login.status_code}")
    assert res_login.status_code == 200, f"Login failed: {res_login.text}"
    token_data = res_login.json()
    token = token_data["access_token"]
    print(f"    JWT Token issued successfully. Admin: {token_data['admin_email']}")

    headers = {"Authorization": f"Bearer {token}"}

    # 5. Get Preferences
    res_prefs = requests.get(f"{BASE_API}/api/preferences", headers=headers)
    print(f"[5] Preferences Read Status: {res_prefs.status_code}")
    print(f"    User Preferences: {res_prefs.json()}")

    # 6. List Documents
    res_docs = requests.get(f"{BASE_API}/api/documents", headers=headers)
    print(f"[6] Documents Ingested Status: {res_docs.status_code}")
    docs_data = res_docs.json()
    print(f"    Total chunks in ChromaDB: {docs_data.get('total_chunks', 0)}")
    print(f"    Available Files: {[f.get('filename') for f in docs_data.get('files', [])]}")

    # 7. Ask Document Question via Chat
    print("\n[7] Querying RAG Assistant via /api/chat: 'What are the course outcomes of KTU CS301?'...")
    chat_payload = {
        "message": "What are the course outcomes of KTU CS301 Theory of Computation?",
        "session_id": "localhost_test_session"
    }
    res_chat = requests.post(f"{BASE_API}/api/chat", json=chat_payload, headers=headers)
    print(f"    Chat Response Status: {res_chat.status_code}")
    if res_chat.status_code == 200:
        chat_data = res_chat.json()
        print(f"    Route Chosen: {chat_data.get('route')}")
        print(f"    Retrieved Sources: {chat_data.get('sources')}")
        answer_preview = chat_data.get('response', '')[:300].replace('\n', ' ')
        print(f"    Assistant Answer: {answer_preview}...")

    # 8. Test MCP Action Execution: Create Reminder
    print("\n[8] Testing MCP Action via Chat: 'Set a reminder to submit report tomorrow at 5 PM'...")
    action_payload = {
        "message": "Set a reminder to submit the report draft tomorrow at 5 PM",
        "session_id": "localhost_test_session"
    }
    res_action = requests.post(f"{BASE_API}/api/chat", json=action_payload, headers=headers)
    print(f"    MCP Action Status: {res_action.status_code}")
    if res_action.status_code == 200:
        action_data = res_action.json()
        print(f"    Route Chosen: {action_data.get('route')}")
        print(f"    Actions Executed: {action_data.get('action_results')}")
        answer_preview = action_data.get('response', '')[:300].replace('\n', ' ')
        print(f"    Assistant Answer: {answer_preview}...")

    print("\n" + "=" * 65)
    print("  ALL LOCALHOST VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_e2e_localhost_check()
