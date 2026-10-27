"""
==============================================================================
Module: ui.streamlit_app
Role in Architecture: Interactive Web Chat UI & Trace Visualization Dashboard
==============================================================================
Provides a polished, secure interface for the Personal Assistant:
1. Administrator-Only Authentication:
   - Dedicated sign-in page with email & salted bcrypt password verification
   - Brute-force protection & progressive lockout
   - Secure session management with explicit logout token revocation
   - Single-use Password Reset ("Forgot Password?") workflow with 15-minute token expiry
2. Conversational Chat Interface with message history & session persistence.
3. Verified Source Citations displayed in an expandable accordion.
4. Collapsible "Debug / Trace Telemetry" Panel:
   Exposes routing decisions, cosine similarity, chunk text, and MCP tool execution.
5. Sidebar Document Ingestion:
   Drag-and-drop file upload for PDF, DOCX, TXT, and MD with live ChromaDB indexing.
6. Direct In-Chat PDF Download Delivery with secure magic bytes validation.
7. Human-in-the-Loop Confirmation:
   Interactive approval card before sensitive actions (like sending emails) are dispatched.
==============================================================================
"""

from __future__ import annotations
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Safe sqlite3 monkey-patch for Streamlit Community Cloud (Linux)
try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import streamlit as st
from app.config import settings
from app.auth import (
    authenticate_administrator,
    check_reset_request_rate_limit,
    generate_password_reset_token,
    reset_password_with_token,
    revoke_token,
    verify_access_token,
    verify_password_reset_token,
    AuthError,
)
from app.auth_email import send_password_reset_email, build_password_reset_url
from agents.graph import run_assistant
from agents.memory import ConversationMemory
from rag.ingest import load_single_document
from rag.chunking import chunk_documents
from rag.vectorstore import get_vector_store
from mcp_servers.client import get_mcp_client


# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="RAG-MCP Personal Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished typography, badges, and compact sidebar
st.markdown("""
<style>
    .main-title {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    .badge-route {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        font-size: 0.8rem;
        font-weight: 600;
        border-radius: 6px;
        background-color: #DBEAFE;
        color: #1E40AF;
        margin-right: 0.5rem;
    }
    .action-card {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
        font-size: 0.9rem;
    }
    .hitl-box {
        background-color: #FEF3C7;
        border: 1px solid #F59E0B;
        border-radius: 6px;
        padding: 1rem;
        margin: 0.8rem 0;
    }
    /* Compact Sidebar styling to prevent vertical scrolling */
    [data-testid="stSidebar"] {
        padding-top: 0.8rem !important;
    }
    [data-testid="stSidebar"] .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 0.8rem !important;
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
    }
    [data-testid="stSidebar"] hr {
        margin-top: 0.4rem !important;
        margin-bottom: 0.4rem !important;
    }
    [data-testid="stSidebar"] .stMarkdown p {
        margin-bottom: 0.2rem !important;
        font-size: 0.84rem !important;
        line-height: 1.3 !important;
    }
    [data-testid="stSidebar"] h3 {
        font-size: 1.15rem !important;
        margin-bottom: 0.15rem !important;
        padding-top: 0 !important;
    }
    [data-testid="stSidebar"] h4 {
        font-size: 0.92rem !important;
        margin-top: 0.2rem !important;
        margin-bottom: 0.3rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] .stTextInput input {
        padding: 0.25rem 0.5rem !important;
        font-size: 0.85rem !important;
        height: 2.1rem !important;
    }
    [data-testid="stSidebar"] .stButton button {
        padding: 0.25rem 0.5rem !important;
        font-size: 0.82rem !important;
        height: 2.1rem !important;
        min-height: 2.1rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        padding: 0.5rem !important;
    }
</style>
""", unsafe_allow_html=True)


# --- Session State Initialization ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "admin_email" not in st.session_state:
    st.session_state.admin_email = None
if "auth_view" not in st.session_state:
    st.session_state.auth_view = "login"
if "session_id" not in st.session_state:
    st.session_state.session_id = "admin_session_1"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation = None
if "password_reset_done" not in st.session_state:
    st.session_state.password_reset_done = False


# Validate active session token if user is authenticated
if st.session_state.authenticated and st.session_state.auth_token:
    try:
        verify_access_token(st.session_state.auth_token)
    except Exception:
        # Session expired, logged out, or invalidated by password change
        st.session_state.authenticated = False
        st.session_state.auth_token = None
        st.session_state.admin_email = None
        st.session_state.messages = []
        st.session_state.auth_view = "login"


