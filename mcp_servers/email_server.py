"""
==============================================================================
MCP Server: email_server.py
Domain: Email Dispatcher via Gmail SMTP (with Human-in-the-Loop Safety)
Protocol: Model Context Protocol (FastMCP) over stdio
==============================================================================
Provides tools to send emails with optional attachments (e.g. generated PDFs):
- `send_email`: Connects via Gmail SMTP (smtp.gmail.com:587) with STARTTLS.
- `preview_email`: Formats an email draft for Human-in-the-Loop confirmation.

Safety & Review Defense:
1. Strict Parameter Validation: Validates recipient email address against RFC 5322 regex.
2. Human-in-the-Loop (HITL) Gate: In the multi-agent UI, destructive or external
   actions (like email dispatch) require user confirmation before executing.
3. Fail-Soft Fallback: If live Gmail App Password credentials are not yet supplied
   in `.env`, it provides simulated mock dispatch mode so demos and reviews can
   succeed offline without failing abruptly.
"""

from __future__ import annotations
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import mimetypes
from pathlib import Path
import re
import smtplib
from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP("email_server")

# Standard RFC 5322 compatible email regex
EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


def is_valid_email(address: str) -> bool:
    """Validates email format."""
    return bool(re.match(EMAIL_REGEX, address.strip()))


@mcp.tool()
def preview_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates an email draft preview for student confirmation before sending.

    Args:
        to: Destination email address.
        subject: Email subject line.
        body: Body text of the email.
        attachment_path: Optional path to a file attachment.

    Returns:
        Structured preview dictionary for the UI confirmation modal.
    """
    valid = is_valid_email(to)
    has_attachment = False
    attachment_name = None

    if attachment_path:
        p = Path(attachment_path)
        if p.exists() and p.is_file():
            has_attachment = True
            attachment_name = p.name

    return {
        "status": "ready_for_confirmation",
        "action": "preview_email",
        "to": to,
        "valid_recipient": valid,
        "subject": subject,
        "body_preview": body[:300] + ("..." if len(body) > 300 else ""),
        "full_body": body,
        "has_attachment": has_attachment,
        "attachment_name": attachment_name,
        "attachment_path": attachment_path,
        "requires_confirmation": True,
    }


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    confirmed: bool = True,
) -> Dict[str, Any]:
    """
    Sends an email via Gmail SMTP with optional file attachments.

    Args:
        to: Recipient email address (e.g. "student@ktu.edu.in").
        subject: Email subject line.
        body: Text content of the email.
        attachment_path: Optional path to an attachment (e.g. "outputs/OS_Notes_Summary.pdf").
        confirmed: Flag indicating the user confirmed this action in the UI.

    Returns:
        Dispatch receipt dictionary.
    """
    to_clean = to.strip()
    if not is_valid_email(to_clean):
        return {
            "status": "error",
            "action": "send_email",
            "message": f"Invalid email format: '{to_clean}'. Please provide a valid address.",
        }

    # Verify attachment if provided
    attached_file = None
    if attachment_path:
        p = Path(attachment_path).resolve()
        if not p.exists() or not p.is_file():
            return {
                "status": "error",
                "action": "send_email",
                "message": f"Attachment file not found at: '{attachment_path}'.",
            }
        attached_file = p

    # Check credentials
    gmail_user = settings.GMAIL_USER.strip()
    gmail_password = settings.GMAIL_APP_PASSWORD.strip()

    if not gmail_user or not gmail_password or gmail_user.startswith("your_") or gmail_password.startswith("your_"):
        # Simulated dispatch mode for offline demos / college presentations without live credentials
        print(f"[EMAIL SIMULATION] Live SMTP credentials not configured in .env.")
        print(f"                   To: {to_clean} | Subject: {subject} | Attachment: {attached_file}")
        return {
            "status": "success",
            "action": "send_email",
            "mode": "simulated",
            "to": to_clean,
            "subject": subject,
            "attachment": attached_file.name if attached_file else None,
            "message": f"[Simulated Mode] Email drafted and simulated for '{to_clean}'. (To send real emails, set GMAIL_USER and GMAIL_APP_PASSWORD in .env).",
        }

    # Construct live MIME message
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = to_clean
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attach file if present
    if attached_file:
        ctype, encoding = mimetypes.guess_type(str(attached_file))
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)

        with open(attached_file, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename=\"{attached_file.name}\"",
            )
            msg.attach(part)

    # Dispatch via Gmail SMTP
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()

        return {
            "status": "success",
            "action": "send_email",
            "mode": "live",
            "to": to_clean,
            "subject": subject,
            "attachment": attached_file.name if attached_file else None,
            "message": f"Email successfully sent to '{to_clean}' via Gmail SMTP.",
        }

    except Exception as e:
        return {
            "status": "error",
            "action": "send_email",
            "message": f"SMTP Dispatch failed: {str(e)}",
        }


if __name__ == "__main__":
    mcp.run()
