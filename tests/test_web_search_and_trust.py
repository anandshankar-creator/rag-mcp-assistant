"""
==============================================================================
Test Suite: tests/test_web_search_and_trust.py
Role: Unit & Integration Tests for Domain Trust Ranking and Web Fallback
==============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch
from rag.trust_ranker import DomainTrustRanker
from rag.web_search import WebSearchEngine
from rag.generator import RAGGenerator, RAGResponse
from rag.retriever import RetrievalResult


def test_trust_ranker_tier_classification():
    """Verify DomainTrustRanker classifies domains into accurate authority tiers."""
    ranker = DomainTrustRanker()

    # Tier 1: Academic & Documentation
    assert ranker.calculate_trust_score("https://docs.python.org/3/library/os.html") >= 0.90
    assert ranker.calculate_trust_score("https://en.wikipedia.org/wiki/Operating_system") >= 0.90
    assert ranker.calculate_trust_score("https://www.stanford.edu/research") == 1.0
    assert ranker.calculate_trust_score("https://ktu.edu.in/syllabus") == 1.0

    # Tier 2: Established technical publications
    assert ranker.calculate_trust_score("https://www.geeksforgeeks.org/virtual-memory-in-operating-system/") >= 0.75
    assert ranker.calculate_trust_score("https://realpython.com/python-gil/") >= 0.75

    # Untrusted / Spam
    assert ranker.calculate_trust_score("https://www.quora.com/What-is-paging") <= 0.20
    assert ranker.calculate_trust_score("https://www.pinterest.com/pin/12345") <= 0.20


def test_trust_ranker_filtering_and_composite_ranking():
    """Verify ranker filters low-credibility links and prioritizes authoritative sources."""
    ranker = DomainTrustRanker()

    sample_results = [
        {"title": "Social Forum Answer", "href": "https://www.quora.com/answer-1", "body": "some forum post"},
        {"title": "Python Docs", "href": "https://docs.python.org/3/tutorial/", "body": "official python tutorial"},
        {"title": "GeeksforGeeks", "href": "https://www.geeksforgeeks.org/python/", "body": "gfg python tutorial"},
    ]

    filtered_ranked = ranker.rank_and_filter_results(sample_results, min_trust=0.40)

    # Quora should be filtered out
    urls = [item["href"] for item in filtered_ranked]
    assert "https://www.quora.com/answer-1" not in urls

    # docs.python.org should be ranked top
    assert filtered_ranked[0]["href"] == "https://docs.python.org/3/tutorial/"
    assert filtered_ranked[0]["trust_score"] >= 0.90


def test_web_search_engine_grounded_synthesis():
    """Verify WebSearchEngine synthesizes grounded answers with URL citations."""
    mock_llm = MagicMock()
    mock_llm.generate.return_value = MagicMock(
        content="The Global Interpreter Lock (GIL) is a mutex in CPython [https://docs.python.org/3/glossary.html#term-global-interpreter-lock]."
    )

    engine = WebSearchEngine(llm_client=mock_llm)

    # Mock search and fetch
    with patch.object(engine, "search") as mock_search, \
         patch.object(engine, "fetch_page_content") as mock_fetch:

        mock_search.return_value = [
            {
                "title": "Python Glossary",
                "href": "https://docs.python.org/3/glossary.html#term-global-interpreter-lock",
                "body": "The Global Interpreter Lock is a mechanism used by CPython...",
                "tier": "Tier 1: Authoritative",
            }
        ]
        mock_fetch.return_value = "The Global Interpreter Lock, or GIL, is a mutex that protects access to Python objects."

        res = engine.research_and_answer("What is Python GIL?")

        assert res["success"] is True
        assert "Global Interpreter Lock" in res["answer"]
        assert len(res["citations"]) == 1
        assert "https://docs.python.org" in res["citations"][0]


def test_rag_generator_local_to_web_fallback():
    """Verify RAGGenerator falls back to web research when local threshold fails and fallback is enabled."""
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = RetrievalResult(
        query="What is the latest James Webb telescope discovery?",
        chunks=[],
        max_similarity=0.12,  # Below 0.30 threshold
        passed_threshold=False,
    )

    mock_web_engine = MagicMock()
    mock_web_engine.research_and_answer.return_value = {
        "success": True,
        "answer": "JWST detected carbon dioxide on an exoplanet [https://www.nasa.gov/news].",
        "citations": ["https://www.nasa.gov/news"],
        "sources": [],
        "source_type": "web",
    }

    generator = RAGGenerator(retriever=mock_retriever, web_search_engine=mock_web_engine)

    # 1. With allow_web_fallback=True
    res_web = generator.answer_question(
        query="What is the latest James Webb telescope discovery?",
        allow_web_fallback=True,
    )
    assert res_web.refused is False
    assert res_web.source_type == "web"
    assert "JWST detected" in res_web.answer
    assert "https://www.nasa.gov/news" in res_web.citations

    # 2. With allow_web_fallback=False (deterministic refusal)
    res_refusal = generator.answer_question(
        query="What is the latest James Webb telescope discovery?",
        allow_web_fallback=False,
    )
    assert res_refusal.refused is True
    assert "couldn't find this in your documents" in res_refusal.answer.lower()
    assert len(res_refusal.citations) == 0
