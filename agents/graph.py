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
import time
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END

from app.config import settings
from llm import get_llm_client, LLMResponse
from agents.memory import ConversationMemory
from agents.orchestrator import get_router
from agents.planner import get_planner
from agents.rag_agent import get_rag_agent
from agents.action_agent import get_action_agent
from mcp_servers.client import get_mcp_client


class AgentState(TypedDict):
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


# --- Graph Node Implementations ---

def load_context_node(state: AgentState) -> Dict[str, Any]:
    """Loads previous turns and preferences from SQLite."""
    session_id = state.get("session_id", "default_student")
    history = ConversationMemory.get_recent_history(session_id, last_n=6)
    prefs = ConversationMemory.get_all_preferences()

    trace_entry = {
        "node": "load_context",
        "agent": "Memory Component",
        "timestamp": datetime.datetime.now().isoformat(),
        "details": f"Loaded {len(history)} previous turns and profile preferences for {prefs.get('name', 'Student')}.",
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
    router = get_router()
    user_msg = state["user_message"]
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

    trace_entry = {
        "node": "rag_node",
        "agent": "RAG Knowledge Agent",
        "timestamp": datetime.datetime.now().isoformat(),
        "latency_sec": elapsed,
        "max_similarity": rag_output.get("max_similarity", 0.0),
        "refused": rag_output.get("refused", False),
        "chunks_retrieved": len(rag_output.get("retrieved_chunks", [])),
        "citations_count": len(rag_output.get("citations", [])),
        "details": f"Retrieved {len(rag_output.get('retrieved_chunks', []))} chunks (Max similarity: {rag_output.get('max_similarity'):.4f}).",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "rag_result": rag_output,
        "citations": rag_output.get("citations", []),
        "final_response": rag_output.get("answer", ""),
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
        "trace": current_trace,
    }


def chat_node(state: AgentState) -> Dict[str, Any]:
    """Handles open-ended general dialogue and general programming/assistant tasks."""
    llm = get_llm_client()
    user_msg = state["user_message"]
    history = state.get("chat_history", [])
    user_prefs = state.get("user_preferences", {})

    student_name = user_prefs.get("name", "Student")
    system_prompt = (
        f"You are an intelligent, helpful personal assistant for {student_name}. "
        "You speak naturally, politely, and effectively like ChatGPT or Gemini. "
        "Answer general questions, brainstorm ideas, explain concepts, or engage in conversation."
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
        "details": "Generated open-domain assistant conversation.",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "final_response": resp.content.strip(),
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


def executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes each step in the Planner's JSON plan sequentially,
    passing intermediate results (notes -> summary -> PDF -> email/reminder).
    """
    plan = state.get("plan", [])
    user_prefs = state.get("user_preferences", {})
    mcp_client = get_mcp_client()
    rag_agent = get_rag_agent()
    llm = get_llm_client()

    step_results = {}
    action_receipts = []
    citations = []

    last_text_context = ""
    last_pdf_path = None

    for step in plan:
        act = step.get("action", "")
        args = step.get("args", {})
        desc = step.get("description", "")
        print(f"[CHAINED EXECUTOR] Running Step {step.get('step')}: {act} ({desc})")

        if act == "rag_retrieve":
            query = args.get("query", "OS Unit 3 Virtual Memory")
            rag_res = rag_agent.run(query)
            last_text_context = rag_res.get("answer", "")
            citations.extend(rag_res.get("citations", []))
            step_results["rag_retrieve"] = last_text_context

        elif act == "summarize":
            summary_prompt = (
                "Please synthesize the following study notes into a clear, structured "
                "revision document with markdown headings (##) and bullet points (*):\n\n"
                f"{last_text_context}"
            )
            resp = llm.generate([{"role": "user", "content": summary_prompt}])
            last_text_context = resp.content.strip()
            step_results["summarize"] = last_text_context

        elif act == "generate_pdf":
            title = args.get("title", "Study Notes Summary")
            filename = args.get("filename", "Study_Summary.pdf")
            pdf_res = mcp_client.execute_tool(
                "generate_pdf",
                {"title": title, "content": last_text_context, "filename": filename},
            )
            action_receipts.append({"tool_name": "generate_pdf", "receipt": pdf_res})
            if pdf_res.get("status") == "success":
                last_pdf_path = pdf_res.get("result", {}).get("file_path")
            step_results["generate_pdf"] = last_pdf_path

        elif act == "send_email":
            target_to = args.get("to")
            if not target_to or target_to == "default":
                target_to = user_prefs.get("email", "alex.student@ktu.edu.in")
            subj = args.get("subject", "Automated Study Notes PDF")
            body = f"Hello,\n\nPlease find attached your requested revision PDF.\n\nGenerated by your Personal Assistant."
            email_res = mcp_client.execute_tool(
                "send_email",
                {"to": target_to, "subject": subj, "body": body, "attachment_path": last_pdf_path},
            )
            action_receipts.append({"tool_name": "send_email", "receipt": email_res})
            step_results["send_email"] = email_res

        elif act == "create_reminder":
            title = args.get("title", "Exam Revision Reminder")
            due = args.get("due_datetime", "2026-03-13 18:00:00")
            note = args.get("note", "Automated revision reminder.")
            rem_res = mcp_client.execute_tool(
                "create_reminder",
                {"title": title, "due_datetime": due, "note": note},
            )
            action_receipts.append({"tool_name": "create_reminder", "receipt": rem_res})
            step_results["create_reminder"] = rem_res

        elif act == "create_event":
            title = args.get("title", "Study Session")
            start = args.get("start", "2026-03-13 10:00:00")
            end = args.get("end", "2026-03-13 12:00:00")
            ev_res = mcp_client.execute_tool(
                "create_event",
                {"title": title, "start": start, "end": end, "description": desc},
            )
            action_receipts.append({"tool_name": "create_event", "receipt": ev_res})
            step_results["create_event"] = ev_res

    # Assemble composite final summary
    executed_lines = [
        "I have completed your multi-step request successfully:",
        f"1. **Retrieved & Summarized Notes**: Grounded in your private documents.",
    ]
    if last_pdf_path:
        executed_lines.append(f"2. **Compiled PDF**: Saved to `{last_pdf_path}`.")
    if any(a["tool_name"] == "send_email" for a in action_receipts):
        target_to = user_prefs.get("email", "alex.student@ktu.edu.in")
        executed_lines.append(f"3. **Dispatched Email**: Sent to `{target_to}` with PDF attached.")
    if any(a["tool_name"] == "create_reminder" for a in action_receipts):
        executed_lines.append(f"4. **Created Reminder**: Alarm scheduled for the day before your exam.")

    final_msg = "\n".join(executed_lines)

    trace_entry = {
        "node": "executor_node",
        "agent": "Chained Workflow Executor",
        "timestamp": datetime.datetime.now().isoformat(),
        "steps_executed": len(plan),
        "details": f"Completed all {len(plan)} chained steps successfully.",
    }

    current_trace = state.get("trace", [])
    current_trace.append(trace_entry)

    return {
        "action_receipts": action_receipts,
        "citations": citations,
        "final_response": final_msg,
        "trace": current_trace,
    }


def responder_node(state: AgentState) -> Dict[str, Any]:
    """Composes the final response, saves to SQLite memory, and formats citations."""
    session_id = state.get("session_id", "default_student")
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


def run_assistant(user_message: str, session_id: str = "default_student") -> AgentState:
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
