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
            {"step": i, "action": "create_reminder", "description": f"Step {i}", "args": {"title": f"T{i}", "due_datetime": "2099-01-01 18:00:00"}}
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


def test_executor_real_pipeline_os_notes_to_pdf(tmp_path):
    """
    Verify real pipeline (no synthetic rag_result) retrieves OS Unit 3 notes,
    summarizes them, compiles a PDF, and verifies PDF text contains OS notes content.
    Also verifies preview_email deduplication and PDF attachment.
    """
    import os
    import pypdf
    from rag.retriever import get_retriever
    from mcp_servers.pdf_server import generate_pdf

    # Verify retriever can find OS notes
    retriever = get_retriever()
    retrieval = retriever.retrieve("OS Unit 3 Virtual Memory Demand Paging Belady")
    assert len(retrieval.chunks) > 0, "Expected to retrieve at least one chunk for OS Unit 3"

    pdf_filename = f"test_os_unit3_{os.getpid()}.pdf"

    state: AgentState = {
        "session_id": "test_real_pipeline",
        "user_message": "Summarize my OS Unit 3 notes, make a PDF, and email it to me",
        "plan": [
            {"step": 1, "action": "rag_retrieve", "description": "Retrieve OS Unit 3 notes", "args": {"query": "OS Unit 3 Virtual Memory Demand Paging"}},
            {"step": 2, "action": "summarize", "description": "Summarize notes", "args": {"instructions": "Summarize key virtual memory concepts."}},
            {"step": 3, "action": "generate_pdf", "description": "Compile summary into PDF", "args": {"title": "OS Unit 3 Summary", "filename": pdf_filename}},
            {"step": 4, "action": "preview_email", "description": "Preview email", "args": {"to": "team.rag.mcp@gmail.com", "subject": "OS Notes"}},
            {"step": 5, "action": "send_email", "description": "Send email with PDF", "args": {"to": "team.rag.mcp@gmail.com", "subject": "OS Notes"}},
        ],
        "user_preferences": {"email": "team.rag.mcp@gmail.com"},
        "user_confirmed_actions": False,
    }

    result = executor_node(state)

    # 1. Ensure summary succeeded without error
    assert "Workflow halted" not in result["final_response"]

    # 2. Verify PDF was created and contains OS Unit 3 content
    from app.config import settings
    pdf_path = settings.OUTPUTS_DIR / pdf_filename
    assert pdf_path.exists(), f"Expected PDF file to exist at {pdf_path}"

    reader = pypdf.PdfReader(str(pdf_path))
    extracted_text = " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    
    # Assert PDF contains actual OS Unit 3 concepts
    assert any(term in extracted_text.lower() for term in ["virtual memory", "demand paging", "page fault", "belady", "fifo", "frame"]), \
        f"PDF text did not contain expected OS Unit 3 concepts. Text: {extracted_text[:300]}"

    # 3. Verify duplicate preview_email step was removed (single preview only)
    preview_receipts = [
        r for r in result["action_receipts"]
        if r.get("tool_name") == "preview_email"
    ]
    assert len(preview_receipts) == 1, f"Expected exactly 1 preview_email receipt, got {len(preview_receipts)}"

    # 4. Verify PDF is attached to the single preview
    preview_receipt_data = preview_receipts[0]["receipt"]
    assert preview_receipt_data.get("result", {}).get("has_attachment") is True
    assert preview_receipt_data.get("result", {}).get("attachment_name") == pdf_filename

    # Cleanup test PDF
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except Exception:
            pass


