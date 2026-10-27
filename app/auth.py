"""
==============================================================================
Module: app.auth
Role in Architecture: Central Administrator Authentication & Session Engine
==============================================================================
Provides robust, administrator-only authentication, session management, and
password recovery:
1. Administrator-Only Architecture:
   Single configured administrator account (no public self-registration).
2. Salted bcrypt password hashing & verification.
3. Cryptographic JWT session tokens with:
   - Configurable session expiration
   - Explicit token revocation (logout)
   - Global session invalidation (auth_version increment upon password reset)
4. Protection against brute-force login attacks with progressive lockout.
5. Secure, single-use password reset tokens:
   - Only SHA-256 hashes of reset tokens are stored in SQLite
   - 15-minute expiration window
   - Automatic single-use consumption
   - Rate limiting on reset requests to prevent enumeration & denial-of-service
6. Standard password complexity policy enforcement.
==============================================================================
"""

from __future__ import annotations
import datetime
import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt

from app.config import settings


class AuthError(Exception):
    """Custom exception raised on authentication failures."""
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_auth_db() -> sqlite3.Connection:
    """Returns a SQLite connection for authentication tables."""
    db_path = settings.SQLITE_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_tables() -> None:
    """Initializes administrator credentials, sessions, and token tables."""
    conn = get_auth_db()
    cursor = conn.cursor()

    # 1. Administrator Credentials (Single configured account)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            auth_version INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Login Attempt Tracking (Brute-force protection)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            identifier TEXT PRIMARY KEY,
            failed_count INTEGER DEFAULT 0,
            last_failed_at REAL DEFAULT 0,
            locked_until REAL DEFAULT 0
        )
    """)

    # 3. Password Reset Tokens (Single-use, only SHA-256 hash stored)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            used INTEGER DEFAULT 0
        )
    """)

    # 4. Revoked JWT Tokens (Blacklist for explicit logout)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti TEXT PRIMARY KEY,
            revoked_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
    """)

    # 5. Password Reset Request Rate Limiting
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reset_request_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT NOT NULL,
            requested_at REAL NOT NULL
        )
    """)

    conn.commit()

    # Seed administrator account if not present
    _seed_admin_account_if_needed(cursor, conn)

    conn.close()


