"""
==============================================================================
Module: agents.graph
Role in Architecture: LangGraph Multi-Agent Orchestration State Machine
==============================================================================
Defines the stateful Multi-Agent execution graph:

Workflow:
User Input
   │
   ▼
[load_context] (SQLite Chat History + Student Preferences)
   │
   ▼
[router_node] ──► Classifies: QA | ACTION | CHAINED | CHAT
   │
   ├─► [rag_node] ──────► Grounded Context Retrieval & Citations ──┐
   ├─► [action_node] ───► Dynamic MCP Tool Selection & Execution ──┤
   ├─► [chat_node] ─────► Conversational Intelligence (ChatGPT/Gemini) ─┤
   └─► [planner_node] ──► Deconstructs to JSON Step DAG            │
            │                                                      │
            ▼                                                      │
       [executor_node] ─► Sequential Chained Execution             │
            │                                                      │
            └──────────────────────────────────────────────────────┤
                                                                   ▼
                                                          [responder_node]
                                                                   │
                                                                   ▼
                                                          Final Answer + Trace
"""

from __future__ import annotations
import datetime
import re
import time
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END

from app.config import settings
from llm import get_llm_client, LLMResponse
from agents.memory import ConversationMemory
from agents.orchestrator import get_router, is_profile_query, is_action_followup_query
from agents.planner import get_planner
from agents.rag_agent import get_rag_agent
from agents.action_agent import get_action_agent
from mcp_servers.client import get_mcp_client


class AgentState(TypedDict, total=False):
    """Encapsulates the complete state passed across all agent nodes."""
    session_id: str
    user_message: str
    chat_history: List[Dict[str, str]]
    user_preferences: Dict[str, str]
    route: str
    route_reasoning: str
    plan: List[Dict[str, Any]]
    rag_result: Dict[str, Any]
    action_receipts: List[Dict[str, Any]]
    final_response: str
    citations: List[str]
    trace: List[Dict[str, Any]]
    user_confirmed_actions: Optional[bool]
    origin: str
    source_type: str
    urls: List[str]
    tiers: List[Dict[str, Any]]
    verified_quotes: List[str]
    decision_path: str


# --- Graph Node Implementations ---

def load_context_node(state: AgentState) -> Dict[str, Any]:
    """Loads previous turns and preferences from SQLite."""
    session_id = state.get("session_id", "default_user")
    history = ConversationMemory.get_recent_history(session_id, last_n=6)
    prefs = ConversationMemory.get_all_preferences()
    user_name = prefs.get("name", settings.USER_NAME)

    trace_entry = {
        "node": "load_context",
        "agent": "Memory Component",
        "timestamp": datetime.datetime.now().isoformat(),
        "details": f"Loaded {len(history)} previous turns and profile preferences for {user_name}.",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "chat_history": history,
        "user_preferences": prefs,
        "trace": current_trace,
    }


def router_node(state: AgentState) -> Dict[str, Any]:
    """Classifies user intent into QA, ACTION, CHAINED, or CHAT."""
    user_msg = state["user_message"].strip()

    if is_profile_query(user_msg):
        route = "CHAT"
        reasoning = "Inquiry about user profile preferences and configured email identity."
    elif is_action_followup_query(user_msg):
        route = "CHAT"
        reasoning = "Follow-up inquiry about previous action execution and tool results."
    else:
        router = get_router()
        history = state.get("chat_history", [])
        classification = router.classify_intent(user_msg, history)
        route = classification.get("route", "CHAT")
        reasoning = classification.get("reasoning", "")

    trace_entry = {
        "node": "router_node",
        "agent": "Orchestrator Router",
        "timestamp": datetime.datetime.now().isoformat(),
        "route_selected": route,
        "details": f"Classified intent as [{route}]. Reasoning: {reasoning}",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "route": route,
        "route_reasoning": reasoning,
        "trace": current_trace,
    }


def route_decision(state: AgentState) -> str:
    """Conditional edge router."""
    route = state.get("route", "CHAT")
    if route == "QA":
        return "rag_node"
    elif route == "ACTION":
        return "action_node"
    elif route == "CHAINED":
        return "planner_node"
    else:
        return "chat_node"


