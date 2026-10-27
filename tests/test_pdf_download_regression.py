import io
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.auth import create_access_token
from mcp_servers.pdf_server import generate_pdf, cleanup_old_generated_pdfs
from agents.memory import ConversationMemory

client = TestClient(app)


def _get_auth_headers() -> dict:
    token = create_access_token(settings.ADMIN_EMAIL)
    return {"Authorization": f"Bearer {token}"}


def test_pdf_generation_valid_signature_and_metadata():
    """Verify generate_pdf validates and creates a readable PDF with %PDF- header."""
    res = generate_pdf(
        title="Public Holidays Test",
        content="# Holidays\n- Diwali\n- Christmas",
        filename="Public_Holidays_Test.pdf"
    )
    assert res["status"] == "success"
    assert res["filename"] == "Public_Holidays_Test.pdf"
    assert "download_url" in res
    assert "Your PDF is ready" in res["message"]

    pdf_path = Path(res["file_path"])
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0

    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_pdf_filename_path_traversal_sanitization():
    """Verify path traversal in filename argument is stripped to basename."""
    res = generate_pdf(
        title="Security Test",
        content="Testing traversal",
        filename="../../traversal_attempt.pdf"
    )
    assert res["status"] == "success"
    assert res["filename"] == "traversal_attempt.pdf"
    expected_path = (settings.OUTPUTS_DIR / "traversal_attempt.pdf").resolve()
    assert Path(res["file_path"]).resolve() == expected_path


def test_secure_download_endpoint_unauthorized_returns_401():
    """Verify unauthenticated requests to the download endpoint are rejected."""
    resp = client.get("/api/download/pdf/Public_Holidays_Test.pdf")
    assert resp.status_code == 401
    assert "authentication required" in resp.json()["detail"].lower()


def test_secure_download_endpoint_success():
    """Verify GET /api/download/pdf/{filename} returns attachment with valid binary bytes when authenticated."""
    # First generate a test file
    fname = "Secure_Download_Endpoint_Test.pdf"
    gen_res = generate_pdf(
        title="Download Test",
        content="Content for download endpoint",
        filename=fname
    )
    assert gen_res["status"] == "success"

    # Request via FastAPI with Bearer token
    resp = client.get(f"/api/download/pdf/{fname}", headers=_get_auth_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert f'attachment; filename="{fname}"' in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF-")

    # Also verify query param token works (for browser download links)
    token = create_access_token(settings.ADMIN_EMAIL)
    resp_query = client.get(f"/api/download/pdf/{fname}?token={token}")
    assert resp_query.status_code == 200
    assert resp_query.content.startswith(b"%PDF-")


def test_secure_download_endpoint_nonexistent_returns_404():
    """Verify requesting a missing PDF returns 404 rather than empty or fake data."""
    resp = client.get("/api/download/pdf/nonexistent_file_12345.pdf", headers=_get_auth_headers())
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_secure_download_endpoint_rejects_non_pdf_extension():
    """Verify endpoint rejects requests for non-pdf files."""
    resp = client.get("/api/download/pdf/malicious_script.sh", headers=_get_auth_headers())
    assert resp.status_code == 400
    assert "only pdf" in resp.json()["detail"].lower()


def test_secure_download_endpoint_rejects_corrupted_signature():
    """Verify endpoint rejects files that do not start with %PDF- header."""
    fake_pdf = settings.OUTPUTS_DIR / "corrupt_fake.pdf"
    fake_pdf.write_text("This is plain text, not a real PDF document.")

    try:
        resp = client.get("/api/download/pdf/corrupt_fake.pdf", headers=_get_auth_headers())
        assert resp.status_code == 400
        assert "not a valid pdf" in resp.json()["detail"].lower()
    finally:
        fake_pdf.unlink(missing_ok=True)


def test_cleanup_old_generated_pdfs_retention():
    """Verify retention cleanup deletes expired files while keeping fresh ones."""
    fresh_file = settings.OUTPUTS_DIR / "fresh_test_doc.pdf"
    fresh_file.write_bytes(b"%PDF- fresh document")

    old_file = settings.OUTPUTS_DIR / "old_test_doc.pdf"
    old_file.write_bytes(b"%PDF- old document")

    # Set old_file mtime to 3 days ago
    past_time = time.time() - (72 * 3600)
    import os
    os.utime(str(old_file), (past_time, past_time))

    purged = cleanup_old_generated_pdfs(max_age_hours=48)
    assert purged >= 1
    assert not old_file.exists()
    assert fresh_file.exists()

    # Clean up fresh file
    fresh_file.unlink(missing_ok=True)


def test_profile_student_name_update_without_email_input():
    """Verify student name can be updated in memory independently of university email."""
    orig_name = ConversationMemory.get_preference("name", settings.USER_NAME)
    orig_email = ConversationMemory.get_preference("email", settings.USER_DEFAULT_EMAIL)

    try:
        # Update name only
        ConversationMemory.set_preference("name", "Arun Student")
        assert ConversationMemory.get_preference("name") == "Arun Student"
        # Email preference remains untouched
        assert ConversationMemory.get_preference("email") == orig_email
    finally:
        ConversationMemory.set_preference("name", orig_name)