def _seed_admin_account_if_needed(cursor: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
    """Seeds the initial administrator credentials from settings if database table is empty."""
    cursor.execute("SELECT COUNT(*) as cnt FROM admin_credentials")
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        return

    admin_email = settings.ADMIN_EMAIL
    pwd_hash = settings.ADMIN_PASSWORD_HASH

    if not pwd_hash:
        # Generate bcrypt hash from configured initial password
        initial_pwd = settings.ADMIN_INITIAL_PASSWORD or "AdminSecurePass2026!"
        pwd_hash = hash_password(initial_pwd)

    cursor.execute(
        "INSERT INTO admin_credentials (email, password_hash, auth_version) VALUES (?, ?, 1)",
        (admin_email, pwd_hash),
    )
    conn.commit()


# --- Password Cryptography & Policy ---

def hash_password(password: str) -> str:
    """Generates a salted bcrypt password hash."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verifies plaintext password against a bcrypt hash in constant time."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_policy(password: str) -> Tuple[bool, str]:
    """
    Enforces password complexity:
    - Minimum 8 characters
    - At least one letter (a-z, A-Z)
    - At least one digit or symbol
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"[0-9!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one number or special character."
    return True, ""


# --- Administrator Account Retrieval ---

def get_admin_account() -> Optional[Dict[str, Any]]:
    """Retrieves the single configured administrator record from SQLite."""
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, password_hash, auth_version FROM admin_credentials ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def is_admin_email(email: str) -> bool:
    """Checks whether the supplied email matches the configured administrator."""
    admin = get_admin_account()
    if not admin:
        return False
    return email.strip().lower() == admin["email"].strip().lower()


# --- Brute-Force & Rate Limiting ---

def check_login_rate_limit(identifier: str) -> Tuple[bool, Optional[str], int]:
    """
    Checks whether a client or account is currently locked out due to excessive failed logins.
    Returns: (is_allowed, error_message, remaining_lockout_seconds)
    """
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("SELECT failed_count, locked_until FROM login_attempts WHERE identifier = ?", (identifier,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return True, None, 0

    now = time.time()
    locked_until = row["locked_until"]
    if locked_until > now:
        remaining_sec = int(locked_until - now)
        remaining_min = max(1, (remaining_sec + 59) // 60)
        return False, f"Too many failed login attempts. Access is locked for {remaining_min} minute(s).", remaining_sec

    return True, None, 0


def record_login_failure(identifier: str) -> Tuple[int, bool]:
    """
    Records a failed login attempt. Locks out if threshold exceeded.
    Returns: (new_failed_count, is_now_locked)
    """
    conn = get_auth_db()
    cursor = conn.cursor()
    now = time.time()

    cursor.execute("SELECT failed_count, locked_until FROM login_attempts WHERE identifier = ?", (identifier,))
    row = cursor.fetchone()

    if not row:
        failed = 1
        locked = 0
        cursor.execute(
            "INSERT INTO login_attempts (identifier, failed_count, last_failed_at, locked_until) VALUES (?, ?, ?, ?)",
            (identifier, failed, now, locked),
        )
    else:
        # If previous lock expired, reset count to 1
        if row["locked_until"] > 0 and row["locked_until"] <= now:
            failed = 1
            locked = 0
        else:
            failed = row["failed_count"] + 1
            locked = row["locked_until"]

        if failed >= settings.MAX_LOGIN_ATTEMPTS:
            locked = now + (settings.LOCKOUT_MINUTES * 60)

        cursor.execute(
            "UPDATE login_attempts SET failed_count = ?, last_failed_at = ?, locked_until = ? WHERE identifier = ?",
            (failed, now, locked, identifier),
        )

    conn.commit()
    conn.close()
    return failed, (locked > now)


def clear_login_failures(identifier: str) -> None:
    """Clears failed login attempts upon successful login."""
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_attempts WHERE identifier = ?", (identifier,))
    conn.commit()
    conn.close()


def check_reset_request_rate_limit(identifier: str) -> Tuple[bool, Optional[str]]:
    """
    Rate limits password reset requests to prevent token enumeration & mail abuse.
    Allows at most MAX_RESET_ATTEMPTS within 15 minutes.
    """
    conn = get_auth_db()
    cursor = conn.cursor()
    now = time.time()
    window_start = now - (15 * 60)

    # Clean old requests
    cursor.execute("DELETE FROM reset_request_attempts WHERE requested_at < ?", (window_start,))

    cursor.execute(
        "SELECT COUNT(*) as cnt FROM reset_request_attempts WHERE identifier = ? AND requested_at >= ?",
        (identifier, window_start),
    )
    row = cursor.fetchone()
    count = row["cnt"] if row else 0

    if count >= settings.MAX_RESET_ATTEMPTS:
        conn.commit()
        conn.close()
        return False, "Too many password reset requests. Please wait a few minutes before trying again."

    cursor.execute(
        "INSERT INTO reset_request_attempts (identifier, requested_at) VALUES (?, ?)",
        (identifier, now),
    )
    conn.commit()
    conn.close()
    return True, None


# --- JWT Session Management ---

def create_access_token(email: str, expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Generates a cryptographically signed JWT access token."""
    admin = get_admin_account()
    auth_version = admin["auth_version"] if admin else 1

    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(minutes=settings.SESSION_EXPIRE_MINUTES)

    jti = str(uuid.uuid4())
    payload = {
        "sub": email.strip().lower(),
        "jti": jti,
        "v": auth_version,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verifies a JWT access token:
    - Signature validity & algorithm
    - Expiration time
    - Blacklist check (explicit logout)
    - Auth version check (global invalidation on password reset)
    """
    if not token or not token.strip():
        raise AuthError("Authentication required: No token provided.")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid authentication token.")

    jti = payload.get("jti")
    if not jti:
        raise AuthError("Malformed authentication token.")

    # Check revoked tokens blacklist
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("SELECT jti FROM revoked_tokens WHERE jti = ?", (jti,))
    if cursor.fetchone():
        conn.close()
        raise AuthError("Session has been logged out. Please sign in again.")

    # Check auth version (invalidates all tokens issued prior to a password reset)
    admin = get_admin_account()
    if not admin:
        conn.close()
        raise AuthError("Administrator account not found.")

    token_version = payload.get("v", 0)
    current_version = admin["auth_version"]
    if token_version != current_version:
        conn.close()
        raise AuthError("Session has been invalidated due to a password change.")

    conn.close()
    return payload


def revoke_token(token: str) -> bool:
    """Explicitly revokes a session token by blacklisting its JTI."""
    try:
        # Decode without verifying expiration to revoke even recently expired tokens
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
        exp = payload.get("exp", time.time() + 3600)
        if not jti:
            return False

        conn = get_auth_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)",
            (jti, time.time(), exp),
        )
        # Purge old revoked tokens whose expiration has passed
        cursor.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (time.time(),))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def invalidate_all_sessions() -> None:
    """Increments the administrator auth_version, instantly invalidating ALL active sessions."""
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE admin_credentials SET auth_version = auth_version + 1, updated_at = CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()


# --- Administrator Login Authenticator ---

def authenticate_administrator(email: str, password: str, client_id: str = "default_client") -> Dict[str, Any]:
    """
    Authenticates the administrator account:
    - Enforces rate limiting & lockout
    - Validates email and password using bcrypt
    - On failure, returns generic error without exposing account existence
    - On success, clears failure count and returns an access token
    """
    clean_email = email.strip().lower()
    allowed, lock_msg, _ = check_login_rate_limit(clean_email)
    if not allowed:
        raise AuthError(lock_msg or "Account temporarily locked.", status_code=429)

    # Also check rate limit by client IP/ID
    if client_id != clean_email:
        allowed_ip, lock_msg_ip, _ = check_login_rate_limit(client_id)
        if not allowed_ip:
            raise AuthError(lock_msg_ip or "Client temporarily locked.", status_code=429)

    admin = get_admin_account()
    if not admin:
        record_login_failure(clean_email)
        record_login_failure(client_id)
        raise AuthError("Invalid email or password.", status_code=401)

    # Constant-time comparison check
    email_matches = (clean_email == admin["email"].strip().lower())
    pwd_matches = verify_password(password, admin["password_hash"])

    if not (email_matches and pwd_matches):
        record_login_failure(clean_email)
        record_login_failure(client_id)
        raise AuthError("Invalid email or password.", status_code=401)

    # Success: clear failure counters
    clear_login_failures(clean_email)
    clear_login_failures(client_id)

    token = create_access_token(admin["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.SESSION_EXPIRE_MINUTES,
        "admin_email": admin["email"],
    }


# --- Forgot Password & Single-Use Reset Tokens ---

def generate_password_reset_token(email: str) -> Optional[str]:
    """
    Generates a cryptographically secure, single-use password reset token.
    Stores ONLY the SHA-256 hash of the token in SQLite.
    Returns the raw URL-safe token to be emailed to the administrator.
    If email does not match admin, returns None without revealing existence.
    """
    clean_email = email.strip().lower()
    if not is_admin_email(clean_email):
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    now = time.time()
    expires_at = now + (settings.RESET_TOKEN_EXPIRE_MINUTES * 60)

    conn = get_auth_db()
    cursor = conn.cursor()

    # Invalidate any existing unused reset tokens for this email
    cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE email = ? AND used = 0", (clean_email,))

    cursor.execute(
        "INSERT INTO password_reset_tokens (token_hash, email, created_at, expires_at, used) VALUES (?, ?, ?, ?, 0)",
        (token_hash, clean_email, now, expires_at),
    )
    conn.commit()
    conn.close()

    return raw_token


def verify_password_reset_token(raw_token: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates a password reset token:
    - Hashes the token and checks presence
    - Confirms token is not used
    - Confirms token is not expired
    Returns: (is_valid, email, error_message)
    """
    if not raw_token or not raw_token.strip():
        return False, None, "Reset token is missing or empty."

    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    conn = get_auth_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT email, expires_at, used FROM password_reset_tokens WHERE token_hash = ?",
        (token_hash,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, None, "Invalid or unrecognized reset link."

    if row["used"] == 1:
        return False, None, "This password reset link has already been used. Please request a new link."

    now = time.time()
    if row["expires_at"] <= now:
        return False, None, "This password reset link has expired (valid for 15 minutes). Please request a new link."

    return True, row["email"], None


def reset_password_with_token(raw_token: str, new_password: str) -> Tuple[bool, str]:
    """
    Executes a password reset:
    1. Validates token (hash matching, unused, unexpired).
    2. Validates new password policy.
    3. Updates administrator password hash with salted bcrypt.
    4. Marks token as used (single use).
    5. Increments auth_version to invalidate ALL existing active sessions.
    Returns: (success, message)
    """
    is_valid, email, err_msg = verify_password_reset_token(raw_token)
    if not is_valid:
        return False, err_msg or "Invalid reset token."

    # Validate password complexity
    policy_ok, policy_msg = validate_password_policy(new_password)
    if not policy_ok:
        return False, policy_msg

    new_hash = hash_password(new_password)
    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

    conn = get_auth_db()
    cursor = conn.cursor()

    try:
        # 1. Mark token as used
        cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE token_hash = ?", (token_hash,))

        # 2. Update admin password and increment auth_version
        cursor.execute(
            "UPDATE admin_credentials SET password_hash = ?, auth_version = auth_version + 1, updated_at = CURRENT_TIMESTAMP WHERE email = ?",
            (new_hash, email),
        )

        # 3. Clear any lockout history for the admin
        cursor.execute("DELETE FROM login_attempts WHERE identifier = ?", (email,))

        conn.commit()
        conn.close()
        return True, "Password has been successfully updated. All active sessions have been invalidated. You can now sign in."
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Failed to reset password: {str(e)}"


# Initialize auth tables upon module import
init_auth_tables()