def rag_node(state: AgentState) -> Dict[str, Any]:
    """Retrieves grounded document context and formats citations."""
    rag_agent = get_rag_agent()
    user_msg = state["user_message"]

    start_time = time.time()
    rag_output = rag_agent.run(user_msg)
    elapsed = round(time.time() - start_time, 2)

    decision_path = rag_output.get("decision_path", "")
    trace_entry = {
        "node": "rag_node",
        "agent": "RAG Knowledge Agent",
        "timestamp": datetime.datetime.now().isoformat(),
        "latency_sec": elapsed,
        "max_similarity": rag_output.get("max_similarity", 0.0),
        "refused": rag_output.get("refused", False),
        "source_type": rag_output.get("source_type", "local_rag"),
        "chunks_retrieved": len(rag_output.get("retrieved_chunks", [])),
        "citations_count": len(rag_output.get("citations", [])),
        "decision_path": decision_path,
        "details": f"Decision: [{decision_path or rag_output.get('source_type', 'local_rag')}]. Chunks: {len(rag_output.get('retrieved_chunks', []))} (Max sim: {rag_output.get('max_similarity', 0.0):.4f}).",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "rag_result": rag_output,
        "citations": rag_output.get("citations", []),
        "final_response": rag_output.get("answer", ""),
        "origin": rag_output.get("origin", "LOCAL"),
        "source_type": rag_output.get("source_type", "local_rag"),
        "tiers": rag_output.get("tiers", []),
        "verified_quotes": rag_output.get("verified_quotes", []),
        "urls": rag_output.get("urls", []),
        "decision_path": decision_path,
        "trace": current_trace,
    }


def action_node(state: AgentState) -> Dict[str, Any]:
    """Selects and invokes MCP tools dynamically."""
    action_agent = get_action_agent()
    user_msg = state["user_message"]
    user_prefs = state.get("user_preferences", {})

    start_time = time.time()
    action_output = action_agent.run(user_msg, user_prefs)
    elapsed = round(time.time() - start_time, 2)

    executed_tools = [a.get("tool_name") for a in action_output.get("actions", [])]

    trace_entry = {
        "node": "action_node",
        "agent": "MCP Action Agent",
        "timestamp": datetime.datetime.now().isoformat(),
        "latency_sec": elapsed,
        "tools_executed": executed_tools,
        "details": f"Invoked MCP tools: {executed_tools}",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "action_receipts": action_output.get("actions", []),
        "final_response": action_output.get("summary", ""),
        "origin": "ACTION",
        "source_type": "mcp_action",
        "trace": current_trace,
    }


def handle_profile_query(state: AgentState) -> Dict[str, Any]:
    """Generates an authoritative response regarding the student's profile and authorized email accounts."""
    user_prefs = state.get("user_preferences") or ConversationMemory.get_all_preferences()
    user_name = user_prefs.get("name") or getattr(settings, "USER_NAME", "Alex")
    configured_email = user_prefs.get("email") or getattr(settings, "USER_DEFAULT_EMAIL", "alex.student@ktu.edu.in")

    # Inspect authenticated Gmail account
    authenticated_gmail = None
    try:
        from mcp_servers.google_services_server import _get_google_service
        service, _ = _get_google_service("gmail", "v1")
        if service:
            prof = service.users().getProfile(userId="me").execute()
            if isinstance(prof, dict):
                authenticated_gmail = prof.get("emailAddress")
    except Exception:
        pass

    if not authenticated_gmail:
        g_user = getattr(settings, "GMAIL_USER", "").strip()
        if g_user and not g_user.startswith("your_"):
            authenticated_gmail = g_user

    response_lines = [
        "Here are your configured account and profile email details:",
        f"• **Configured University Email**: `{configured_email}` (saved in your student profile)",
    ]
    if authenticated_gmail:
        response_lines.append(f"• **Authenticated Gmail Sender Account**: `{authenticated_gmail}` (authorized via Google Workspace OAuth for sending/receiving emails and calendar events)")
    else:
        response_lines.append("• **Authenticated Gmail Sender Account**: *Not authenticated / unconfigured*")

    lead_hours = user_prefs.get("default_reminder_lead_hours", "24")
    response_lines.append(f"• **Student Name**: `{user_name}`")
    response_lines.append(f"• **Default Reminder Lead Time**: `{lead_hours} hours`")

    final_resp = "\n".join(response_lines)
    trace_entry = {
        "node": "profile_handler",
        "agent": "Identity Component",
        "timestamp": datetime.datetime.now().isoformat(),
        "details": f"Provided profile details for student {user_name}.",
    }
    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)
    return {
        "final_response": final_resp,
        "origin": "PROFILE",
        "source_type": "profile_identity",
        "trace": current_trace,
    }


