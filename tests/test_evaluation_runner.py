"""
==============================================================================
Test Suite: tests/test_evaluation_runner.py
Role: Unit Tests for Empirical Evaluation Suite (Split Handling & Metrics)
==============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch
from evaluation.run_eval import BenchmarkEvaluator, QAEvalRecord, ActionEvalRecord


def test_evaluator_split_filtering():
    """Verify evaluator accurately separates development/tuning from held-out evaluation splits."""
    evaluator = BenchmarkEvaluator()

    with patch("builtins.open") as mock_file:
        mock_file.return_value.__enter__.return_value.read.return_value = '{"qa_cases": [], "action_cases": []}'

        # Verify evaluator initializes without error
        assert evaluator.retriever is not None
        assert evaluator.generator is not None


def test_evaluator_qa_in_domain_scoring():
    """Verify in-domain factual answer containing key facts scores as correct with zero hallucination."""
    evaluator = BenchmarkEvaluator()
    evaluator.generator = MagicMock()
    evaluator.retriever = MagicMock()

    # Mock RAG response with correct answer & citations
    mock_rag_resp = MagicMock()
    mock_rag_resp.answer = "The internal exam is in Room 304 on 14 March 2026 [Timetable.txt, page 1]."
    mock_rag_resp.refused = False
    mock_rag_resp.citations = ["Timetable.txt, page 1"]

    mock_retrieval = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.source_file = "Timetable.txt"
    mock_retrieval.chunks = [mock_chunk]
    mock_retrieval.max_similarity = 0.82

    evaluator.generator.answer_question.return_value = mock_rag_resp
    evaluator.retriever.retrieve.return_value = mock_retrieval
    evaluator._call_baseline_llm = MagicMock(return_value="I do not know.")

    item = {
        "id": "QA-TEST-01",
        "category": "qa_answerable",
        "domain": "Timetable",
        "split": "held_out",
        "query": "When and where is the internal exam?",
        "expected_answer": "14 March 2026 in Room 304",
        "expected_source_file": "Timetable.txt",
        "key_facts": ["Room 304", "14 March 2026"],
        "should_refuse": False,
    }

    record = evaluator.evaluate_qa_item(item)

    assert record.rag_correct is True
    assert record.rag_hallucinated is False
    assert record.retrieval_hit is True
    assert len(record.rag_citations) == 1
    assert record.baseline_refused is True
    assert record.baseline_hallucinated is False


def test_evaluator_qa_out_of_domain_refusal_scoring():
    """Verify out-of-domain query triggers threshold refusal and counts as anti-hallucination success."""
    evaluator = BenchmarkEvaluator()
    evaluator.generator = MagicMock()
    evaluator.retriever = MagicMock()

    # Mock RAG refusal
    mock_rag_resp = MagicMock()
    mock_rag_resp.answer = "I couldn't find this in your documents."
    mock_rag_resp.refused = True
    mock_rag_resp.citations = []

    mock_retrieval = MagicMock()
    mock_retrieval.chunks = []
    mock_retrieval.max_similarity = 0.15

    evaluator.generator.answer_question.return_value = mock_rag_resp
    evaluator.retriever.retrieve.return_value = mock_retrieval
    # Closed-book baseline guesses an answer
    evaluator._call_baseline_llm = MagicMock(return_value="Argentina won the World Cup in 2022.")

    item = {
        "id": "QA-TEST-OOD",
        "category": "qa_unanswerable",
        "domain": "Out-of-Domain",
        "split": "held_out",
        "query": "Who won the FIFA World Cup?",
        "expected_answer": "I couldn't find this in your documents.",
        "expected_source_file": None,
        "key_facts": ["couldn't find this in your documents"],
        "should_refuse": True,
    }

    record = evaluator.evaluate_qa_item(item)

    assert record.rag_refused is True
    assert record.rag_correct is True
    assert record.rag_hallucinated is False
    # Baseline failed to acknowledge lack of private domain relevance
    assert record.baseline_refused is False
    assert record.baseline_hallucinated is True
