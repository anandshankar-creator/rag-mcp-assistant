"""
==============================================================================
Test Suite: Phase 6 Verification (Evaluation Module & Metrics)
==============================================================================
Validates:
1. Benchmark Testset integrity (40 QA items + 10 MCP action tasks).
2. Evaluator runner and metrics compilation.
3. Publication-quality figure generation (Matplotlib charts).
4. Academic evaluation report generation (EVALUATION_REPORT.md).
5. Streamlit Evaluation Page dashboard integration.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
TESTSET_PATH = PROJECT_ROOT / "evaluation" / "testset.json"


def test_testset_integrity():
    """Verify testset.json contains balanced academic evaluation cases."""
    assert TESTSET_PATH.exists(), "testset.json must exist in evaluation/"
    with open(TESTSET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    qa_cases = data.get("qa_cases", [])
    action_cases = data.get("action_cases", [])

    assert len(qa_cases) >= 40, f"Expected at least 40 QA cases, got {len(qa_cases)}"
    assert len(action_cases) >= 10, f"Expected at least 10 action cases, got {len(action_cases)}"

    # Check that in-domain and out-of-domain are represented
    in_domain = [q for q in qa_cases if not q.get("should_refuse")]
    out_of_domain = [q for q in qa_cases if q.get("should_refuse")]

    assert len(in_domain) >= 30, f"Expected >= 30 in-domain cases, got {len(in_domain)}"
    assert len(out_of_domain) >= 10, f"Expected >= 10 out-of-domain cases, got {len(out_of_domain)}"

    # Check key fields in each case
    for q in qa_cases:
        assert "id" in q and "query" in q and "domain" in q
        assert "key_facts" in q or q.get("should_refuse")


def test_benchmark_results_exist():
    """Verify evaluation runner generated summary metrics and detailed records."""
    summary_path = RESULTS_DIR / "summary_metrics.json"
    results_path = RESULTS_DIR / "eval_results.json"
    qa_csv_path = RESULTS_DIR / "eval_qa_results.csv"

    assert summary_path.exists(), "summary_metrics.json must be generated"
    assert results_path.exists(), "eval_results.json must be generated"
    assert qa_csv_path.exists(), "eval_qa_results.csv must be generated"

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    assert "rag_overall_accuracy" in summary
    assert "baseline_overall_accuracy" in summary
    assert "rag_hallucination_rate" in summary
    assert "baseline_hallucination_rate" in summary
    assert "action_tool_accuracy" in summary

    # Verify RAG performs at least as well as or outperforms Baseline on accuracy and hallucination suppression
    assert summary["rag_overall_accuracy"] >= summary["baseline_overall_accuracy"]
    assert summary["rag_hallucination_rate"] <= summary["baseline_hallucination_rate"]


def test_academic_figures_generated():
    """Verify that all three Matplotlib charts are generated as valid PNGs."""
    c1 = RESULTS_DIR / "accuracy_comparison.png"
    c2 = RESULTS_DIR / "hallucination_rate.png"
    c3 = RESULTS_DIR / "latency_comparison.png"

    assert c1.exists() and c1.stat().st_size > 1000, "accuracy_comparison.png must exist and be valid"
    assert c2.exists() and c2.stat().st_size > 1000, "hallucination_rate.png must exist and be valid"
    assert c3.exists() and c3.stat().st_size > 1000, "latency_comparison.png must exist and be valid"


def test_academic_report_generated():
    """Verify that Chapter 5 thesis markdown report is written and formatted."""
    report_path = RESULTS_DIR / "EVALUATION_REPORT.md"
    assert report_path.exists(), "EVALUATION_REPORT.md must exist"

    content = report_path.read_text(encoding="utf-8")
    assert "Chapter 5: Experimental Evaluation" in content
    assert "Overall QA Accuracy" in content
    assert "Hallucination Rate" in content
    assert "Anti-Hallucination Gate" in content or "Refusal Gating" in content


def test_streamlit_evaluation_page_syntax():
    """Verify ui/pages/1_Evaluation.py exists and parses cleanly."""
    page_path = PROJECT_ROOT / "ui" / "pages" / "1_Evaluation.py"
    assert page_path.exists(), "ui/pages/1_Evaluation.py must exist"

    # Compile syntax check
    with open(page_path, "r", encoding="utf-8") as f:
        code = f.read()
    compile(code, str(page_path), "exec")


if __name__ == "__main__":
    pytest.main(["-v", str(Path(__file__))])