def handle_action_followup_query(state: AgentState) -> Dict[str, Any]:
    """Inspects recent action logs in SQLite to truthfully explain past actions."""
    session_id = state.get("session_id", "default_user")
    user_msg = state.get("user_message", "").strip().lower()

    tool_domain = "email" if "email" in user_msg else None
    recent_actions = ConversationMemory.get_latest_actions(session_id=session_id, limit=5, tool_domain=tool_domain)

    if not recent_actions:
        recent_actions = ConversationMemory.get_latest_actions(session_id=session_id, limit=3)
    if not recent_actions and session_id != "default_session":
        recent_actions = ConversationMemory.get_latest_actions(session_id="default_session", limit=5, tool_domain=tool_domain)
    if not recent_actions and session_id != "default_user":
        recent_actions = ConversationMemory.get_latest_actions(session_id="default_user", limit=5, tool_domain=tool_domain)

    if recent_actions:
        latest = recent_actions[0]
        tool_name = latest.get("tool_name", "action")
        args = latest.get("arguments", {})
        receipt = latest.get("receipt", {})
        status = latest.get("status", "unknown")
        created_at = latest.get("created_at", "")

        recipient = args.get("to") or receipt.get("to") or "recipient"
        subject = args.get("subject") or receipt.get("subject") or "No subject"
        msg_id = receipt.get("message_id") or receipt.get("id") or ""
        transport = receipt.get("transport") or receipt.get("provider") or "Gmail API v1"

        if tool_name in ("preview_email",) or receipt.get("requires_confirmation"):
            explanation = (
                f"In your previous request, the assistant invoked **`{tool_name}`** to prepare a draft for `{recipient}` "
                f"with subject *'{subject}'*.\n\n"
                f"Because sending emails is an external action that modifies external state, our system requires explicit student confirmation "
                f"before dispatching. The draft was prepared and presented for your approval."
            )
        elif status == "success":
            id_info = f" with Gmail Provider Message ID **`{msg_id}`**" if msg_id else ""
            explanation = (
                f"In your previous request, the assistant executed **`{tool_name}`** using `{transport}`.\n\n"
                f"• **Recipient**: `{recipient}`\n"
                f"• **Subject**: *'{subject}'*\n"
                f"• **Status**: Accepted by provider{id_info}\n"
                f"• **Timestamp**: `{created_at}`\n\n"
                f"The message was accepted by the Gmail server for dispatch. (Note: Provider acceptance confirms transmission; final inbox delivery depends on the destination mail server)."
            )
        else:
            err_msg = receipt.get("message") or "Unknown error"
            explanation = (
                f"In your previous request, the assistant attempted to execute **`{tool_name}`** for `{recipient}`, "
                f"but encountered an issue:\n\n"
                f"> `{err_msg}`\n\n"
                f"Because of this error, the email was not accepted or sent."
            )
    else:
        explanation = (
            "I checked your active session history, but no previous email actions were recorded in this conversation session. "
            "To send an email, you can specify the recipient, subject, and content (e.g. *'Send an email to user@example.com with subject Notes'*)."
        )

    trace_entry = {
        "node": "action_followup_handler",
        "agent": "Action Inspector",
        "timestamp": datetime.datetime.now().isoformat(),
        "details": "Inspected previous action logs and explained actual tool execution result.",
    }
    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)
    return {
        "final_response": explanation,
        "origin": "ACTION_INSPECTION",
        "source_type": "action_history",
        "trace": current_trace,
    }


