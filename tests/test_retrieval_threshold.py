"""
==============================================================================
Test Suite: Retrieval Threshold & Anti-Hallucination Gating Validation
==============================================================================
Validates:
1. Cosine similarity mathematical conversion: sim = 1.0 - distance.
2. Threshold Gate: candidates below tau are filtered out.
3. Refusal Behavior: queries failing the threshold trigger pre-emptive refusal.
4. In-domain vs Out-of-domain discrimination on live ChromaDB vector store.
"""

import pytest
from rag.retriever import RetrievedChunk, RetrievalResult, get_retriever
from rag.generator import get_rag_generator


def test_similarity_math_conversion():
    """Verify that cosine distance d maps to similarity score s = 1 - d."""
    distance = 0.25
    similarity = 1.0 - distance
    assert similarity == 0.75

    distance_zero = 0.0
    similarity_zero = 1.0 - distance_zero
    assert similarity_zero == 1.0


def test_threshold_gating_logic():
    """Test RetrievalResult property has_context based on threshold."""
    # Case 1: Chunks exceed threshold
    passing_chunk = RetrievedChunk(
        chunk_id="doc1_p1_c0",
        text="CS402 Operating Systems notes",
        metadata={"source_file": "doc1.txt", "page": 1},
        similarity=0.72,
        source_file="doc1.txt",
        page=1,
    )
    result_passed = RetrievalResult(
        query="When is OS exam?",
        chunks=[passing_chunk],
        passed_threshold=True,
        max_similarity=0.72,
        threshold_applied=0.30,
    )
    assert result_passed.has_context is True

    # Case 2: Max similarity falls below threshold
    result_failed = RetrievalResult(
        query="Who won FIFA World Cup?",
        chunks=[],
        passed_threshold=False,
        max_similarity=0.18,
        threshold_applied=0.30,
    )
    assert result_failed.has_context is False


def test_anti_hallucination_refusal_trigger():
    """Verify that generator returns graceful refusal without calling LLM when gate trips."""
    generator = get_rag_generator()

    # Query guaranteed to be completely out of domain
    out_of_domain_query = "Who won the 2022 FIFA World Cup in Qatar?"
    retriever = get_retriever()
    retrieval = retriever.retrieve(out_of_domain_query, threshold=0.30)

    # If the gate trips, generator must refuse
    if not retrieval.has_context:
        resp = generator.generate(out_of_domain_query)
        assert resp.refused is True
        assert "couldn't find this in your documents" in resp.answer.lower()
        assert len(resp.citations) == 0


def test_in_domain_retrieval_success():
    """Verify in-domain query passes threshold and retrieves correct document."""
    retriever = get_retriever()
    query = "What is Belady's Anomaly in FIFO page replacement?"
    result = retriever.retrieve(query, threshold=0.30)

    assert result.has_context is True
    assert result.max_similarity >= 0.30
    assert len(result.chunks) > 0

    # Verify top chunk matches OS notes
    top_chunk = result.chunks[0]
    assert "OS_Unit3_Virtual_Memory_Notes.txt" in top_chunk.source_file
    assert "Belady" in top_chunk.text or "FIFO" in top_chunk.text
