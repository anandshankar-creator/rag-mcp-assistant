"""
==============================================================================
Script: test_phase5.py
Role: Phase 5 Automated Verification - FastAPI Backend & Streamlit App
==============================================================================
Validates:
1. FastAPI application initialization and health probe.
2. Document listing endpoint `/api/documents`.
3. Preference management endpoints `/api/preferences`.
4. End-to-end Chat API endpoint `/api/chat`.
5. Streamlit application syntax and compilation sanity.
"""

import py_compile
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_fastapi_health():
    print("\n--- 1. Testing FastAPI /health Probe ---")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    data = resp.json()
    print(f"Health Response: {data}")
    assert data["status"] == "healthy"
    print("Health check PASSED.")


def test_fastapi_documents():
    print("\n--- 2. Testing /api/documents Endpoint ---")
    resp = client.get("/api/documents")
    assert resp.status_code == 200, f"Get documents failed: {resp.text}"
    data = resp.json()
    print(f"Total Chunks in Vector DB: {data.get('total_chunks')}")
    print(f"Documents found on disk: {len(data.get('documents', []))}")
    assert len(data.get("documents", [])) > 0, "No sample documents returned."
    print("Documents endpoint PASSED.")


def test_fastapi_preferences():
    print("\n--- 3. Testing /api/preferences Endpoints ---")
    # Get current preferences
    resp = client.get("/api/preferences")
    assert resp.status_code == 200
    prefs = resp.json()
    print(f"Current Preferences: {prefs}")

    # Update preferences
    update_resp = client.post(
        "/api/preferences",
        json={"name": "Alex Student", "email": "alex.ktu@university.edu", "default_reminder_lead_hours": 12},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["preferences"]
    print(f"Updated Preferences: {updated}")
    assert updated["name"] == "Alex Student"
    assert updated["email"] == "alex.ktu@university.edu"
    print("Preferences endpoint PASSED.")


def test_fastapi_chat():
    print("\n--- 4. Testing /api/chat End-to-End Execution ---")
    payload = {
        "message": "When is my CS402 internal exam?",
        "session_id": "fastapi_test_session",
    }
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200, f"Chat endpoint failed: {resp.text}"
    data = resp.json()

    print(f"Route Selected: {data.get('route')}")
    print(f"Response: {data.get('response')[:120]}...")
    print(f"Citations: {data.get('citations')}")
    print(f"Trace Steps Recorded: {len(data.get('trace', []))}")

    assert data.get("route") == "QA", f"Expected QA route, got {data.get('route')}"
    assert len(data.get("citations", [])) > 0, "No citations in API response."
    assert len(data.get("trace", [])) >= 3, "Incomplete trace telemetry."
    print("Chat API endpoint PASSED.")


def test_streamlit_compilation():
    print("\n--- 5. Testing Streamlit UI Compilation Sanity ---")
    ui_script = PROJECT_ROOT / "ui" / "streamlit_app.py"
    assert ui_script.exists(), "streamlit_app.py missing."
    # Compile Python bytecode to verify zero syntax errors
    py_compile.compile(str(ui_script), doraise=True)
    print(f"Verified syntax and bytecode compilation: {ui_script.name}")
    print("Streamlit UI compilation PASSED.")


if __name__ == "__main__":
    print("==================================================================")
    print("  RUNNING PHASE 5 VERIFICATION: FASTAPI BACKEND & STREAMLIT UI")
    print("==================================================================")
    try:
        test_fastapi_health()
        test_fastapi_documents()
        test_fastapi_preferences()
        test_fastapi_chat()
        test_streamlit_compilation()
        print("\n==================================================================")
        print("  ALL PHASE 5 CHECKS PASSED SUCCESSFULLY!")
        print("==================================================================")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        sys.exit(1)
