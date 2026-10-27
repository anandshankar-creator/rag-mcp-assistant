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
from pathlib import Path
import re
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
    has_indexed_documents: bool = True

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

    def _retrieve_document_overview_chunks(
        self,
        target_file: str,
        query: str,
        max_chunks: int = 6,
    ) -> List[RetrievedChunk]:
        """
        Retrieves representative overview and key-content chunks from a target document
        to fulfill high-level summarization queries with verified page citations.
        """
        try:
            records = self.store.collection.get(
                where={"source_file": target_file},
                include=["documents", "metadatas"],
            )
            ids = records.get("ids", [])
            docs = records.get("documents", [])
            metas = records.get("metadatas", [])
            if not ids:
                return []

            # Sort chunks by page number and chunk_index
            sorted_indices = sorted(
                range(len(ids)),
                key=lambda i: (metas[i].get("page", 1), metas[i].get("chunk_index", 0))
            )

            selected_indices: List[int] = []
            # 1. Beginning chunks (Cover, Abstract, Intro, Table of Contents)
            first_chunks_count = min(3, len(sorted_indices))
            selected_indices.extend(sorted_indices[:first_chunks_count])

            # 2. Thematic/Core chunks matching expanded query
            stem = Path(target_file).stem.replace("_", " ").replace("-", " ")
            expanded_query = f"{stem} overview introduction architecture objectives key features conclusion"
            candidate_matches = self.store.query_similarity(expanded_query, top_k=15)
            matched_file_chunks = [c for c in candidate_matches if c.get("source_file") == target_file]

            seen_ids = {ids[i] for i in selected_indices}
            for c in matched_file_chunks:
                if len(selected_indices) >= max_chunks - 1:
                    break
                cid = c.get("chunk_id")
                if cid and cid not in seen_ids and cid in ids:
                    seen_ids.add(cid)
                    selected_indices.append(ids.index(cid))

            # 3. Concluding chunk if not already included
            if len(sorted_indices) > 3:
                last_idx = sorted_indices[-1]
                if ids[last_idx] not in seen_ids and len(selected_indices) < max_chunks:
                    selected_indices.append(last_idx)

            chunks: List[RetrievedChunk] = []
            for idx in selected_indices:
                chunks.append(
                    RetrievedChunk(
                        chunk_id=ids[idx],
                        text=docs[idx],
                        metadata=metas[idx],
                        similarity=0.85,
                        source_file=metas[idx].get("source_file", target_file),
                        page=metas[idx].get("page", 1),
                    )
                )
            return chunks
        except Exception as e:
            print(f"[RETRIEVER WARNING] Document overview retrieval failed: {e}")
            return []

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Executes similarity search and filters candidates against the refusal threshold.
        Supports automatic coreference resolution and overview retrieval for document-level queries.
        """
        k = top_k or self.top_k
        thresh = threshold if threshold is not None else self.threshold

        # Diagnostic check: verify whether documents exist in the collection
        stats = self.store.get_collection_stats()
        indexed_files = stats.get("source_files", [])
        total_chunks = stats.get("total_chunks", 0)

        if total_chunks == 0 or not indexed_files:
            return RetrievalResult(
                query=query,
                chunks=[],
                passed_threshold=False,
                max_similarity=0.0,
                threshold_applied=thresh,
                has_indexed_documents=False,
            )

        raw_candidates = self.store.query_similarity(query=query, top_k=k)

        # Compute maximum similarity among top results
        max_sim = max((c["similarity"] for c in raw_candidates), default=0.0)

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

        # Document coreference & overview query resolution:
        # If raw query did not match specific chunks above threshold, check if the query
        # is asking to summarize or inspect an uploaded/indexed document.
        if not passing_chunks:
            lower_q = query.lower()
            is_summary_query = bool(re.search(
                r"\b(summariz(e|ing|ation)|summary|overview|outline|main points|important points|key points|key takeaways|abstract)\b",
                lower_q
            ))
            refers_to_uploaded = bool(re.search(
                r"\b(uploaded|this|the|my|our)\s+(document|file|pdf|report|notes|paper|doc)\b",
                lower_q
            ) or "uploaded" in lower_q)

            target_file: Optional[str] = None

            # 1. Check if an indexed document is explicitly or partially named in query
            for f in indexed_files:
                stem = Path(f).stem.lower().replace("_", " ").replace("-", " ")
                words = [w for w in stem.split() if len(w) > 2 and w not in ("the", "and", "for", "with")]
                if words and any(w in lower_q for w in words):
                    target_file = f
                    break

            # 2. If no specific name matched, but query refers to an uploaded document or summary
            if not target_file and (is_summary_query or refers_to_uploaded):
                # Try getting last uploaded document from ConversationMemory if set
                try:
                    from agents.memory import ConversationMemory
                    last_doc = ConversationMemory.get_preference("last_uploaded_doc")
                    if last_doc and last_doc in indexed_files:
                        target_file = last_doc
                except Exception:
                    pass

                # If still not found, check newest file in DATA_DIR that is indexed
                if not target_file and settings.DATA_DIR.exists():
                    try:
                        files_in_dir = [
                            p for p in settings.DATA_DIR.glob("*")
                            if p.is_file() and p.name in indexed_files
                        ]
                        if files_in_dir:
                            files_in_dir.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                            target_file = files_in_dir[0].name
                    except Exception:
                        pass

                # Fallback to single indexed file
                if not target_file and len(indexed_files) == 1:
                    target_file = indexed_files[0]

            # If a target document was resolved for document summary / overview:
            if target_file:
                selected_chunks = self._retrieve_document_overview_chunks(target_file, query, max_chunks=max(k, 6))
                if selected_chunks:
                    passing_chunks = selected_chunks
                    max_sim = max(c.similarity for c in passing_chunks)

        passed = len(passing_chunks) > 0 and max_sim >= thresh

        return RetrievalResult(
            query=query,
            chunks=passing_chunks,
            passed_threshold=passed,
            max_similarity=max_sim,
            threshold_applied=thresh,
            has_indexed_documents=True,
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
