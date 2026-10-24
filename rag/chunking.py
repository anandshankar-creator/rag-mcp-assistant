"""
==============================================================================
Module: rag.chunking
Role in Architecture: Document Chunking and Token Windowing
==============================================================================
Splits extracted document texts into uniform, semantically cohesive chunks.

Key Architectural Parameters:
- `chunk_size`: ~500 tokens (approx. 2000 characters). Balances retaining enough
  academic context to answer multi-part questions while avoiding context dilution.
- `chunk_overlap`: ~50 tokens (approx. 200 characters). Sliding window overlap
  prevents critical definitions or exam dates that fall on chunk boundaries from
  getting bisected or lost.
- Metadata Preservation: Every chunk inherits {source_file, page} and gets a
  deterministic chunk_id: `{source_file}_p{page}_c{idx}`.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from app.config import settings
from rag.ingest import Document


@dataclass
class Chunk:
    """Represents a discrete semantic chunk indexed in the vector store."""
    chunk_id: str
    text: str
    metadata: Dict[str, str | int] = field(default_factory=dict)

    @property
    def source_file(self) -> str:
        return str(self.metadata.get("source_file", "unknown"))

    @property
    def page(self) -> int:
        return int(self.metadata.get("page", 1))

    @property
    def token_count(self) -> int:
        return int(self.metadata.get("token_count", 0))


def estimate_tokens(text: str) -> int:
    """
    Fast, model-agnostic token estimator (~0.75 words per token or 4 chars per token).
    Splits on whitespace and punctuation tokens.
    """
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def chunk_text(
    text: str,
    chunk_size_tokens: int = 500,
    chunk_overlap_tokens: int = 50,
) -> List[str]:
    """
    Sliding window chunking algorithm operating on word/sentence boundaries.
    Ensures no word is cut midway, and preserves paragraph breaks where possible.
    """
    if not text.strip():
        return []

    # First, split into paragraph blocks to preserve structural unity
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: List[str] = []
    current_tokens: List[str] = []
    current_token_count = 0

    # Tokenize by words while preserving space
    words = re.findall(r"\S+|\n", text)
    if not words:
        return [text]

    i = 0
    total_words = len(words)

    # Convert token limits to approximate word limits (1 token ~ 0.75 words)
    target_words = max(50, int(chunk_size_tokens * 0.75))
    overlap_words = max(10, int(chunk_overlap_tokens * 0.75))
    step = max(1, target_words - overlap_words)

    while i < total_words:
        chunk_slice = words[i : i + target_words]
        chunk_str = " ".join(chunk_slice)
        # Clean up space before newlines
        chunk_str = chunk_str.replace(" \n ", "\n\n").replace(" \n", "\n")
        chunks.append(chunk_str.strip())
        i += step

        # If the remaining words are fewer than the overlap, include them and terminate
        if i + overlap_words >= total_words and i < total_words:
            remaining_slice = words[i:]
            if remaining_slice:
                remaining_str = " ".join(remaining_slice).replace(" \n ", "\n\n").strip()
                chunks.append(remaining_str)
            break

    return [c for c in chunks if c.strip()]


def chunk_documents(
    documents: List[Document],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Chunk]:
    """
    Transforms a list of ingested Document pages into granular Chunks.
    Inherits all metadata and attaches chunk_id and token_count.
    """
    target_size = chunk_size or settings.RAG_CHUNK_SIZE
    target_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

    all_chunks: List[Chunk] = []

    for doc in documents:
        text_pieces = chunk_text(
            text=doc.content,
            chunk_size_tokens=target_size,
            chunk_overlap_tokens=target_overlap,
        )

        for idx, piece in enumerate(text_pieces):
            clean_filename = re.sub(r"[^\w\-.]", "_", doc.source_file)
            c_id = f"{clean_filename}_p{doc.page}_c{idx + 1}"
            
            chunk_meta = dict(doc.metadata)
            chunk_meta["chunk_id"] = c_id
            chunk_meta["chunk_index"] = idx + 1
            chunk_meta["token_count"] = estimate_tokens(piece)

            all_chunks.append(
                Chunk(
                    chunk_id=c_id,
                    text=piece,
                    metadata=chunk_meta,
                )
            )

    return all_chunks


if __name__ == "__main__":
    from rag.ingest import load_documents
    print("Testing chunking on extracted documents...")
    docs = load_documents()
    chunks = chunk_documents(docs)
    print(f"Total chunks created: {len(chunks)}")
    for c in chunks[:3]:
        print(f"[{c.chunk_id}] {c.source_file} (Page {c.page}) -> {c.token_count} tokens")
        print(f"Sample: {c.text[:120]}...\n")
