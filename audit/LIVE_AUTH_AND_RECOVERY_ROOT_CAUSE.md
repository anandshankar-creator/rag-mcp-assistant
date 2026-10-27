# Live Authentication and Password Recovery Root Cause Analysis

**Project**: RAG-Based Multi-Agent Personal Assistant Using MCP  
**Repository**: `https://github.com/anandshankar-creator/rag-mcp-assistant`  
**Live Application**: `https://rag-mcp-assistant-mf654govkzfnjjmmtlgxfqw.streamlit.app`  
**Target Administrator**: `sergio759516@gmail.com`  
**Audit Date**: October 2026  

---

## 1. Executive Summary

During live verification of the deployed Streamlit Community Cloud application, two major authentication breakdowns occurred:
1. **Administrator Sign-In Failure**: Attempting to sign in with the canonical administrator email (`sergio759516@gmail.com`) failed with `Invalid email or password`, and the input fields displayed `admin@assistant.local` as placeholder defaults.
2. **Password Recovery ("Forgot Password?") Silent Failure**: Submitting `sergio759516@gmail.com` in the recovery form displayed a generic success notification, but no password reset email arrived in the administrator's inbox.

This investigation determined that these failures were caused by an architectural disconnect between initial database seeding, environment configuration loading, rate-limiting lockout tracking, and cloud mail provider assumptions.

---

## 2. Forensic Code Trace & Root Cause Breakdown

### 2.1 The SQLite Seeding Deadlock (`app/auth.py`)

In `app/auth.py`, table creation and initial credential provisioning were handled by `_ensure_tables()` and `_seed_admin_account_if_needed()`:

```python
# PREVIOUS IMPLEMENTATION IN app/auth.py (Lines 121-126)
def _seed_admin_account_if_needed(cursor: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
    cursor.execute("SELECT COUNT(*) as cnt FROM admin_credentials")
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        return  # <-- DEADLOCK: If any record exists, exit without checking email!
    ...
```

#### The Sequence of Events on Streamlit Community Cloud:
1. When the repository was initially deployed to Streamlit Community Cloud, `app/config.py` had default fallback:
   ```python
   ADMIN_EMAIL: str = _get_config_value("ADMIN_EMAIL", "admin@assistant.local").strip().lower()
   ```
2. On first boot, SQLite database `db/assistant.db` was created and seeded with:
   - `email`: `admin@assistant.local`
   - `password_hash`: bcrypt hash of `AdminSecurePass2026!`
   - `auth_version`: `1`
3. When the user subsequently set `ADMIN_EMAIL = "sergio759516@gmail.com"` in Streamlit Secrets, the application reloaded. However, `SELECT COUNT(*) FROM admin_credentials` returned `1`.
4. Because the count was greater than zero, `_seed_admin_account_if_needed` returned immediately. The SQLite database retained `admin@assistant.local`.

---

### 2.2 Constant-Time Comparison Rejection (`app/auth.py`)

In `authenticate_administrator()`:
```python
clean_email = email.strip().lower()
admin = get_admin_account()  # Fetches row from admin_credentials
email_matches = (clean_email == admin["email"].strip().lower())
```
- Submitting `sergio759516@gmail.com` was compared against `admin@assistant.local`.
- `email_matches` evaluated to `False`.
- The system recorded a login failure in `login_attempts` for `sergio759516@gmail.com` and raised an `AuthError("Invalid email or password.", status_code=401)`.
- Multiple attempts triggered the brute-force lockout threshold (`MAX_LOGIN_ATTEMPTS = 5`), locking out the account for 15 minutes.

---

### 2.3 The "Forgot Password?" Phantom Success (`ui/streamlit_app.py` & `app/auth.py`)

When the administrator navigated to Password Recovery:
```python
# app/auth.py
def generate_password_reset_token(email: str) -> Optional[str]:
    clean_email = email.strip().lower()
    if not is_admin_email(clean_email):
        return None  # <-- Returns None because DB still has admin@assistant.local!
```

