"""
==============================================================================
Test Suite: tests.test_auth_and_security
Domain: Administrator-Only Authentication, Session Management, and Security
==============================================================================
Covers:
1. Administrator login with valid credentials (salted bcrypt verification).
2. Login rejections with generic error (invalid email, invalid password).
3. Brute-force protection & progressive lockout after multiple failed attempts.
4. JWT session creation, validation, and expiration.
5. Logout & explicit session token revocation.
6. Unauthorized access blocking for all protected FastAPI endpoints:
   - POST /api/chat
   - POST /api/upload
   - GET /api/documents
   - DELETE /api/documents/{filename}
   - POST /api/confirm-action
   - GET /api/preferences
   - POST /api/preferences
   - GET /api/download/pdf/{filename}
7. Single-use Password Reset ("Forgot Password?"):
   - Generic confirmation (no account enumeration)
   - SHA-256 hash storage verification (plaintext token never stored)
   - 15-minute token expiration enforcement
   - Immediate invalidation upon use (single-use enforcement)
   - Password complexity policy verification
   - Global session invalidation upon password reset
   - Rate limiting on reset requests
   - Fail-soft behavior on email provider errors
==============================================================================
"""

import datetime
import hashlib
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.auth import (
    authenticate_administrator,
    check_login_rate_limit,
    check_reset_request_rate_limit,
    clear_login_failures,
    create_access_token,
    generate_password_reset_token,
    get_admin_account,
    get_auth_db,
    hash_password,
    record_login_failure,
    reset_password_with_token,
    revoke_token,
    validate_password_policy,
    verify_access_token,
    verify_password,
    verify_password_reset_token,
    AuthError,
)
from app.auth_email import send_password_reset_email, build_password_reset_url

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_auth_state():
    """Ensure clean authentication tables and failure counters for each test."""
    clear_login_failures(settings.ADMIN_EMAIL)
    clear_login_failures("test_client_ip")
    clear_login_failures("testclient")
    clear_login_failures("attacker@evil.com")
    conn = get_auth_db()
    conn.cursor().execute("DELETE FROM reset_request_attempts")
    conn.commit()
    conn.close()
    yield
    clear_login_failures(settings.ADMIN_EMAIL)
    clear_login_failures("test_client_ip")
    clear_login_failures("testclient")
    clear_login_failures("attacker@evil.com")
    conn = get_auth_db()
    conn.cursor().execute("DELETE FROM reset_request_attempts")
    conn.commit()
    conn.close()


# --- 1. Password Hashing & Verification Tests ---

def test_password_hashing_uses_salted_bcrypt():
    """Verify passwords are hashed with bcrypt and produce distinct salts."""
    pwd = "AdminSecurePass2026!"
    hash1 = hash_password(pwd)
    hash2 = hash_password(pwd)

    assert hash1.startswith("$2b$") or hash1.startswith("$2a$")
    assert hash2.startswith("$2b$") or hash2.startswith("$2a$")
    assert hash1 != hash2, "Bcrypt hashes must use unique salts"
    assert verify_password(pwd, hash1) is True
    assert verify_password(pwd, hash2) is True
    assert verify_password("WrongPassword123", hash1) is False


def test_password_policy_validation():
    """Verify password policy requires >=8 chars, letters, and numbers/symbols."""
    assert validate_password_policy("Short1!")[0] is False
    assert validate_password_policy("nouppercaseornumbershere")[0] is False
    assert validate_password_policy("1234567890")[0] is False
    assert validate_password_policy("ValidPass2026!")[0] is True
    assert validate_password_policy("Another#Strong99")[0] is True


# --- 2. Administrator Login & Brute-Force Lockout ---

def test_admin_login_success():
    """Verify administrator can sign in and receive a signed JWT token."""
    pwd = settings.ADMIN_INITIAL_PASSWORD or "AdminSecurePass2026!"
    res = authenticate_administrator(settings.ADMIN_EMAIL, pwd, client_id="test_client_ip")

    assert "access_token" in res
    assert res["token_type"] == "bearer"
    assert res["admin_email"] == settings.ADMIN_EMAIL

    payload = verify_access_token(res["access_token"])
    assert payload["sub"] == settings.ADMIN_EMAIL