# --- Authentication Views ---

def render_login_view():
    """Renders the professional Administrator Sign-In portal."""
    st.markdown("""
        <div style="max-width: 480px; margin: 30px auto 10px auto; text-align: center;">
            <span style="font-size: 3rem;">🔒</span>
            <h2 style="color: #1E3A8A; font-weight: 700; margin-top: 6px; margin-bottom: 2px;">Administrator Sign In</h2>
            <p style="color: #64748B; font-size: 0.95rem;">RAG & MCP Multi-Agent Personal Assistant</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        with st.form("admin_login_form"):
            email_val = st.text_input("Administrator Email", value=settings.ADMIN_EMAIL, placeholder=settings.ADMIN_EMAIL)
            password_val = st.text_input("Password", type="password", placeholder="Enter administrator password")
            submit_btn = st.form_submit_button("Sign In", use_container_width=True, type="primary")

            if submit_btn:
                clean_email = email_val.strip().lower()
                client_id = clean_email or "unknown_admin"
                try:
                    res = authenticate_administrator(clean_email, password_val, client_id=client_id)
                    st.session_state.auth_token = res["access_token"]
                    st.session_state.admin_email = res["admin_email"]
                    st.session_state.authenticated = True
                    st.session_state.auth_view = "app"
                    st.toast("Signed in successfully!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
                except AuthError as e:
                    st.error(f"❌ {e.message}")

        col_space, col_forgot = st.columns([1, 1])
        with col_forgot:
            if st.button("Forgot Password?", use_container_width=True, type="secondary"):
                st.session_state.auth_view = "forgot_password"
                st.rerun()


def render_forgot_password_view():
    """Renders the Password Recovery request page."""
    st.markdown("""
        <div style="max-width: 480px; margin: 30px auto 10px auto; text-align: center;">
            <span style="font-size: 3rem;">🔑</span>
            <h2 style="color: #1E3A8A; font-weight: 700; margin-top: 6px; margin-bottom: 2px;">Password Recovery</h2>
            <p style="color: #64748B; font-size: 0.95rem;">Enter your administrator email to receive a secure, single-use reset link.</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        with st.form("forgot_password_form"):
            email_val = st.text_input("Registered Administrator Email", value=settings.ADMIN_EMAIL, placeholder=settings.ADMIN_EMAIL)
            submit_btn = st.form_submit_button("Send Reset Link", use_container_width=True, type="primary")

            if submit_btn:
                clean_email = email_val.strip().lower()
                allowed, rate_msg = check_reset_request_rate_limit(clean_email or "unknown")
                if not allowed:
                    st.error(f"⚠️ {rate_msg}")
                else:
                    raw_token = generate_password_reset_token(clean_email)
                    if raw_token:
                        try:
                            sent_ok, send_msg = send_password_reset_email(clean_email, raw_token)
                        except Exception as e:
                            sent_ok, send_msg = False, str(e)
                            print(f"[UI FORGOT PWD] Failed to send email: {e}")

                        if sent_ok:
                            st.success("✅ A password reset link has been dispatched to your administrator email.")
                            st.info("The reset link is valid for 15 minutes and can only be used once.")
                        else:
                            st.warning(f"⚠️ Password reset token was generated, but email delivery could not be completed: {send_msg}")
                            st.info(
                                "On Streamlit Community Cloud, add `GMAIL_USER` & `GMAIL_APP_PASSWORD` or `GOOGLE_TOKEN_JSON` "
                                "in your app secrets to receive automated emails."
                            )
                            reset_url = build_password_reset_url(raw_token)
                            with st.expander("🛠️ Admin Direct Reset Link (Emergency Diagnostic)"):
                                st.caption("Because cloud email transport is not configured, you can use this single-use link directly:")
                                st.code(reset_url, language="text")
                    else:
                        st.success("✅ If the email address matches our administrator records, a password reset link has been sent.")
                        st.info("The reset link is valid for 15 minutes and can only be used once.")

        if st.button("← Back to Sign In", use_container_width=True):
            st.session_state.auth_view = "login"
            st.rerun()


def render_reset_password_view(raw_token: str):
    """Renders the Set New Password view using the single-use token."""
    st.markdown("""
        <div style="max-width: 480px; margin: 30px auto 10px auto; text-align: center;">
            <span style="font-size: 3rem;">🔐</span>
            <h2 style="color: #1E3A8A; font-weight: 700; margin-top: 6px; margin-bottom: 2px;">Set New Password</h2>
            <p style="color: #64748B; font-size: 0.95rem;">Create a strong new password for your administrator account.</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        is_valid, email, err_msg = verify_password_reset_token(raw_token)
        if not is_valid:
            st.error(f"⚠️ {err_msg}")
            if st.button("Return to Sign In", use_container_width=True, type="primary"):
                st.query_params.clear()
                st.session_state.auth_view = "login"
                st.rerun()
            return

        st.caption(f"Resetting password for: `{email}`")
        with st.form("set_new_password_form"):
            new_pwd = st.text_input("New Password", type="password", placeholder="Minimum 8 characters with letters & numbers")
            confirm_pwd = st.text_input("Confirm New Password", type="password", placeholder="Re-enter new password")
            submit_btn = st.form_submit_button("Update Password", use_container_width=True, type="primary")

            if submit_btn:
                if new_pwd != confirm_pwd:
                    st.error("Passwords do not match. Please re-enter identical passwords.")
                else:
                    success, msg = reset_password_with_token(raw_token, new_pwd)
                    if not success:
                        st.error(f"❌ {msg}")
                    else:
                        st.success("✅ Password updated successfully! All active sessions have been invalidated.")
                        st.session_state.password_reset_done = True

        if st.session_state.get("password_reset_done"):
            st.markdown(
                '<a href="/" target="_self" style="display: block; text-align: center; padding: 0.5rem; background: #1E40AF; color: white; border-radius: 6px; text-decoration: none; font-weight: 600; margin-top: 12px;">Proceed to Sign In</a>',
                unsafe_allow_html=True,
            )
        else:
            if st.button("Cancel & Return to Sign In", use_container_width=True):
                st.query_params.clear()
                st.session_state.auth_view = "login"
                st.rerun()


# --- Authentication Routing & Security Gate ---

query_action = st.query_params.get("action")
query_token = st.query_params.get("token")

if query_action == "reset_password" or query_token:
    render_reset_password_view(query_token or "")
    st.stop()

if not st.session_state.authenticated:
    if st.session_state.auth_view == "forgot_password":
        render_forgot_password_view()
    else:
        render_login_view()
    st.stop()


# ==============================================================================
# AUTHENTICATED APPLICATION AREA (Protected)
# ==============================================================================

def refresh_documents_list():
    """Fetches collection statistics and local file records."""
    store = get_vector_store()
    stats = store.get_collection_stats()
    files = []
    if settings.DATA_DIR.exists():
        for p in settings.DATA_DIR.glob("*"):
            if p.is_file() and not p.name.startswith("."):
                files.append({
                    "name": p.name,
                    "size": round(p.stat().st_size / 1024, 1),
                    "indexed": p.name in stats.get("source_files", []),
                })
    return stats, files


def render_pdf_download_card(filename: str, key_suffix: str = ""):
    """
    Renders an authenticated, secure downloadable PDF card inside the chat response.
    Never exposes raw filesystem paths; validates that the file exists and has valid PDF magic bytes.
    """
    safe_name = Path(filename).name.strip()
    pdf_path = (settings.OUTPUTS_DIR / safe_name).resolve()

    if not str(pdf_path).startswith(str(settings.OUTPUTS_DIR.resolve())):
        st.error("⚠️ Invalid PDF file request: path traversal detected.")
        return

    if not pdf_path.exists() or not pdf_path.is_file():
        st.warning(f"📄 **{safe_name}** — *File not found or expired on server.*")
        return

    file_size = pdf_path.stat().st_size
    if file_size == 0:
        st.error(f"⚠️ PDF **{safe_name}** is empty or corrupt.")
        return

    try:
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                st.error(f"⚠️ File **{safe_name}** does not contain a valid PDF signature.")
                return
            f.seek(0)
            pdf_bytes = f.read()

        size_kb = round(file_size / 1024, 1)
        st.markdown(
            f"""
            <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 10px 14px; margin: 8px 0;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <span style="font-size: 1.25rem;">📄</span>
                        <strong style="color: #1E3A8A; font-size: 0.95rem; margin-left: 6px;">{safe_name}</strong>
                        <span style="color: #64748B; font-size: 0.8rem; margin-left: 8px;">({size_kb} KB • Academic PDF)</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.download_button(
            label=f"📥 Download PDF ({safe_name})",
            data=pdf_bytes,
            file_name=safe_name,
            mime="application/pdf",
            key=f"dl_pdf_{safe_name}_{key_suffix}",
            use_container_width=True,
            type="primary",
        )
    except Exception as e:
        st.error(f"Failed to prepare download for '{safe_name}': {e}")


# --- Sidebar ---

with st.sidebar:
    st.image("https://img.icons8.com/color/96/artificial-intelligence.png", width=44)
    st.markdown("### Assistant Profile")
    st.caption("Final Year B.Tech Project • KTU S7")

    # Administrator Session Header with Sign Out
    col_adm, col_logout = st.columns([2.5, 1.5])
    with col_adm:
        st.markdown(f"👤 **Admin**\n`{st.session_state.get('admin_email', 'admin')}`")
    with col_logout:
        if st.button("🚪 Logout", use_container_width=True, type="secondary"):
            if st.session_state.get("auth_token"):
                revoke_token(st.session_state.auth_token)
            st.session_state.authenticated = False
            st.session_state.auth_token = None
            st.session_state.admin_email = None
            st.session_state.messages = []
            st.session_state.auth_view = "login"
            st.rerun()

    st.divider()

    # System Status Indicator
    with st.container():
        st.markdown(f"**LLM Provider**: `{settings.LLM_PROVIDER}` (`{settings.GEMINI_MODEL}`)")
        st.markdown(f"**Vector DB**: `ChromaDB` (Local Persistent)")
        st.markdown(f"**Protocol**: `Model Context Protocol (FastMCP)`")
    st.divider()

    # Admin Settings (Compact layout, no email input)
    st.markdown("#### ⚙️ Admin Settings")
    curr_name = ConversationMemory.get_preference("admin_name", ConversationMemory.get_preference("name", "Administrator"))

    col_name, col_btn = st.columns([2.4, 1.4])
    with col_name:
        new_name = st.text_input(
            "Admin Name",
            value=curr_name,
            label_visibility="collapsed",
            placeholder="Admin Name",
        )
    with col_btn:
        if st.button("Save Profile", use_container_width=True):
            cleaned_name = new_name.strip() or "Administrator"
            ConversationMemory.set_preference("admin_name", cleaned_name)
            ConversationMemory.set_preference("name", cleaned_name)
            st.toast("Admin profile updated!", icon="✅")

    st.divider()

    # Knowledge Base & File Upload
    st.markdown("#### 📁 Knowledge Base Manager")
    uploaded_file = st.file_uploader(
        "Upload Note, Syllabus, or Schedule",
        type=["pdf", "txt", "docx", "md"],
        help="Supports PDF, Word (.docx), plain text (.txt), and Markdown (.md)",
    )

    if uploaded_file is not None:
        if st.button("Index Document into ChromaDB", use_container_width=True, type="primary"):
            with st.spinner("Extracting text, chunking, and computing vector embeddings..."):
                try:
                    dest = settings.DATA_DIR / uploaded_file.name
                    with open(dest, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    docs = load_single_document(dest)
                    if not docs or all(not (getattr(d, "content", "") or getattr(d, "text", "")).strip() for d in docs):
                        st.error(f"Text extraction failed for '{uploaded_file.name}'. The document is empty or text could not be extracted.")
                        if dest.exists():
                            dest.unlink()
                    else:
                        chunks = chunk_documents(docs)
                        if not chunks:
                            st.error(f"Chunking failed for '{uploaded_file.name}'. No semantic chunks could be created.")
                            if dest.exists():
                                dest.unlink()
                        else:
                            store = get_vector_store()
                            store.delete_document(uploaded_file.name)
                            added = store.add_chunks(chunks)
                            if added == 0:
                                st.error(f"ChromaDB insertion failed for '{uploaded_file.name}'. 0 chunks were indexed.")
                            else:
                                ConversationMemory.set_preference("last_uploaded_doc", uploaded_file.name)
                                st.session_state["last_uploaded_doc"] = uploaded_file.name
                                st.success(f"Indexed {len(docs)} page(s) into {added} semantic chunks!")
                                time.sleep(1)
                                st.rerun()
                except Exception as e:
                    st.error(f"Document indexing failed: {e}")

    # Document Inventory
    stats, doc_files = refresh_documents_list()
    st.caption(f"Total Chunks in Database: **{stats.get('total_chunks', 0)}**")

    with st.expander("📚 Stored Documents", expanded=False):
        for d in doc_files:
            col1, col2 = st.columns([3, 1])
            with col1:
                status_icon = "🟢" if d["indexed"] else "⚪"
                st.text(f"{status_icon} {d['name']} ({d['size']} KB)")
            with col2:
                if st.button("🗑️", key=f"del_{d['name']}"):
                    store = get_vector_store()
                    store.delete_document(d["name"])
                    p = settings.DATA_DIR / d["name"]
                    if p.exists():
                        p.unlink()
                    if ConversationMemory.get_preference("last_uploaded_doc") == d["name"]:
                        ConversationMemory.set_preference("last_uploaded_doc", "")
                    st.rerun()

    st.divider()
    if st.button("🧹 Clear Chat Session", use_container_width=True):
        st.session_state.messages = []
        ConversationMemory.clear_session(st.session_state.session_id)
        st.rerun()


# --- Main Chat Area ---

st.markdown('<div class="main-title">Personal AI Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Retrieval-Augmented Generation (RAG) + Model Context Protocol (MCP) + LangGraph Multi-Agent Architecture</div>', unsafe_allow_html=True)

# Render Chat History
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show Sources if present
        if msg.get("citations"):
            with st.expander("📚 Grounded Sources & Citations", expanded=False):
                for c in msg["citations"]:
                    st.markdown(f"- `{c}`")

        # Show Action Receipts and PDF Download Attachments
        if msg.get("action_receipts"):
            for act_idx, act in enumerate(msg["action_receipts"]):
                tool_name = act.get("tool_name", "tool")
                receipt = act.get("receipt", {})
                status_badge = "✅" if receipt.get("status") == "success" else "⚠️"
                raw_res = receipt.get("result")

                # If generate_pdf, render the secure downloadable PDF card
                if tool_name == "generate_pdf" and receipt.get("status") == "success":
                    fname = (raw_res.get("filename") if isinstance(raw_res, dict) else act.get("arguments", {}).get("filename")) or "document.pdf"
                    render_pdf_download_card(fname, key_suffix=f"hist_{msg_idx}_{act_idx}")

                if isinstance(raw_res, dict):
                    if tool_name == "generate_pdf":
                        fname = raw_res.get("filename") or act.get("arguments", {}).get("filename", "document.pdf")
                        msg_text = f"Compiled PDF '{Path(fname).name}' — available for download above."
                    else:
                        msg_text = raw_res.get("message") or receipt.get("message") or f"{tool_name} executed."
                elif isinstance(raw_res, list):
                    msg_text = f"{len(raw_res)} item(s) found."
                else:
                    msg_text = str(raw_res) if raw_res else receipt.get("message") or f"{tool_name} executed."
                st.markdown(f'<div class="action-card">{status_badge} <b>{tool_name}</b>: {msg_text}</div>', unsafe_allow_html=True)

        # Show Collapsible Debug / Trace Panel
        if msg.get("trace"):
            with st.expander("🔍 Debug / Trace Telemetry (Agent Decisions)", expanded=False):
                route = msg.get("route", "UNKNOWN")
                reasoning = msg.get("route_reasoning", "")
                st.markdown(f'<span class="badge-route">Route: {route}</span> {reasoning}', unsafe_allow_html=True)
                if msg.get("decision_path"):
                    st.markdown(f"**Decision Path:** `{msg.get('decision_path')}`")

                trace_events = msg.get("trace", [])
                for idx, t in enumerate(trace_events, 1):
                    agent_name = t.get("agent", "Agent")
                    node_name = t.get("node", "node")
                    details = t.get("details", "")
                    latency = t.get("latency_sec")
                    lat_str = f" • {latency}s" if latency else ""
                    st.markdown(f"**[{idx}] {agent_name}** (`{node_name}`{lat_str})")
                    st.caption(details)

                    if t.get("max_similarity") is not None:
                        st.caption(f"Cosine Similarity Peak: `{t.get('max_similarity'):.4f}` • Refused: `{t.get('refused')}`")


# --- Human-in-the-Loop Confirmation Card ---
if st.session_state.pending_confirmation:
    conf = st.session_state.pending_confirmation
    st.markdown('<div class="hitl-box">', unsafe_allow_html=True)
    st.markdown("### ⚠️ Human-in-the-Loop Approval Required")
    st.markdown(f"The assistant is preparing to execute an external tool: **`{conf['action']}`**")
    st.markdown(f"**Recipient**: `{conf.get('to')}`")
    st.markdown(f"**Subject**: `{conf.get('subject')}`")
    if conf.get("attachment"):
        st.markdown(f"**Attachment**: `{conf.get('attachment')}`")
    st.markdown(f"**Message Body**:\n> {conf.get('body')}")

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("✅ Approve & Send", type="primary", use_container_width=True):
            mcp_client = get_mcp_client()
            res = mcp_client.execute_tool(
                "send_email",
                {
                    "to": conf.get("to"),
                    "subject": conf.get("subject"),
                    "body": conf.get("body"),
                    "attachment_path": conf.get("attachment"),
                    "confirmed": True,
                    "session_id": st.session_state.session_id,
                },
            )
            st.session_state.pending_confirmation = None
            if res.get("status") == "success":
                raw_res = res.get("result", {})
                msg_id = raw_res.get("message_id") if isinstance(raw_res, dict) else ""
                info_id = f" (Message ID: {msg_id})" if msg_id else ""
                st.success(f"Email sent successfully via Gmail!{info_id}")
            else:
                err = res.get("message") or (res.get("result", {}).get("message") if isinstance(res.get("result"), dict) else "Send failed.")
                st.error(f"Email sending failed: {err}")
            time.sleep(1)
            st.rerun()
    with col_btn2:
        if st.button("❌ Cancel Action", use_container_width=True):
            st.session_state.pending_confirmation = None
            st.info("Action canceled by administrator.")
            time.sleep(1)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# --- User Input Box ---
if prompt := st.chat_input("Ask a question, request a task, or manage your schedule..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Processing request through Multi-Agent Orchestrator..."):
            result_state = run_assistant(prompt, session_id=st.session_state.session_id)

            response_content = result_state.get("final_response", "")
            citations = result_state.get("citations", [])
            action_receipts = result_state.get("action_receipts", [])
            trace = result_state.get("trace", [])
            route = result_state.get("route", "CHAT")
            route_reasoning = result_state.get("route_reasoning", "")

            st.markdown(response_content)

            if citations:
                with st.expander("📚 Grounded Sources & Citations", expanded=False):
                    for c in citations:
                        st.markdown(f"- `{c}`")

            if action_receipts:
                for act_idx, act in enumerate(action_receipts):
                    t_name = act.get("tool_name", "tool")
                    rec = act.get("receipt", {})
                    badge = "✅" if rec.get("status") == "success" else "⚠️"
                    raw_res = rec.get("result")

                    if t_name == "generate_pdf" and rec.get("status") == "success":
                        fname = (raw_res.get("filename") if isinstance(raw_res, dict) else act.get("arguments", {}).get("filename")) or "document.pdf"
                        render_pdf_download_card(fname, key_suffix=f"live_{act_idx}")

                    if isinstance(raw_res, dict):
                        if t_name == "generate_pdf":
                            fname = raw_res.get("filename") or act.get("arguments", {}).get("filename", "document.pdf")
                            inner_msg = f"Compiled PDF '{Path(fname).name}' — available for download above."
                        else:
                            inner_msg = raw_res.get("message") or rec.get("message") or f"{t_name} executed."
                    elif isinstance(raw_res, list):
                        inner_msg = f"{len(raw_res)} item(s) found."
                    else:
                        inner_msg = str(raw_res) if raw_res else rec.get("message") or f"{t_name} executed."
                    st.markdown(f'<div class="action-card">{badge} <b>{t_name}</b>: {inner_msg}</div>', unsafe_allow_html=True)

            decision_path = result_state.get("decision_path", "")
            if trace:
                with st.expander("🔍 Debug / Trace Telemetry (Agent Decisions)", expanded=False):
                    st.markdown(f'<span class="badge-route">Route: {route}</span> {route_reasoning}', unsafe_allow_html=True)
                    if decision_path:
                        st.markdown(f"**Decision Path:** `{decision_path}`")
                    for idx, t in enumerate(trace, 1):
                        agent_name = t.get("agent", "Agent")
                        node_name = t.get("node", "node")
                        details = t.get("details", "")
                        st.markdown(f"**[{idx}] {agent_name}** (`{node_name}`)")
                        st.caption(details)

            for act in action_receipts:
                if act.get("tool_name") == "preview_email":
                    raw_res = act.get("receipt", {}).get("result")
                    rec = raw_res if isinstance(raw_res, dict) else {}
                    st.session_state.pending_confirmation = {
                        "action": "send_email",
                        "to": rec.get("to"),
                        "subject": rec.get("subject"),
                        "body": rec.get("full_body"),
                        "attachment": rec.get("attachment_path"),
                    }
                    st.rerun()

            st.session_state.messages.append({
                "role": "assistant",
                "content": response_content,
                "citations": citations,
                "action_receipts": action_receipts,
                "trace": trace,
                "route": route,
                "route_reasoning": route_reasoning,
                "decision_path": decision_path,
            })