def test_executor_summarize_lacks_notes_halts_workflow():
    """Verify workflow stops with error when summary reports missing notes."""
    mock_rag_result = {
        "answer": "I couldn't find this in your documents.",
        "citations": [],
        "retrieved_chunks": [],
        "refused": True,
    }

    mock_llm_response = MagicMock()
    mock_llm_response.content = "It looks like you didn't include or attach the notes for Unit 3! Please paste the text."

    with patch("agents.graph.get_rag_agent") as mock_get_rag, \
         patch("agents.graph.get_llm_client") as mock_get_llm, \
         patch("agents.graph.get_mcp_client") as mock_get_mcp:

        mock_rag = MagicMock()
        mock_rag.run.return_value = mock_rag_result
        mock_get_rag.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm

        mock_mcp = MagicMock()
        mock_get_mcp.return_value = mock_mcp

        state: AgentState = {
            "session_id": "test_halt",
            "user_message": "Summarize my missing notes and email me",
            "plan": [
                {"step": 1, "action": "rag_retrieve", "description": "Retrieve notes", "args": {"query": "missing notes"}},
                {"step": 2, "action": "summarize", "description": "Summarize notes", "args": {}},
                {"step": 3, "action": "generate_pdf", "description": "Make PDF", "args": {"title": "Summary", "filename": "summary.pdf"}},
                {"step": 4, "action": "send_email", "description": "Send email", "args": {"to": "test@example.com"}},
            ],
            "user_preferences": {},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        # Must halt at step 2 with clear error
        assert "Workflow halted at Step 2 (summarize)" in result["final_response"]
        # Must NOT have executed PDF generation or email tools
        mock_mcp.execute_tool.assert_not_called()


def test_planner_validation_malformed_plan():
    """Verify validate_plan_steps filters out malformed, invalid, and unknown steps."""
    from agents.planner import validate_plan_steps

    malformed_raw = [
        "not a dict",
        {"action": "hack_system", "args": {}},  # Unknown action
        {"action": "generate_pdf", "args": {"title": "Doc"}},  # Valid
        {"step": 99, "action": "send_email", "args": {"to": "a@b.com"}},  # Valid, out of order step
        {"no_action_field": True},  # Missing action
        {"action": "create_reminder", "args": "invalid_args_type"},  # Args not dict
    ]

    validated = validate_plan_steps(malformed_raw, max_steps=5)
    assert len(validated) == 3
    # Step 1: generate_pdf
    assert validated[0]["step"] == 1
    assert validated[0]["action"] == "generate_pdf"
    # Step 2: send_email (renumbered sequentially)
    assert validated[1]["step"] == 2
    assert validated[1]["action"] == "send_email"
    # Step 3: create_reminder (args reset to dict)
    assert validated[2]["step"] == 3
    assert validated[2]["action"] == "create_reminder"
    assert isinstance(validated[2]["args"], dict)


def test_executor_unverified_exam_date_halts_reminder():
    """Verify workflow halts when an exam reminder cannot verify the exam date from context."""
    with patch("agents.graph.get_mcp_client") as mock_get_mcp:
        mock_mcp = MagicMock()
        mock_get_mcp.return_value = mock_mcp

        state: AgentState = {
            "session_id": "test_unverified_exam",
            "user_message": "Remind me the day before the exam",
            "plan": [
                {
                    "step": 1,
                    "action": "create_reminder",
                    "description": "Remind me the day before the exam",
                    "args": {"title": "Exam Prep"},  # No verified date and no date in context
                }
            ],
            "user_preferences": {},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        # Reminder must halt and NOT call MCP
        mock_mcp.execute_tool.assert_not_called()
        assert "Reminder not scheduled: could not verify the exam date" in result["final_response"]
        assert len(result["action_receipts"]) == 1
        assert result["action_receipts"][0]["receipt"]["status"] == "error"


def test_executor_empty_content_halts_generate_pdf():
    """Verify generate_pdf halts instead of inventing placeholder text when content is absent."""
    with patch("agents.graph.get_mcp_client") as mock_get_mcp:
        mock_mcp = MagicMock()
        mock_get_mcp.return_value = mock_mcp

        state: AgentState = {
            "session_id": "test_empty_pdf",
            "user_message": "Make a PDF",
            "plan": [
                {"step": 1, "action": "generate_pdf", "description": "Make PDF", "args": {}},
            ],
            "user_preferences": {},
            "user_confirmed_actions": False,
        }

        result = executor_node(state)

        # Must halt safely without calling PDF generator
        mock_mcp.execute_tool.assert_not_called()
        assert "Workflow halted at Step 1 (generate_pdf)" in result["final_response"]
        assert len(result["action_receipts"]) == 1
        assert result["action_receipts"][0]["receipt"]["status"] == "error"


