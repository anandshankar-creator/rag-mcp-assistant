"""
==============================================================================
Module: ui.streamlit_app
Role in Architecture: Interactive Web Chat UI & Trace Visualization Dashboard
==============================================================================
Provides a polished, demo-ready interface for the student personal assistant:
1. Conversational Chat Interface with message history.
2. Verified Source Citations displayed in an expandable accordion.
3. Collapsible "Debug / Trace" Panel:
   Exposes which agent ran, the routing rationale, cosine similarity scores,
   retrieved document chunks, and exact MCP tool arguments (essential for viva!).
4. Sidebar Document Ingestion:
   Drag-and-drop file upload for PDF, DOCX, TXT, and MD with live ChromaDB indexing.
5. Human-in-the-Loop Confirmation:
   Interactive approval card before sensitive actions (like sending emails) are dispatched.

Run locally:
  streamlit run ui/streamlit_app.py
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

import streamlit as st
from app.config import settings
from agents.graph import run_assistant
from agents.memory import ConversationMemory
from rag.ingest import load_single_document, load_documents
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

# Custom CSS for polished typography, badges, and card containers
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
</style>
""", unsafe_allow_html=True)


# --- Session State Initialization ---
if "session_id" not in st.session_state:
    st.session_state.session_id = "student_session_1"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation = None


# --- Helper Functions ---

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


# --- Sidebar ---

with st.sidebar:
    st.image("https://img.icons8.com/color/96/artificial-intelligence.png", width=64)
    st.markdown("### Assistant Profile")
    st.caption("Final Year B.Tech Project • KTU S7")

    # System Status Indicator
    with st.container():
        st.markdown(f"**LLM Provider**: `{settings.LLM_PROVIDER}` (`{settings.GEMINI_MODEL}`)")
        st.markdown(f"**Vector DB**: `ChromaDB` (Local Persistent)")
        st.markdown(f"**Protocol**: `Model Context Protocol (FastMCP)`")
    st.divider()

    # User Preferences
    st.markdown("#### ⚙️ Student Settings")
    curr_name = ConversationMemory.get_preference("name", settings.USER_NAME)
    curr_email = ConversationMemory.get_preference("email", settings.USER_DEFAULT_EMAIL)

    new_name = st.text_input("Student Name", value=curr_name)
    new_email = st.text_input("University Email", value=curr_email)
    if st.button("Save Profile", use_container_width=True):
        ConversationMemory.set_preference("name", new_name)
        ConversationMemory.set_preference("email", new_email)
        st.success("Profile updated!")

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
                dest = settings.DATA_DIR / uploaded_file.name
                with open(dest, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Ingest into vector store
                docs = load_single_document(dest)
                chunks = chunk_documents(docs)
                store = get_vector_store()
                store.delete_document(uploaded_file.name)
                added = store.add_chunks(chunks)
                st.success(f"Indexed {len(docs)} page(s) into {added} semantic chunks!")
                time.sleep(1)
                st.rerun()

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
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show Sources if present
        if msg.get("citations"):
            with st.expander("📚 Grounded Sources & Citations", expanded=False):
                for c in msg["citations"]:
                    st.markdown(f"- `{c}`")

        # Show Action Receipts if present
        if msg.get("action_receipts"):
            for act in msg["action_receipts"]:
                tool_name = act.get("tool_name", "tool")
                receipt = act.get("receipt", {})
                status_badge = "✅" if receipt.get("status") == "success" else "⚠️"
                raw_res = receipt.get("result")
                if isinstance(raw_res, dict):
                    msg_text = raw_res.get("message") or receipt.get("message") or f"{tool_name} executed."
                elif isinstance(raw_res, list):
                    msg_text = f"{len(raw_res)} item(s) found."
                else:
                    msg_text = str(raw_res) if raw_res else receipt.get("message") or f"{tool_name} executed."
                st.markdown(f'<div class="action-card">{status_badge} <b>{tool_name}</b>: {msg_text}</div>', unsafe_allow_html=True)

        # Show Collapsible Debug / Trace Panel (VIVA DEMO PANEL)
        if msg.get("trace"):
            with st.expander("🔍 Debug / Trace Telemetry (Agent Decisions)", expanded=False):
                route = msg.get("route", "UNKNOWN")
                reasoning = msg.get("route_reasoning", "")
                st.markdown(f'<span class="badge-route">Route: {route}</span> {reasoning}', unsafe_allow_html=True)

                trace_events = msg.get("trace", [])
                for idx, t in enumerate(trace_events, 1):
                    agent_name = t.get("agent", "Agent")
                    node_name = t.get("node", "node")
                    details = t.get("details", "")
                    latency = t.get("latency_sec")
                    lat_str = f" • {latency}s" if latency else ""
                    st.markdown(f"**[{idx}] {agent_name}** (`{node_name}`{lat_str})")
                    st.caption(details)

                    # Show retrieved chunks preview if in RAG node
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
                },
            )
            st.session_state.pending_confirmation = None
            st.success("Action dispatched successfully!")
            time.sleep(1)
            st.rerun()
    with col_btn2:
        if st.button("❌ Cancel Action", use_container_width=True):
            st.session_state.pending_confirmation = None
            st.info("Action canceled by student.")
            time.sleep(1)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# --- User Input Box ---
