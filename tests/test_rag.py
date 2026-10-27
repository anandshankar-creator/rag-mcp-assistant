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


def test_regression_uploaded_document_summary_retrieval():
    """
    Regression Test:
    Verifies that procedural / meta-inquiries like 'Summarize the uploaded document'
    properly resolve to the uploaded document in ChromaDB rather than tripping the
    low-similarity threshold gate or falling back to ungrounded chat.
    """
    retriever = get_retriever()
    query = "Summarize the uploaded document. List its five most important points and cite the relevant source pages or sections"
    result = retriever.retrieve(query)

    assert result.has_context is True, "Uploaded document summary query must pass context retrieval"
    assert len(result.chunks) > 0, "Expected overview chunks to be returned"
    assert result.max_similarity >= 0.35, "Overview chunks must satisfy similarity threshold"

    # Verify chunks have correct metadata
    for c in result.chunks:
        assert c.source_file, "Source file must not be empty"
        assert c.page >= 1, "Page number must be a valid positive integer"
        assert len(c.text.strip()) > 0, "Chunk text must not be empty"


def test_regression_citation_extraction_with_spaces():
    """
    Regression Test:
    Verifies that extract_citations correctly extracts citations from document filenames
    containing spaces and complex formatting like 'Guardian_AI_Project_Phase_1_Report 2.0.pdf'.
    """
    from rag.generator import extract_citations

    sample_text = (
        "Guardian AI is a multimodal safety system [Guardian_AI_Project_Phase_1_Report 2.0.pdf, page 14]. "
        "It provides real-time emergency detection [Guardian_AI_Project_Phase_1_Report 2.0.pdf, pages 2, 3]."
    )
    cites = extract_citations(sample_text)
    assert "Guardian_AI_Project_Phase_1_Report 2.0.pdf, page 14" in cites
    assert "Guardian_AI_Project_Phase_1_Report 2.0.pdf, page 2" in cites
    assert "Guardian_AI_Project_Phase_1_Report 2.0.pdf, page 3" in cites


def test_regression_distinguish_no_file_uploaded():
    """
    Regression Test:
    Verifies that the RAG Generator distinguishes between 'no document uploaded'
    and 'document indexed but query not found'.
    """
    from rag.generator import RAGGenerator
    from rag.retriever import RetrievalResult

    class MockEmptyRetriever:
        store = type('MockStore', (), {'get_collection_stats': lambda s: {'total_chunks': 0, 'source_files': []}})()
        def retrieve(self, query, top_k=None, threshold=None):
            return RetrievalResult(
                query=query,
                chunks=[],
                passed_threshold=False,
                max_similarity=0.0,
                threshold_applied=0.35,
                has_indexed_documents=False,
            )

    gen = RAGGenerator(retriever=MockEmptyRetriever())
    resp = gen.answer_question("Summarize the uploaded document")
    assert resp.refused is True
    assert resp.origin == "NO_DOCUMENTS"
    assert "no documents have been uploaded or indexed" in resp.answer.lower()


def test_regression_no_ungrounded_fallback_on_missing_document_evidence():
    """
    Regression Test:
    Verifies that requests explicitly requiring summarizing or citing an uploaded document
    do NOT fall back to ungrounded chat or web search when retrieval returns no relevant context.
    They must return a clear, grounded refusal (origin='NOT_FOUND', refused=True).
    """
    from rag.generator import RAGGenerator
    from rag.retriever import RetrievalResult

    class MockEmptyMatchRetriever:
        store = type('MockStore', (), {'get_collection_stats': lambda s: {'total_chunks': 10, 'source_files': ['some_doc.pdf']}})()
        def retrieve(self, query, top_k=None, threshold=None):
            return RetrievalResult(
                query=query,
                chunks=[],
                passed_threshold=False,
                max_similarity=0.15,
                threshold_applied=0.35,
                has_indexed_documents=True,
            )

    gen = RAGGenerator(retriever=MockEmptyMatchRetriever())
    # Query explicitly requiring summarizing or citing an uploaded document
    query = "Summarize the document and cite the relevant source pages"
    resp = gen.answer_question(query, allow_web_fallback=True)

    assert resp.refused is True, "Must refuse when local document evidence is missing"
    assert resp.origin == "NOT_FOUND", f"Expected origin 'NOT_FOUND', got {resp.origin}"
    assert resp.source_type == "local_refusal", f"Expected 'local_refusal', got {resp.source_type}"
    assert "couldn't find this in your documents" in resp.answer.lower()
    assert "not verified against your documents" not in resp.answer.lower(), "Must NOT leak ungrounded chat note"


def test_regression_session_rerun_and_persistence_last_uploaded_doc():
    """
    Regression Test:
    Verifies that last_uploaded_doc persists across session reruns in SQLite ConversationMemory,
    enabling the Retriever to accurately resolve 'the uploaded document' across multiple turns.
    """
    from agents.memory import ConversationMemory
    from rag.retriever import get_retriever

    test_file = "Guardian_AI_Project_Phase_1_Report 2.0.pdf"
    ConversationMemory.set_preference("last_uploaded_doc", test_file)

    # Verify persistent SQLite retrieval
    reloaded_pref = ConversationMemory.get_preference("last_uploaded_doc")
    assert reloaded_pref == test_file

    retriever = get_retriever()
    query = "Summarize the uploaded document and list the key points"
    result = retriever.retrieve(query)

    assert result.has_context is True
    assert len(result.chunks) > 0
    # Chunks must come from the persisted uploaded document
    for c in result.chunks:
        assert c.source_file == test_file


if __name__ == "__main__":
    pytest.main(["-v", __file__])
