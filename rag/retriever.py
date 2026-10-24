"""
==============================================================================
Module: rag.retriever
Role in Architecture: Threshold-Gated Semantic Context Retriever
==============================================================================
Dispatches queries against ChromaDB, sorts candidate chunks by cosine similarity,
and implements the critical Academic Refusal Gate.

Key Academic Mechanism (Anti-Hallucination Gate):
Standard RAG naively forces the top-K chunks into the LLM prompt regardless of
whether they are semantically relevant. When asked an out-of-domain question
(e.g., "Who won the 2018 World Cup?"), standard RAG feeds the closest (yet irrelevant)
OS notes chunks to the model, leading to hallucinations.

Our Architecture:
If the maximum cosine similarity score among the retrieved candidates is strictly
below `RAG_SIMILARITY_THRESHOLD` (default 0.35), the retriever trips the gate:
  `passed_threshold = False`
This immediately bypasses LLM generation and signals a graceful refusal:
  "I couldn't find this in your documents."
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings
from rag.vectorstore import get_vector_store


@dataclass
class RetrievedChunk:
    """Standardized retrieved chunk container."""
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    similarity: float
    source_file: str
    page: int


@dataclass
class RetrievalResult:
    """Encapsulates the complete retrieval state and anti-hallucination decision."""
    query: str
    chunks: List[RetrievedChunk] = field(default_factory=list)
    passed_threshold: bool = False
    max_similarity: float = 0.0
    threshold_applied: float = 0.35

    @property
    def has_context(self) -> bool:
        return self.passed_threshold and len(self.chunks) > 0


class Retriever:
    """Coordinates vector search with similarity filtering and threshold gating."""

    def __init__(
        self,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ):
        self.top_k = top_k or settings.RAG_TOP_K
        self.threshold = threshold if threshold is not None else settings.RAG_SIMILARITY_THRESHOLD
        self.store = get_vector_store()

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Executes similarity search and filters candidates against the refusal threshold.
        """
        k = top_k or self.top_k
        thresh = threshold if threshold is not None else self.threshold

        raw_candidates = self.store.query_similarity(query=query, top_k=k)

        if not raw_candidates:
            return RetrievalResult(
                query=query,
                chunks=[],
                passed_threshold=False,
                max_similarity=0.0,
                threshold_applied=thresh,
            )

        # Compute maximum similarity among top results
        max_sim = max(c["similarity"] for c in raw_candidates)

        # Filter chunks that satisfy the similarity threshold
        passing_chunks: List[RetrievedChunk] = []
        for c in raw_candidates:
            if c["similarity"] >= thresh:
                passing_chunks.append(
                    RetrievedChunk(
                        chunk_id=c["chunk_id"],
                        text=c["text"],
                        metadata=c["metadata"],
                        similarity=c["similarity"],
                        source_file=c["source_file"],
                        page=c["page"],
                    )
                )

        passed = len(passing_chunks) > 0 and max_sim >= thresh

        return RetrievalResult(
            query=query,
            chunks=passing_chunks,
            passed_threshold=passed,
            max_similarity=max_sim,
            threshold_applied=thresh,
        )


# Singleton instance
_retriever_instance: Optional[Retriever] = None


def get_retriever() -> Retriever:
    """Factory function for the system Retriever instance."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = Retriever()
    return _retriever_instance


if __name__ == "__main__":
    retriever = get_retriever()
    print(f"Retriever initialized. Top-K: {retriever.top_k}, Threshold: {retriever.threshold}")