if prompt := st.chat_input("Ask a question, request a task, or manage your schedule..."):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process through LangGraph Assistant
    with st.chat_message("assistant"):
        with st.spinner("Processing request through Multi-Agent Orchestrator..."):
            result_state = run_assistant(prompt, session_id=st.session_state.session_id)

            response_content = result_state.get("final_response", "")
            citations = result_state.get("citations", [])
            action_receipts = result_state.get("action_receipts", [])
            trace = result_state.get("trace", [])
            route = result_state.get("route", "CHAT")
            route_reasoning = result_state.get("route_reasoning", "")

            # Display response
            st.markdown(response_content)

            # Display sources
            if citations:
                with st.expander("📚 Grounded Sources & Citations", expanded=False):
                    for c in citations:
                        st.markdown(f"- `{c}`")

            # Display action receipts
            if action_receipts:
                for act in action_receipts:
                    t_name = act.get("tool_name", "tool")
                    rec = act.get("receipt", {})
                    badge = "✅" if rec.get("status") == "success" else "⚠️"
                    raw_res = rec.get("result")
                    if isinstance(raw_res, dict):
                        inner_msg = raw_res.get("message") or rec.get("message") or f"{t_name} executed."
                    elif isinstance(raw_res, list):
                        inner_msg = f"{len(raw_res)} item(s) found."
                    else:
                        inner_msg = str(raw_res) if raw_res else rec.get("message") or f"{t_name} executed."
                    st.markdown(f'<div class="action-card">{badge} <b>{t_name}</b>: {inner_msg}</div>', unsafe_allow_html=True)

            # Display Debug Trace
            if trace:
                with st.expander("🔍 Debug / Trace Telemetry (Agent Decisions)", expanded=False):
                    st.markdown(f'<span class="badge-route">Route: {route}</span> {route_reasoning}', unsafe_allow_html=True)
                    for idx, t in enumerate(trace, 1):
                        agent_name = t.get("agent", "Agent")
                        node_name = t.get("node", "node")
                        details = t.get("details", "")
                        st.markdown(f"**[{idx}] {agent_name}** (`{node_name}`)")
                        st.caption(details)

            # Check if this requires email confirmation
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

            # Save assistant message to session state
            st.session_state.messages.append({
                "role": "assistant",
                "content": response_content,
                "citations": citations,
                "action_receipts": action_receipts,
                "trace": trace,
                "route": route,
                "route_reasoning": route_reasoning,
            })