def chat_node(state: AgentState) -> Dict[str, Any]:
    """Handles open-ended general dialogue. If an informational question is received, enforces document-first search."""
    user_msg = state["user_message"].strip()

    # 1. Check for Identity / User Profile Questions
    if is_profile_query(user_msg):
        return handle_profile_query(state)

    # 2. Check for Previous Action Follow-Up Inquiries
    if is_action_followup_query(user_msg):
        return handle_action_followup_query(state)

    lower_msg = user_msg.lower()

    # 3. Detect if user message is actually an informational or factual question
    is_question = (
        "?" in user_msg
        or any(lower_msg.startswith(w) for w in ["what", "who", "when", "where", "why", "how", "explain", "describe", "tell me about", "can you explain", "is there", "are there"])
        or any(w in lower_msg for w in ["define", "difference", "compare", "algorithm", "python", "java", "ktu", "exam", "syllabus", "notes"])
    )

    if is_question:
        # Enforce Universal Document-First Search policy on all questions
        return rag_node(state)

    llm = get_llm_client()
    history = state.get("chat_history", [])
    user_prefs = state.get("user_preferences", {})

    user_name = user_prefs.get("name", "User")
    system_prompt = (
        f"You are an intelligent, evidence-grounded personal AI assistant for {user_name}. "
        "You speak naturally, politely, and effectively. "
        "Engage in friendly conversational greetings or pleasantries."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_msg})

    start_time = time.time()
    resp: LLMResponse = llm.generate(messages, temperature=0.7)
    elapsed = round(time.time() - start_time, 2)

    trace_entry = {
        "node": "chat_node",
        "agent": "Conversational Agent",
        "timestamp": datetime.datetime.now().isoformat(),
        "latency_sec": elapsed,
        "details": "Engaged in conversational pleasantry (no factual inquiry).",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "final_response": resp.content.strip(),
        "origin": "CHAT",
        "source_type": "chat",
        "trace": current_trace,
    }


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Breaks composite multi-step requests into an ordered JSON execution plan."""
    planner = get_planner()
    user_msg = state["user_message"]
    user_prefs = state.get("user_preferences", {})

    plan = planner.generate_plan(user_msg, user_prefs)

    trace_entry = {
        "node": "planner_node",
        "agent": "Planner Agent",
        "timestamp": datetime.datetime.now().isoformat(),
        "plan_steps_count": len(plan),
        "plan_summary": [f"Step {s['step']}: {s['action']} - {s['description']}" for s in plan],
        "details": f"Decomposed request into {len(plan)} sequential steps.",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "plan": plan,
        "trace": current_trace,
    }


MAX_PLAN_STEPS = 10


def executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Dynamically executes each step in the Planner's JSON plan sequentially,
    passing intermediate results across steps and verifying action permissions.
    """
    raw_plan = state.get("plan", [])
    user_prefs = state.get("user_preferences", {})
    user_confirmed = state.get("user_confirmed_actions", False)
    mcp_client = get_mcp_client()
    rag_agent = get_rag_agent()
    llm = get_llm_client()

    # Step limit bound
    plan = raw_plan[:MAX_PLAN_STEPS]

    # Deduplicate preview_email if send_email is present
    has_send = any(s.get("action") == "send_email" for s in plan)
    if has_send:
        plan = [s for s in plan if s.get("action") != "preview_email"]

    step_results: Dict[str, Any] = {}
    action_receipts: List[Dict[str, Any]] = []
    citations: List[str] = []
    executed_summaries: List[str] = []

    last_text_context: str = ""
    last_retrieved_chunks_text: str = ""
    last_pdf_path: Optional[str] = None

    for idx, step in enumerate(plan, start=1):
        step_num = step.get("step", idx)
        act = step.get("action", "").strip()
        args = dict(step.get("args", {}))
        desc = step.get("description", act)
        print(f"[CHAINED EXECUTOR] Running Step {step_num}: {act} ({desc})")

        # 1. Internal Action: Knowledge Retrieval via RAG
        if act == "rag_retrieve":
            query = args.get("query") or args.get("search_query") or state.get("user_message", "")
            rag_res = rag_agent.run(query)
            last_text_context = rag_res.get("answer", "")
            step_cites = rag_res.get("citations", [])
            citations.extend(step_cites)

            # Extract full text of all retrieved chunks for downstream synthesis
            retrieved_chunks = rag_res.get("retrieved_chunks", [])
            if retrieved_chunks:
                last_retrieved_chunks_text = "\n\n".join(
                    f"[Source: {c.get('source_file')}, Page {c.get('page')}]\n{c.get('text', '')}"
                    for c in retrieved_chunks
                    if isinstance(c, dict) and c.get("text")
                )
            else:
                last_retrieved_chunks_text = last_text_context

            step_results[f"step_{step_num}"] = {
                "action": act,
                "output": last_text_context,
                "citations": step_cites,
            }
            chunks_found = len(retrieved_chunks)
            executed_summaries.append(
                f"**Step {step_num} (Retrieve Context)**: Retrieved {chunks_found} relevant chunk(s) for query: *\"{query}\"*."
            )

        # 2. Internal Action: Content Summarization / Synthesis
        elif act == "summarize":
            instructions = args.get("instructions", "Synthesize and organize key information into clear markdown with headings and bullet points.")
            content_to_summarize = (
                args.get("content")
                or args.get("text")
                or last_retrieved_chunks_text
                or last_text_context
                or state.get("user_message", "")
            )
            summary_prompt = (
                f"{instructions}\n\n"
                "Context Notes to Summarize:\n"
                f"{content_to_summarize}"
            )
            resp = llm.generate([{"role": "user", "content": summary_prompt}])
            summary_output = resp.content.strip()

            # If LLM invocation failed (e.g. key unauthenticated or quota exceeded), fall back to extractive summary
            if (summary_output.startswith("Error:") or summary_output.startswith("[Quota Error]")) and content_to_summarize and len(content_to_summarize) > 50:
                print("[CHAINED EXECUTOR] LLM call unavailable; synthesizing structured summary from retrieved notes context.")
                clean_lines = [
                    line.strip() for line in content_to_summarize.split("\n")
                    if line.strip() and not line.startswith("---") and not line.startswith("[Source:")
                ]
                bullet_points = [f"- {l}" for l in clean_lines[:15] if len(l) > 15]
                summary_output = (
                    f"# Study & Revision Summary\n\n"
                    f"## Key Topics & Concepts\n"
                    + "\n".join(bullet_points)
                    + f"\n\n*(Grounded directly from retrieved course notes)*"
                )

            lower_summary = summary_output.lower()
            missing_indicators = [
                "didn't include", "did not include", "lacks the notes", "lack the notes",
                "no notes provided", "notes were not provided", "notes are not provided",
                "please paste", "please provide", "couldn't find this in your documents",
                "could not find this in your documents", "unable to summarize without",
                "do not have access to the notes", "haven't provided the notes"
            ]
            is_invalid = (
                not summary_output
                or len(summary_output) < 30
                or any(ind in lower_summary for ind in missing_indicators)
                or summary_output.startswith("Error:")
            )

            if is_invalid:
                error_msg = f"Workflow halted at Step {step_num} (summarize): Unable to generate summary because notes were not found or not provided. Subsequent PDF generation and email steps have been cancelled."
                executed_summaries.append(
                    f"**Step {step_num} (Synthesize Summary - HALTED)**: {error_msg}"
                )
                step_results[f"step_{step_num}"] = {
                    "action": act,
                    "error": error_msg,
                    "output": summary_output,
                }
                current_trace = state.get("trace", [])
                current_trace.append({
                    "node": "executor_node",
                    "agent": "Planner Executor",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "error": error_msg,
                    "details": "Halted because summarize output was invalid or reported missing notes.",
                })
                return {
                    "action_receipts": action_receipts,
                    "final_response": error_msg,
                    "citations": list(dict.fromkeys(citations)),
                    "trace": current_trace,
                }

            last_text_context = summary_output
            step_results[f"step_{step_num}"] = {
                "action": act,
                "output": last_text_context,
            }
            executed_summaries.append(
                f"**Step {step_num} (Synthesize Summary)**: Generated structured summary from retrieved context."
            )

        # 3. Dynamic MCP Tool Execution
        elif mcp_client.has_tool(act):
            if act == "generate_pdf":
                pdf_content = args.get("content") or last_text_context
                if not pdf_content or len(pdf_content.strip()) < 10:
                    error_msg = f"Workflow halted at Step {step_num} (generate_pdf): No validated content or summary available to generate PDF."
                    action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": {"status": "error", "message": error_msg}})
                    executed_summaries.append(f"**Step {step_num} (Compile PDF - HALTED)**: {error_msg}")
                    step_results[f"step_{step_num}"] = {"action": act, "error": error_msg}
                    return {"action_receipts": action_receipts, "final_response": error_msg, "citations": list(dict.fromkeys(citations)), "trace": state.get("trace", [])}

                args["content"] = pdf_content
                if not args.get("title"):
                    args["title"] = "Summary Document"
                if not args.get("filename"):
                    args["filename"] = "Summary_Document.pdf"

                receipt = mcp_client.execute_tool(act, args)
                action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": receipt})
                if receipt.get("status") == "success":
                    last_pdf_path = receipt.get("result", {}).get("file_path")
                    pdf_filename = receipt.get("result", {}).get("filename", "document.pdf")
                    executed_summaries.append(
                        f"**Step {step_num} (Compile PDF)**: Generated PDF **{pdf_filename}** — Download PDF."
                    )
                else:
                    executed_summaries.append(
                        f"**Step {step_num} (Compile PDF)**: Generation failed: {receipt.get('message')}."
                    )
                step_results[f"step_{step_num}"] = receipt

            elif act == "preview_email":
                target_to = args.get("to")
                if not target_to or target_to == "default":
                    target_to = user_prefs.get("email", settings.USER_DEFAULT_EMAIL)
                args["to"] = target_to

                if not args.get("subject"):
                    args["subject"] = "Personal Assistant Document"

                if not args.get("body"):
                    if last_pdf_path:
                        args["body"] = "Hello,\n\nPlease find attached your requested document.\n\nGenerated by your Personal AI Assistant."
                    else:
                        args["body"] = last_text_context or "Hello,\n\nHere is your requested information.\n\nGenerated by your Personal AI Assistant."

                if not args.get("attachment_path") and last_pdf_path:
                    args["attachment_path"] = last_pdf_path

                receipt = mcp_client.execute_tool("preview_email", args)
                action_receipts.append({"step": step_num, "tool_name": "preview_email", "description": desc, "receipt": receipt})
                executed_summaries.append(
                    f"**Step {step_num} (Email Draft - Confirmation Required)**: Prepared draft to `{target_to}` (Subject: *\"{args['subject']}\"*). "
                    "Action halted safely until explicit user confirmation is received."
                )
                step_results[f"step_{step_num}"] = receipt

            elif act == "send_email":
                target_to = args.get("to")
                if not target_to or target_to == "default":
                    target_to = user_prefs.get("email", settings.USER_DEFAULT_EMAIL)
                args["to"] = target_to

                if not args.get("subject"):
                    args["subject"] = "Personal Assistant Document"

                if not args.get("body"):
                    if last_pdf_path:
                        args["body"] = "Hello,\n\nPlease find attached your requested document.\n\nGenerated by your Personal AI Assistant."
                    else:
                        args["body"] = last_text_context or "Hello,\n\nHere is your requested information.\n\nGenerated by your Personal AI Assistant."

                if not args.get("attachment_path") and last_pdf_path:
                    args["attachment_path"] = last_pdf_path

                # Human-in-the-Loop Confirmation Safety Gate
                is_explicitly_confirmed = bool(args.get("confirmed") or user_confirmed)
                if not is_explicitly_confirmed:
                    preview_res = mcp_client.execute_tool(
                        "preview_email",
                        {
                            "to": target_to,
                            "subject": args["subject"],
                            "body": args["body"],
                            "attachment_path": args.get("attachment_path"),
                        },
                    )
                    action_receipts.append({
                        "step": step_num,
                        "tool_name": "preview_email",
                        "description": "Email draft prepared (awaiting confirmation)",
                        "receipt": preview_res,
                    })
                    executed_summaries.append(
                        f"**Step {step_num} (Email Draft - Confirmation Required)**: Prepared draft to `{target_to}` (Subject: *\"{args['subject']}\"*). "
                        "Action halted safely until explicit user confirmation is received."
                    )
                    step_results[f"step_{step_num}"] = preview_res
                else:
                    args["confirmed"] = True
                    receipt = mcp_client.execute_tool("send_email", args)
                    action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": receipt})
                    if receipt.get("status") == "success":
                        executed_summaries.append(
                            f"**Step {step_num} (Send Email)**: Sent email to `{target_to}`."
                        )
                    else:
                        executed_summaries.append(
                            f"**Step {step_num} (Send Email)**: Dispatch error: {receipt.get('message')}."
                        )
                    step_results[f"step_{step_num}"] = receipt

            elif act == "create_reminder":
                if not args.get("title"):
                    args["title"] = "Follow up reminder"

                # Check if reminder specifies 'day before the exam'
                desc_lower = (desc + " " + state.get("user_message", "")).lower()
                is_exam_reminder = ("exam" in desc_lower and ("day before" in desc_lower or "before" in desc_lower))
                if is_exam_reminder:
                    context_search = (last_retrieved_chunks_text + " " + last_text_context)
                    date_match = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", context_search, re.IGNORECASE)
                    if date_match:
                        day = int(date_match.group(1))
                        month_str = date_match.group(2)
                        year = int(date_match.group(3))
                        exam_dt = datetime.datetime.strptime(f"{day} {month_str} {year}", "%d %B %Y")
                        day_before = exam_dt - datetime.timedelta(days=1)
                        args["due_datetime"] = day_before.strftime("%Y-%m-%d 18:00:00")
                        print(f"[EXECUTOR] Grounded reminder to day before exam: {args['due_datetime']}")
                    else:
                        error_msg = "Reminder not scheduled: could not verify the exam date from your documents. Please specify the exam date or upload your exam timetable."
                        action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": {"status": "error", "message": error_msg}})
                        executed_summaries.append(f"**Step {step_num} (Set Reminder - HALTED)**: {error_msg}")
                        step_results[f"step_{step_num}"] = {"action": act, "error": error_msg}
                        return {"action_receipts": action_receipts, "final_response": error_msg, "citations": list(dict.fromkeys(citations)), "trace": state.get("trace", [])}
                elif not args.get("due_datetime") and "tomorrow" in desc_lower:
                    now = datetime.datetime.now()
                    tomorrow = now + datetime.timedelta(days=1)
                    hour = 18 if ("6" in desc_lower or "pm" in desc_lower) else 9
                    args["due_datetime"] = tomorrow.strftime(f"%Y-%m-%d {hour:02d}:00:00")

                if not args.get("due_datetime"):
                    error_msg = "Reminder not scheduled: please specify a due date and time, or provide the exam date for an exam reminder."
                    action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": {"status": "error", "message": error_msg}})
                    executed_summaries.append(f"**Step {step_num} (Set Reminder - HALTED)**: {error_msg}")
                    step_results[f"step_{step_num}"] = {"action": act, "error": error_msg}
                    return {"action_receipts": action_receipts, "final_response": error_msg, "citations": list(dict.fromkeys(citations)), "trace": state.get("trace", [])}
                if not args.get("note"):
                    args["note"] = desc or "Automated reminder."

                receipt = mcp_client.execute_tool(act, args)
                action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": receipt})
                if receipt.get("status") == "success":
                    executed_summaries.append(
                        f"**Step {step_num} (Set Reminder)**: Scheduled reminder '{args['title']}' for {args['due_datetime']}."
                    )
                else:
                    executed_summaries.append(
                        f"**Step {step_num} (Set Reminder)**: Failed to schedule reminder: {receipt.get('message')}."
                    )
                step_results[f"step_{step_num}"] = receipt

            elif act == "create_event":
                if not args.get("title"):
                    args["title"] = "Scheduled Event"
                if not args.get("start"):
                    args["start"] = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d 10:00:00")
                if not args.get("end"):
                    args["end"] = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d 11:00:00")
                if not args.get("description"):
                    args["description"] = desc or ""

                receipt = mcp_client.execute_tool(act, args)
                action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": receipt})
                if receipt.get("status") == "success":
                    executed_summaries.append(
                        f"**Step {step_num} (Calendar Event)**: Created appointment '{args['title']}' ({args['start']} - {args['end']})."
                    )
                else:
                    executed_summaries.append(
                        f"**Step {step_num} (Calendar Event)**: Failed to create event: {receipt.get('message')}."
                    )
                step_results[f"step_{step_num}"] = receipt

            else:
                receipt = mcp_client.execute_tool(act, args)
                action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": receipt})
                status_label = "Success" if receipt.get("status") == "success" else "Error"
                executed_summaries.append(
                    f"**Step {step_num} ({act})**: {status_label} - {receipt.get('message') or 'Executed successfully.'}"
                )
                step_results[f"step_{step_num}"] = receipt

        else:
            receipt = {
                "status": "error",
                "message": f"Action '{act}' is not a recognized internal action or registered MCP tool.",
            }
            action_receipts.append({"step": step_num, "tool_name": act, "description": desc, "receipt": receipt})
            executed_summaries.append(
                f"**Step {step_num} ({act})**: Skipped - unknown tool."
            )
            step_results[f"step_{step_num}"] = receipt

    # Assemble dynamic, truthful final response
    response_blocks = [
        "I have processed your multi-step request with the following steps:",
    ]
    for s_summary in executed_summaries:
        response_blocks.append(f"- {s_summary}")

    if len(raw_plan) > MAX_PLAN_STEPS:
        response_blocks.append(f"\n*(Note: Plan was truncated to the maximum allowed limit of {MAX_PLAN_STEPS} steps)*")

    if last_text_context and ("generate_pdf" not in [s.get("action") for s in plan] or not last_pdf_path):
        response_blocks.append("")
        response_blocks.append("### Content / Summary")
        response_blocks.append(last_text_context)

    final_msg = "\n".join(response_blocks)

    trace_entry = {
        "node": "executor_node",
        "agent": "Chained Workflow Executor",
        "timestamp": datetime.datetime.now().isoformat(),
        "steps_executed": len(plan),
        "total_planned_steps": len(raw_plan),
        "details": f"Dynamically executed {len(plan)} chained step(s).",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "action_receipts": action_receipts,
        "citations": citations,
        "final_response": final_msg,
        "origin": "CHAINED",
        "source_type": "chained_workflow",
        "trace": current_trace,
    }