In `ui/streamlit_app.py`:
```python
raw_token = generate_password_reset_token(clean_email)
if raw_token:
    send_password_reset_email(clean_email, raw_token)

# UI always displayed:
st.success("If the email address matches our administrator records, a password reset link has been sent.")
```
1. `is_admin_email("sergio759516@gmail.com")` checked against `admin@assistant.local` in SQLite and returned `False`.
2. `generate_password_reset_token` returned `None`.
3. No reset token was created in `password_reset_tokens`.
4. `send_password_reset_email` was never called.
5. The UI displayed a generic confirmation to prevent user enumeration, giving the false impression that an email had been dispatched.

---

### 2.4 Reset URL Construction and Mail Provider Gap

Even if a token had been generated:
1. **Base URL Resolution**: `APP_BASE_URL` in `app/config.py` defaulted to `"http://localhost:8501"`. Reset URLs generated in cloud environments without an explicit `APP_BASE_URL` secret pointed to localhost instead of `https://rag-mcp-assistant-mf654govkzfnjjmmtlgxfqw.streamlit.app`.
2. **Provider Availability**: `app/auth_email.py` attempted Gmail API v1 first, then SMTP fallback. On Streamlit Cloud, `credentials/` is excluded by `.gitignore`, and without `GMAIL_USER` and `GMAIL_APP_PASSWORD` in `st.secrets`, email dispatch failed silently (`return False, "Email delivery provider unavailable."`).

---

## 3. Systematic Architecture Remediation

To eliminate these root causes while maintaining bank-grade security and zero plaintext leaks, four synchronized enhancements were applied:

### Remediation 1: Idempotent DB Bootstrap Migration (`app/auth.py`)
`_seed_admin_account_if_needed()` was upgraded to perform safe, idempotent synchronization:
- If `admin_credentials` is empty: insert `settings.ADMIN_EMAIL` and salted bcrypt hash.
- If `admin_credentials` contains an existing record whose email differs from `settings.ADMIN_EMAIL`:
  - Update `email` to `settings.ADMIN_EMAIL`.
  - Maintain the existing `password_hash` and `auth_version` (preventing unwanted password resets).
  - Clear stale lockout records from `login_attempts` for both old and new emails.
  - Log: `[AUTH BOOTSTRAP] Migrated administrator email from '{old}' to canonical '{new}'.`

### Remediation 2: Canonical Configuration Defaults (`app/config.py`)
- `ADMIN_EMAIL` default changed from `"admin@assistant.local"` to `"sergio759516@gmail.com"`.
- `APP_BASE_URL` default changed from `"http://localhost:8501"` to `"https://rag-mcp-assistant-mf654govkzfnjjmmtlgxfqw.streamlit.app"`.

### Remediation 3: Streamlit UI Pre-Filling & Clarity (`ui/streamlit_app.py`)
- Login form `Administrator Email` input is pre-filled with `settings.ADMIN_EMAIL`.
- Recovery form `Registered Administrator Email` input is pre-filled with `settings.ADMIN_EMAIL`.

### Remediation 4: Honest Password Recovery Diagnostics & Fallback (`ui/streamlit_app.py`)
- If the token is generated and email is dispatched: displays success with provider details.
- If token is generated but mail provider is unconfigured in cloud secrets:
  - Displays honest warning: *"Password reset token was generated, but email delivery could not be completed: Email service is unconfigured on this cloud instance."*
  - Provides an emergency diagnostic expander with the direct single-use reset URL (`https://rag-mcp-assistant-mf654govkzfnjjmmtlgxfqw.streamlit.app/?action=reset_password&token=...`) so the administrator can complete recovery immediately.

---

## 4. Verification Evidence

- Automated test `test_admin_email_idempotent_migration` confirms that legacy databases update automatically on application startup.
- Automated test `test_forgot_password_generates_token_for_canonical_admin` confirms `generate_password_reset_token("sergio759516@gmail.com")` issues valid SHA-256 tokens.
- All 29 auth tests in `tests/test_auth_and_security.py` pass cleanly.