def test_admin_login_invalid_password_returns_generic_error():
    """Verify wrong password fails with generic error."""
    with pytest.raises(AuthError) as exc_info:
        authenticate_administrator(settings.ADMIN_EMAIL, "WrongPassword123!", client_id="test_client_ip")
    assert exc_info.value.status_code == 401
    assert "invalid email or password" in exc_info.value.message.lower()


def test_admin_login_unknown_email_returns_identical_generic_error():
    """Verify unknown email fails with identical generic error to prevent account enumeration."""
    with pytest.raises(AuthError) as exc_info:
        authenticate_administrator("unknown_user@random.com", "SomePassword123!", client_id="test_client_ip")
    assert exc_info.value.status_code == 401
    assert "invalid email or password" in exc_info.value.message.lower()


def test_login_brute_force_lockout():
    """Verify client is locked out after consecutive failed attempts."""
    target_id = "brute_force_target_ip"
    clear_login_failures(target_id)

    # 4 failed attempts should not trigger lockout yet
    for _ in range(settings.MAX_LOGIN_ATTEMPTS - 1):
        _, locked = record_login_failure(target_id)
        assert locked is False

    allowed, _, _ = check_login_rate_limit(target_id)
    assert allowed is True

    # 5th failed attempt triggers lockout
    _, locked = record_login_failure(target_id)
    assert locked is True

    allowed, lock_msg, rem_sec = check_login_rate_limit(target_id)
    assert allowed is False
    assert "locked" in lock_msg.lower()
    assert rem_sec > 0

    # Clean up
    clear_login_failures(target_id)


# --- 3. Session Management, Expiration & Revocation ---

def test_session_token_expiration_enforcement():
    """Verify expired tokens are rejected with 401."""
    # Create token expired 10 seconds ago
    expired_delta = datetime.timedelta(seconds=-10)
    token = create_access_token(settings.ADMIN_EMAIL, expires_delta=expired_delta)

    with pytest.raises(AuthError) as exc_info:
        verify_access_token(token)
    assert "session expired" in exc_info.value.message.lower()


def test_session_token_revocation_on_logout():
    """Verify logging out revokes the session token immediately."""
    token = create_access_token(settings.ADMIN_EMAIL)
    assert verify_access_token(token)["sub"] == settings.ADMIN_EMAIL

    # Revoke token
    revoked = revoke_token(token)
    assert revoked is True

    # Verifying now must fail
    with pytest.raises(AuthError) as exc_info:
        verify_access_token(token)
    assert "logged out" in exc_info.value.message.lower()


# --- 4. Protected API Endpoints & Unauthorized Rejection ---

def test_api_chat_unauthorized_rejection():
    """Verify POST /api/chat rejects unauthenticated requests with HTTP 401."""
    resp = client.post("/api/chat", json={"message": "Summarize my notes", "session_id": "test"})
    assert resp.status_code == 401
    assert "authentication required" in resp.json()["detail"].lower()


def test_api_upload_unauthorized_rejection():
    """Verify POST /api/upload rejects unauthenticated requests with HTTP 401."""
    resp = client.post(
        "/api/upload",
        files={"file": ("test.txt", b"Hello world", "text/plain")}
    )
    assert resp.status_code == 401
    assert "authentication required" in resp.json()["detail"].lower()


def test_api_documents_unauthorized_rejection():
    """Verify GET /api/documents rejects unauthenticated requests with HTTP 401."""
    resp = client.get("/api/documents")
    assert resp.status_code == 401


def test_api_delete_document_unauthorized_rejection():
    """Verify DELETE /api/documents/{filename} rejects unauthenticated requests with HTTP 401."""
    resp = client.delete("/api/documents/some_file.pdf")
    assert resp.status_code == 401


def test_api_confirm_action_unauthorized_rejection():
    """Verify POST /api/confirm-action rejects unauthenticated requests with HTTP 401."""
    resp = client.post(
        "/api/confirm-action",
        json={"action_type": "send_email", "parameters": {"to": "test@test.com"}}
    )
    assert resp.status_code == 401


