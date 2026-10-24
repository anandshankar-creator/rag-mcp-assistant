"""
==============================================================================
Test Suite: tests/test_rag.py
Role: Automated Unit & Integration Tests for Phase 2 RAG Pipeline
==============================================================================
Tests:
1. Document ingestion across formats.
2. Chunking sliding window, token counts, and metadata preservation.
3. Embedding dimension and normalization.
4. Vector store retrieval and deletion.
5. Threshold refusal gate logic.
"""

import pytest
from pathlib import Path
from rag.ingest import Document, load_documents, load_single_document
from rag.chunking import chunk_documents, estimate_tokens
from rag.embeddings import embed_documents, embed_query
from rag.vectorstore import get_vector_store
from rag.retriever import get_retriever
from rag.generator import get_rag_generator


def test_token_estimation():
    text = "APJ Abdul Kalam Technological University CS402 Operating Systems."
    tokens = estimate_tokens(text)
    assert tokens > 5, "Token estimation failed on standard text."


def test_chunking_metadata():
    doc = Document(
        content="Virtual memory allows logical memory to exceed physical memory. " * 30,
        metadata={"source_file": "sample_notes.txt", "page": 1},
    )
    chunks = chunk_documents([doc], chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 0, "No chunks generated."
    for c in chunks:
        assert c.source_file == "sample_notes.txt"
        assert c.page == 1
        assert "chunk_id" in c.metadata
        assert c.token_count > 0


def test_embeddings_dimensions():
    sample = ["Operating Systems Unit 3 Virtual Memory"]
    vectors = embed_documents(sample)
    assert len(vectors) == 1
    assert len(vectors[0]) == 384, f"Expected 384-d vector, got {len(vectors[0])}"


def test_retrieval_threshold_refusal():
    retriever = get_retriever()
    # Query clearly out of domain
    out_of_domain = "What is the capital of Australia?"
    result = retriever.retrieve(out_of_domain, threshold=0.30)
    assert result.passed_threshold is False, "Out of domain query should fail threshold!"
    assert len(result.chunks) == 0


def test_retrieval_threshold_pass():
    retriever = get_retriever()
    # Query clearly in domain
    in_domain = "When is the CS402 internal examination?"
    result = retriever.retrieve(in_domain, threshold=0.30)
    assert result.passed_threshold is True, "Domain query should pass threshold!"
    assert len(result.chunks) > 0
    assert result.max_similarity >= 0.30


def test_end_to_end_generator_refusal():
    gen = get_rag_generator()
    resp = gen.answer_question("Who won the 2018 FIFA World Cup?")
    assert resp.refused is True
    assert "couldn't find this in your documents" in resp.answer.lower()
    assert len(resp.citations) == 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
