"""
==============================================================================
Module: app.auth_email
Role in Architecture: Dedicated Restricted Password-Reset Email Dispatcher
==============================================================================
Provides a strictly restricted, single-purpose email sender for administrator
password resets:
1. Strictly Templated: Dispatches only authorized password-reset notifications;
   never accepts arbitrary user-supplied subjects, attachments, or body content.
2. Provider Architecture:
   - Primary: Authenticated Google Workspace Gmail API v1 (via existing OAuth integration)
   - Fallback: Standard Gmail SMTP with App Password (if configured)
3. Fail-Soft Architecture:
   - If mail service is unavailable, logs a generic message without crashing
   - Never exposes tokens, secrets, or internal stack traces in user responses
   - Never logs plaintext passwords or raw tokens to persistent logs
4. Base URL Configuration:
   - Respects APP_BASE_URL (configurable for HTTPS production / domain deployments)
   - Guarantees valid reset links matching the deployment environment
==============================================================================
"""

from __future__ import annotations
import base64
import email.message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import smtplib
from typing import Optional, Tuple

from app.config import settings
from mcp_servers.google_services_server import _get_google_service


def build_password_reset_url(raw_token: str, base_url: Optional[str] = None) -> str:
    """
    Constructs the secure password reset URL.
    Ensures correct base URL (localhost for local dev, HTTPS domain for hosted production).
    """
    base = (base_url or settings.APP_BASE_URL or "http://localhost:8501").rstrip("/")
    return f"{base}/?action=reset_password&token={raw_token}"


def send_password_reset_email(
    to_email: str,
    raw_token: str,
    base_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Sends a password reset link to the administrator.
    Strictly scoped to security notices; no arbitrary message payload allowed.

    Returns:
        (success: bool, info_or_error_message: str)
    """
    reset_url = build_password_reset_url(raw_token, base_url)
    clean_to = to_email.strip().lower()

    subject = "Personal AI Assistant - Administrator Password Reset Request"
    body_text = (
        f"Hello Administrator,\n\n"
        f"A password reset request was received for your Personal AI Assistant account.\n\n"
        f"Click the link below or paste it into your browser to reset your password (valid for 15 minutes):\n"
        f"{reset_url}\n\n"
        f"Note: This link is single-use and will expire automatically in 15 minutes.\n"
        f"If you did not request this password reset, please ignore this email; your existing password remains secure.\n\n"
        f"Regards,\n"
        f"Personal AI Assistant Security Team\n"
    )

    # 1. Attempt delivery via Authenticated Google Workspace Gmail API v1
    try:
        service, _ = _get_google_service("gmail", "v1")
        if service:
            try:
                profile = service.users().getProfile(userId="me").execute()
                sender_email = profile.get("emailAddress") if isinstance(profile, dict) else "me"
            except Exception:
                sender_email = "me"

            mime_msg = MIMEMultipart()
            mime_msg["From"] = sender_email
            mime_msg["To"] = clean_to
            mime_msg["Subject"] = subject
            mime_msg.attach(MIMEText(body_text, "plain", "utf-8"))

            raw_b64 = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
            body_payload = {"raw": raw_b64}

            sent_res = service.users().messages().send(userId="me", body=body_payload).execute()
            if sent_res and sent_res.get("id"):
                print("[AUTH EMAIL] Password reset email successfully dispatched via Gmail API v1.")
                return True, "Password reset email sent successfully via Gmail API."
    except Exception as e:
        print(f"[AUTH EMAIL] Gmail API dispatch attempt encountered an issue: {type(e).__name__}")

    # 2. Fallback: Gmail SMTP with App Password (if configured)
    if settings.GMAIL_USER and settings.GMAIL_APP_PASSWORD and settings.GMAIL_APP_PASSWORD != "your_16_digit_app_password":
        try:
            msg = MIMEText(body_text, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = settings.GMAIL_USER
            msg["To"] = clean_to

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
                server.sendmail(settings.GMAIL_USER, [clean_to], msg.as_string())

            print("[AUTH EMAIL] Password reset email successfully dispatched via Gmail SMTP.")
            return True, "Password reset email sent successfully via SMTP."
        except Exception as e:
            print(f"[AUTH EMAIL] SMTP dispatch failed: {type(e).__name__}")

    # 3. Fail-Soft: Provider unavailable
    print("[AUTH EMAIL] No live email provider available or configured. Failing safely.")
    return False, "Email service is unconfigured on this cloud instance. Please configure GMAIL_USER & GMAIL_APP_PASSWORD or GOOGLE_TOKEN_JSON in Streamlit Secrets."