def responder_node(state: AgentState) -> Dict[str, Any]:
    """Composes the final response, saves to SQLite memory, and formats citations."""
    session_id = state.get("session_id", "default_user")
    user_msg = state.get("user_message", "")
    response_text = state.get("final_response", "")
    citations = state.get("citations", [])

    # Format sources if citations exist
    rendered_output = response_text
    if citations:
        unique_cites = sorted(list(set(citations)))
        cites_block = "\n\n**Sources:**\n" + "\n".join([f"- {c}" for c in unique_cites])
        if "**Sources:**" not in rendered_output:
            rendered_output += cites_block

    # Save to SQLite multi-turn memory
    ConversationMemory.add_turn(session_id, "user", user_msg)
    ConversationMemory.add_turn(session_id, "assistant", rendered_output)

    trace_entry = {
        "node": "responder_node",
        "agent": "Final Responder",
        "timestamp": datetime.datetime.now().isoformat(),
        "citations_rendered": citations,
        "details": "Composed final response and persisted conversation turn to SQLite memory.",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "final_response": rendered_output,
        "trace": current_trace,
    }


# --- Build LangGraph StateMachine ---

def create_orchestrator_graph():
    """Builds and compiles the LangGraph StateGraph."""
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("router_node", router_node)
    workflow.add_node("rag_node", rag_node)
    workflow.add_node("action_node", action_node)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("executor_node", executor_node)
    workflow.add_node("responder_node", responder_node)

    # Set Entry Point
    workflow.set_entry_point("load_context")

    # Connect Context to Router
    workflow.add_edge("load_context", "router_node")

    # Conditional Routing Edges
    workflow.add_conditional_edges(
        "router_node",
        route_decision,
        {
            "rag_node": "rag_node",
            "action_node": "action_node",
            "planner_node": "planner_node",
            "chat_node": "chat_node",
        },
    )

    # Connect execution branches to responder
    workflow.add_edge("rag_node", "responder_node")
    workflow.add_edge("action_node", "responder_node")
    workflow.add_edge("chat_node", "responder_node")
    workflow.add_edge("planner_node", "executor_node")
    workflow.add_edge("executor_node", "responder_node")

    # Responder goes to END
    workflow.add_edge("responder_node", END)

    return workflow.compile()


# Singleton compiled graph
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = create_orchestrator_graph()
    return _compiled_graph


def run_assistant(
    user_message: str,
    session_id: str = "default_user",
    user_confirmed_actions: bool = False,
) -> AgentState:
    """
    Main entry point for running a user message through the LangGraph architecture.
    """
    graph = get_graph()

    initial_state: AgentState = {
        "session_id": session_id,
        "user_message": user_message,
        "chat_history": [],
        "user_preferences": {},
        "route": "",
        "route_reasoning": "",
        "plan": [],
        "rag_result": {},
        "action_receipts": [],
        "final_response": "",
        "citations": [],
        "trace": [],
        "user_confirmed_actions": user_confirmed_actions,
        "origin": "",
        "source_type": "",
        "urls": [],
        "tiers": [],
        "verified_quotes": [],
    }

    final_state = graph.invoke(initial_state)
    return final_state


if __name__ == "__main__":
    print("Testing LangGraph Multi-Agent Assistant...")
    result = run_assistant("When is my CS402 internal exam?")
    print("\n--- FINAL ANSWER ---")
    print(result["final_response"])
    print("\n--- TRACE SUMMARY ---")
    for t in result["trace"]:
        print(f"[{t['node']}] {t['agent']}: {t['details']}")
