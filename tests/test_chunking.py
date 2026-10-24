"""
==============================================================================
Test Suite: Chunking & Windowing Validation
==============================================================================
Validates:
1. estimate_tokens correctly estimates token counts.
2. chunk_text generates non-empty chunks with sliding window overlap.
3. chunk_documents preserves metadata and generates deterministic chunk IDs.
4. Edge cases: empty text, single short paragraph, very long text.
"""

from rag.chunking import Chunk, chunk_documents, chunk_text, estimate_tokens
from rag.ingest import Document


def test_estimate_tokens():
    text = "APJ Abdul Kalam Technological University Operating Systems CS402"
    tokens = estimate_tokens(text)
    assert tokens > 0
    assert tokens == 8


def test_chunk_text_single_short():
    short_text = "Virtual memory allows secondary memory to be addressed as main memory."
    chunks = chunk_text(short_text, chunk_size_tokens=100, chunk_overlap_tokens=20)
    assert len(chunks) == 1
    assert "Virtual memory" in chunks[0]


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []


def test_chunk_text_overlap():
    words = [f"word{i}" for i in range(300)]
    long_text = " ".join(words)

    chunks = chunk_text(long_text, chunk_size_tokens=100, chunk_overlap_tokens=20)
    assert len(chunks) > 1

    # Check that adjacent chunks share overlapping words
    chunk0_words = set(chunks[0].split())
    chunk1_words = set(chunks[1].split())
    shared_words = chunk0_words.intersection(chunk1_words)
    assert len(shared_words) > 0, "Adjacent chunks must share overlapping words"


def test_chunk_documents_metadata_preservation():
    docs = [
        Document(
            content="Operating Systems Module 3: Virtual Memory notes.",
            metadata={"source_file": "OS_Unit3_Notes.txt", "page": 1, "doc_type": "txt"},
        ),
        Document(
            content="Relational Algebra Module 2: Select, Project, Join.",
            metadata={"source_file": "DBMS_Unit2_Notes.md", "page": 2, "doc_type": "md"},
        ),
    ]

    chunks = chunk_documents(docs, chunk_size=50, chunk_overlap=10)
    assert len(chunks) >= 2

    # Check first chunk metadata
    c0 = chunks[0]
    assert c0.source_file == "OS_Unit3_Notes.txt"
    assert c0.page == 1
    assert "p1" in c0.chunk_id
    assert c0.token_count > 0

    # Check second doc chunk
    c1 = chunks[1]
    assert c1.source_file == "DBMS_Unit2_Notes.md"
    assert c1.page == 2
    assert "p2" in c1.chunk_id
