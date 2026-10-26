"""
==============================================================================
Test Suite: tests/test_planner_executor.py
Role: Unit Tests for Dynamic Multi-Step Planner and LangGraph Executor Node
==============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch
from agents.planner import PlannerAgent
from agents.graph import executor_node, AgentState, MAX_PLAN_STEPS


def test_planner_fallback_generation():
    """Verify planner fallback decomposes requests into ordered steps with schema keys."""
    # Using mock LLM that triggers fallback path
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("Simulated LLM network failure")

    planner = PlannerAgent(llm_client=mock_llm)
    plan = planner.generate_plan("Summarize my notes, make a PDF, and email it to me")

    assert len(plan) >= 3, f"Expected at least 3 steps, got {len(plan)}"
    for idx, step in enumerate(plan, 1):
        assert step["step"] == idx
        assert "action" in step
        assert "description" in step
        assert "args" in step


def test_executor_dynamic_rag_and_summarize():
    """Verify executor_node dynamically executes rag_retrieve and summarize steps."""
    mock_rag_result = {
        "answer": "Demand paging is a method of virtual memory management.",
        "citations": ["os_unit3.txt:p1"],
        "retrieved_chunks": [{"text": "Demand paging chunk"}],
        "refused": False,
    }

    mock_summary_response = MagicMock()
    mock_summary_response.content = "## Summary\n- Key point: Demand paging."

    with patch("agents.graph.get_rag_agent") as mock_get_rag, \
         patch("agents.graph.get_llm_client") as mock_get_llm:

        mock_rag_agent = MagicMock()
        mock_rag_agent.run.return_value = mock_rag_result
        mock_get_rag.return_value = mock_rag_agent

        mock_llm = MagicMock()
        mock_llm.generate.return_value = mock_summary_response
        mock_get_llm.return_value = mock_llm

        state: AgentState = {
            "session_id": "test_session",
            "user_message": "Summarize my notes",
            "plan": [
                {"step": 1, "action": "rag_retrieve", "description": "Retrieve notes", "args": {"query": "Virtual Memory"}},
                {"step": 2, "action": "summarize", "description": "Summarize notes", "args": {}},
            ],
            "user_preferences": {"name": "TestUser"},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        assert "Demand paging" in result["final_response"]
        assert len(result["citations"]) == 1
        assert result["citations"][0] == "os_unit3.txt:p1"
        assert len(result["trace"]) >= 1


def test_executor_mcp_reminder_and_event():
    """Verify executor_node dynamically invokes registered MCP tools (create_reminder, create_event)."""
    with patch("agents.graph.get_mcp_client") as mock_get_mcp:
        mock_mcp = MagicMock()
        mock_mcp.has_tool.side_effect = lambda tool_name: tool_name in ["create_reminder", "create_event"]
        mock_mcp.execute_tool.side_effect = lambda tool, args: {
            "status": "success",
            "tool_name": tool,
            "result": {"title": args.get("title")},
            "message": f"Successfully executed {tool}",
        }
        mock_get_mcp.return_value = mock_mcp

        state: AgentState = {
            "session_id": "test_mcp",
            "user_message": "Set a reminder and an event",
            "plan": [
                {"step": 1, "action": "create_reminder", "description": "Team sync reminder", "args": {"title": "Team Sync", "due_datetime": "2026-10-30 09:00:00"}},
                {"step": 2, "action": "create_event", "description": "Sprint planning event", "args": {"title": "Sprint Planning", "start": "2026-10-30 10:00:00", "end": "2026-10-30 11:00:00"}},
            ],
            "user_preferences": {},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        assert len(result["action_receipts"]) == 2
        assert result["action_receipts"][0]["tool_name"] == "create_reminder"
        assert result["action_receipts"][1]["tool_name"] == "create_event"
        assert "Team Sync" in result["final_response"]
        assert "Sprint Planning" in result["final_response"]


def test_executor_email_confirmation_safety_gate():
    """Verify unconfirmed email dispatch invokes preview_email draft and halts live sending."""
    with patch("agents.graph.get_mcp_client") as mock_get_mcp:
        mock_mcp = MagicMock()
        mock_mcp.has_tool.return_value = True

        def mock_execute(tool_name, args):
            if tool_name == "preview_email":
                return {
                    "status": "ready_for_confirmation",
                    "action": "preview_email",
                    "to": args.get("to"),
                    "subject": args.get("subject"),
                    "requires_confirmation": True,
                }
            elif tool_name == "send_email":
                return {
                    "status": "error",
                    "message": "Should not be called when unconfirmed",
                }
            return {"status": "success"}

        mock_mcp.execute_tool.side_effect = mock_execute
        mock_get_mcp.return_value = mock_mcp

        state: AgentState = {
            "session_id": "test_safety",
            "user_message": "Email document to me",
            "plan": [
                {"step": 1, "action": "send_email", "description": "Send summary", "args": {"to": "user@example.com", "subject": "Summary", "confirmed": False}},
            ],
            "user_preferences": {"email": "user@example.com"},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        # Confirm that preview_email was called instead of live send_email
        assert len(result["action_receipts"]) == 1
        assert result["action_receipts"][0]["tool_name"] == "preview_email"
        assert "Confirmation Required" in result["final_response"]


def test_executor_plan_step_bounding():
    """Verify plans exceeding MAX_PLAN_STEPS (10) are bounded and do not loop infinitely."""
    with patch("agents.graph.get_mcp_client") as mock_get_mcp:
        mock_mcp = MagicMock()
        mock_mcp.has_tool.return_value = True
        mock_mcp.execute_tool.return_value = {"status": "success", "message": "ok"}
        mock_get_mcp.return_value = mock_mcp

        # Construct 15 steps
        long_plan = [
            {"step": i, "action": "create_reminder", "description": f"Step {i}", "args": {"title": f"T{i}"}}
            for i in range(1, 16)
        ]

        state: AgentState = {
            "session_id": "test_bounds",
            "user_message": "Excessive plan",
            "plan": long_plan,
            "user_preferences": {},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        assert len(result["action_receipts"]) == MAX_PLAN_STEPS
        assert f"truncated to the maximum allowed limit of {MAX_PLAN_STEPS}" in result["final_response"]


def test_executor_unknown_action_handling():
    """Verify executor handles unknown action gracefully with error receipt."""
    with patch("agents.graph.get_mcp_client") as mock_get_mcp:
        mock_mcp = MagicMock()
        mock_mcp.has_tool.return_value = False
        mock_get_mcp.return_value = mock_mcp

        state: AgentState = {
            "session_id": "test_unknown",
            "user_message": "Run non-existent action",
            "plan": [
                {"step": 1, "action": "non_existent_tool_xyz", "description": "Unknown", "args": {}},
            ],
            "user_preferences": {},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        assert len(result["action_receipts"]) == 1
        receipt = result["action_receipts"][0]["receipt"]
        assert receipt["status"] == "error"
        assert "not a recognized" in receipt["message"]