def test_api_preferences_unauthorized_rejection():
    """Verify GET and POST /api/preferences reject unauthenticated requests with HTTP 401."""
    get_resp = client.get("/api/preferences")
    assert get_resp.status_code == 401

    post_resp = client.post("/api/preferences", json={"name": "Attacker"})
    assert post_resp.status_code == 401


def test_api_download_pdf_unauthorized_rejection():
    """Verify GET /api/download/pdf/{filename} rejects unauthenticated requests with HTTP 401."""
    resp = client.get("/api/download/pdf/AnyDocument.pdf")
    assert resp.status_code == 401


def test_static_outputs_direct_url_is_not_served_unauthenticated():
    """Verify static /outputs mount is not openly served without auth."""
    resp = client.get("/outputs/Public_Holidays_Test.pdf")
    # Should return 404 or not found since static mount was removed
    assert resp.status_code in (404, 401)


def test_api_endpoints_succeed_with_valid_bearer_token():
    """Verify protected endpoints succeed when supplied with valid Bearer token."""
    token = create_access_token(settings.ADMIN_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    # Preferences GET
    resp = client.get("/api/preferences", headers=headers)
    assert resp.status_code == 200

    # Documents GET
    docs_resp = client.get("/api/documents", headers=headers)
    assert docs_resp.status_code == 200

    # Auth verify
    verify_resp = client.get("/api/auth/verify", headers=headers)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["admin_email"] == settings.ADMIN_EMAIL


# --- 5. Forgot Password & Single-Use Reset Tokens ---

def test_forgot_password_generic_response_no_enumeration():
    """Verify forgot-password returns identical confirmation for admin and non-admin emails."""
    # 1. Admin email
    resp_admin = client.post("/api/auth/forgot-password", json={"email": settings.ADMIN_EMAIL})
    assert resp_admin.status_code == 200
    msg_admin = resp_admin.json()["message"]

    # 2. Unknown email
    resp_unknown = client.post("/api/auth/forgot-password", json={"email": "nonexistent@example.com"})
    assert resp_unknown.status_code == 200
    msg_unknown = resp_unknown.json()["message"]

    assert msg_admin == msg_unknown
    assert "if the email address matches" in msg_admin.lower()


def test_reset_token_stores_only_sha256_hash():
    """Verify that only the SHA-256 hash of the reset token is stored in the database."""
    raw_token = generate_password_reset_token(settings.ADMIN_EMAIL)
    assert raw_token is not None

    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token_hash, email FROM password_reset_tokens WHERE token_hash = ?", (expected_hash,))
    row = cursor.fetchone()

    # Raw token itself must NOT be anywhere in the database
    cursor.execute("SELECT * FROM password_reset_tokens WHERE token_hash = ?", (raw_token,))
    raw_match = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row["token_hash"] == expected_hash
    assert raw_match is None, "Raw plaintext token must NEVER be stored in the database"


def test_reset_token_single_use_consumption():
    """Verify reset token can only be used once, and subsequent attempts fail."""
    raw_token = generate_password_reset_token(settings.ADMIN_EMAIL)
    new_password = "BrandNewSecurePassword2026!"

    # 1. First reset succeeds
    success, msg = reset_password_with_token(raw_token, new_password)
    assert success is True
    assert "successfully updated" in msg.lower()

    # 2. Re-using the exact same token MUST fail
    reuse_success, reuse_msg = reset_password_with_token(raw_token, "AnotherPassword2026!")
    assert reuse_success is False
    assert "already been used" in reuse_msg.lower()

    # Revert back to original password for subsequent tests
    orig_pwd = settings.ADMIN_INITIAL_PASSWORD or "AdminSecurePass2026!"
    t2 = generate_password_reset_token(settings.ADMIN_EMAIL)
    reset_password_with_token(t2, orig_pwd)


def test_reset_token_expiration():
    """Verify reset token expires after its expiration timestamp."""
    raw_token = generate_password_reset_token(settings.ADMIN_EMAIL)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # Artificially set expiration to 10 seconds ago in SQLite
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?",
        (time.time() - 10, token_hash),
    )
    conn.commit()
    conn.close()

    is_valid, email, err = verify_password_reset_token(raw_token)
    assert is_valid is False
    assert "expired" in err.lower()


