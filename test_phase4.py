"""
==============================================================================
Script: test_phase4.py
Role: Phase 4 Verification & Multi-Agent Graph Test Harness
==============================================================================
Validates the complete LangGraph State Machine across all 4 pathways:
1. QA Flow: Knowledge retrieval grounded in documents.
2. Action Flow: Single MCP tool command execution.
3. Chained Flow: Multi-step planning, state passing, and action execution.
4. Chat Flow: Open-domain dialogue and general assistant intelligence.
5. Memory & Trace Telemetry: Multi-turn persistence and debug trace logs.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.graph import run_assistant
from agents.memory import ConversationMemory


def test_qa_flow():
    print("\n==================================================================")
    print("1. Testing QA Flow (RAG Grounding in Private Documents)")
    print("==================================================================")
    query = "When is my CS402 internal exam?"
    res = run_assistant(query, session_id="test_qa_session")

    print(f"User Query: {query}")
    print(f"Route Selected: {res['route']} ({res['route_reasoning']})")
    print(f"Final Answer: {res['final_response']}")
    print(f"Citations: {res['citations']}")

    assert res["route"] == "QA", f"Expected QA route, got {res['route']}"
    assert "14 March" in res["final_response"], "Exam date missing from grounded answer."
    assert len(res["citations"]) > 0, "No citations generated for QA route."
    print("QA Flow PASSED.")


def test_action_flow():
    print("\n==================================================================")
    print("2. Testing Action Flow (Dynamic MCP Tool Execution)")
    print("==================================================================")
    query = "Set a reminder tomorrow at 6 PM to revise OS Unit 3"
    res = run_assistant(query, session_id="test_action_session")

    print(f"User Query: {query}")
    print(f"Route Selected: {res['route']} ({res['route_reasoning']})")
    print(f"Final Answer: {res['final_response']}")
    print(f"Action Receipts: {len(res['action_receipts'])}")

    assert res["route"] == "ACTION", f"Expected ACTION route, got {res['route']}"
    assert len(res["action_receipts"]) > 0, "No action receipts recorded."
    assert "Action performed:" in res["final_response"] or "successfully" in res["final_response"]
    print("Action Flow PASSED.")


def test_chained_flow():
    print("\n==================================================================")
    print("3. Testing Chained Flow (Planner Agent & Sequential Execution)")
    print("==================================================================")
    query = "Summarize my OS Unit 3 notes, make a PDF, email it to me, and remind me on the day before the exam"
    res = run_assistant(query, session_id="test_chained_session")

    print(f"User Query: {query}")
    print(f"Route Selected: {res['route']}")
    print(f"Plan Steps ({len(res['plan'])} steps):")
    for s in res["plan"]:
        print(f"  * Step {s.get('step')}: {s.get('action')} - {s.get('description')}")

    print(f"\nFinal Summary:\n{res['final_response']}")
    print(f"Total Action Receipts: {len(res['action_receipts'])}")

    assert res["route"] == "CHAINED", f"Expected CHAINED route, got {res['route']}"
    assert len(res["plan"]) >= 3, f"Expected at least 3 planned steps, got {len(res['plan'])}"
    assert len(res["action_receipts"]) >= 1, "No tool receipts captured during chained run."
    print("Chained Flow PASSED.")


def test_chat_flow():
    print("\n==================================================================")
    print("4. Testing Conversational Chat Flow (Like ChatGPT / Gemini)")
    print("==================================================================")
    query = "Hello! Who won the 2018 FIFA World Cup? Answer briefly."
    res = run_assistant(query, session_id="test_chat_session")

    print(f"User Query: {query}")
    print(f"Route Selected: {res['route']}")
    print(f"Response: {res['final_response']}")

    assert res["route"] == "CHAT", f"Expected CHAT route, got {res['route']}"
    assert len(res["final_response"]) > 5, "Chat response was empty."
    print("Chat Flow PASSED.")


def test_memory_and_trace():
    print("\n==================================================================")
    print("5. Testing SQLite Multi-Turn Memory & Debug Trace Telemetry")
    print("==================================================================")
    # Check memory persistence
    history = ConversationMemory.get_recent_history("test_qa_session", last_n=5)
    print(f"Memory retrieved {len(history)} turns for 'test_qa_session'.")
    assert len(history) >= 2, "Conversation turns were not persisted into SQLite."

    # Run query and inspect trace telemetry
    res = run_assistant("When is the DBMS mini project submission deadline?", session_id="test_trace_session")
    trace = res["trace"]
    print(f"Debug Trace captured {len(trace)} events:")
    for idx, t in enumerate(trace, 1):
        print(f"  [{idx}] Node: {t.get('node')} | Agent: {t.get('agent')} | Info: {t.get('details')}")

    assert len(trace) >= 3, "Trace telemetry incomplete."
    print("Memory & Trace Telemetry PASSED.")


if __name__ == "__main__":
    print("==================================================================")
    print("  RUNNING PHASE 4 VERIFICATION: LANGGRAPH MULTI-AGENT STATE MACHINE")
    print("==================================================================")
    try:
        test_qa_flow()
        test_action_flow()
        test_chained_flow()
        test_chat_flow()
        test_memory_and_trace()
        print("\n==================================================================")
        print("  ALL PHASE 4 CHECKS PASSED SUCCESSFULLY!")
        print("==================================================================")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error during verification: {e}")
        sys.exit(1)