def test_reset_token_invalid_tampered_fails():
    """Verify tampered or invalid reset token is rejected."""
    is_valid, email, err = verify_password_reset_token("completely_fabricated_token_xyz")
    assert is_valid is False
    assert "invalid or unrecognized" in err.lower()


def test_password_reset_invalidates_all_existing_sessions():
    """Verify that resetting password increments auth_version and invalidates all prior sessions."""
    # 1. Issue an access token with current credentials
    old_token = create_access_token(settings.ADMIN_EMAIL)
    assert verify_access_token(old_token)["sub"] == settings.ADMIN_EMAIL

    # 2. Reset password via token
    reset_token = generate_password_reset_token(settings.ADMIN_EMAIL)
    success, _ = reset_password_with_token(reset_token, "NewSecretKey2026!#")
    assert success is True

    # 3. Old token MUST now be rejected due to auth_version increment
    with pytest.raises(AuthError) as exc_info:
        verify_access_token(old_token)
    assert "session has been invalidated" in exc_info.value.message.lower()

    # Revert password
    orig_pwd = settings.ADMIN_INITIAL_PASSWORD or "AdminSecurePass2026!"
    t_revert = generate_password_reset_token(settings.ADMIN_EMAIL)
    reset_password_with_token(t_revert, orig_pwd)


def test_forgot_password_rate_limiting():
    """Verify requesting password reset link is bounded by rate limiter."""
    test_id = "test_rate_limiter_client"
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reset_request_attempts WHERE identifier = ?", (test_id,))
    conn.commit()
    conn.close()

    # Make MAX_RESET_ATTEMPTS requests
    for _ in range(settings.MAX_RESET_ATTEMPTS):
        allowed, _ = check_reset_request_rate_limit(test_id)
        assert allowed is True

    # Next attempt should be blocked
    allowed, msg = check_reset_request_rate_limit(test_id)
    assert allowed is False
    assert "too many password reset requests" in msg.lower()


def test_auth_email_fail_soft_when_provider_unavailable():
    """Verify email dispatcher fails softly and returns False without throwing or logging secrets."""
    with patch("mcp_servers.google_services_server._get_google_service", return_value=(None, None)):
        with patch.object(settings, "GMAIL_APP_PASSWORD", "your_16_digit_app_password"):
            ok, msg = send_password_reset_email(settings.ADMIN_EMAIL, "fake_token_123")
            assert ok is False
            assert "unconfigured" in msg.lower() or "unavailable" in msg.lower()


def test_reset_url_matches_public_base_url():
    """Verify reset URL uses configured APP_BASE_URL and never hardcodes localhost in production."""
    custom_base = "https://personal-assistant.university.edu"
    url = build_password_reset_url("test_token_abc", base_url=custom_base)
    assert url == "https://personal-assistant.university.edu/?action=reset_password&token=test_token_abc"


# --- 7. Canonical Admin Identity & Bootstrapping Tests ---

def test_canonical_admin_email_configured_and_retrievable():
    """Verify canonical administrator email is configured as sergio759516@gmail.com."""
    assert settings.ADMIN_EMAIL == "sergio759516@gmail.com"
    admin = get_admin_account()
    assert admin is not None
    assert admin["email"] == "sergio759516@gmail.com"


def test_admin_email_idempotent_migration():
    """Verify database auto-migrates old/default admin email to canonical settings.ADMIN_EMAIL."""
    from app.auth import _seed_admin_account_if_needed
    conn = get_auth_db()
    cursor = conn.cursor()

    # Artificially set email back to legacy placeholder
    cursor.execute("UPDATE admin_credentials SET email = 'admin@assistant.local'")
    conn.commit()

    # Run migration/seed function
    _seed_admin_account_if_needed(cursor, conn)
    conn.close()

    admin = get_admin_account()
    assert admin["email"] == "sergio759516@gmail.com", "Migration must restore canonical admin email"


def test_forgot_password_generates_token_for_canonical_admin():
    """Verify password recovery generates a valid single-use token for sergio759516@gmail.com."""
    token = generate_password_reset_token("sergio759516@gmail.com")
    assert token is not None
    assert len(token) > 20

    is_valid, email, err = verify_password_reset_token(token)
    assert is_valid is True
    assert email == "sergio759516@gmail.com"
    assert err is None
