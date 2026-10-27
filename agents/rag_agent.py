"""
==============================================================================
Module: agents.rag_agent
Role in Architecture: Grounded Knowledge Retrieval Agent
==============================================================================
Specialized agent wrapping the Phase 2 RAG pipeline.
Handles knowledge retrieval from the student's personal documents (notes,
syllabus, exam timetable), strictly grounding the output with citations.

Telemetry:
Returns answer, verified citations, and detailed trace telemetry for the UI
debug panel and evaluation module.
"""

from __future__ import annotations
from typing import Any, Dict, List
from rag.generator import get_rag_generator, RAGResponse


class RAGAgent:
    """Agent node responsible for grounded document QA."""

    def __init__(self, generator=None):
        self.generator = generator or get_rag_generator()

    def run(self, query: str, allow_web_fallback: bool = True) -> Dict[str, Any]:
        """
        Executes grounded retrieval and synthesis for the query.
        """
        rag_resp: RAGResponse = self.generator.answer_question(
            query,
            allow_web_fallback=allow_web_fallback,
        )

        return {
            "answer": rag_resp.answer,
            "citations": rag_resp.citations,
            "refused": rag_resp.refused,
            "max_similarity": rag_resp.max_similarity,
            "retrieved_chunks": rag_resp.retrieved_chunks,
            "source_type": rag_resp.source_type,
            "origin": getattr(rag_resp, "origin", "LOCAL"),
            "tiers": getattr(rag_resp, "tiers", []),
            "verified_quotes": getattr(rag_resp, "verified_quotes", []),
            "urls": getattr(rag_resp, "urls", []),
            "decision_path": getattr(rag_resp, "decision_path", ""),
        }


# Global instance
_rag_agent_instance = None


def get_rag_agent() -> RAGAgent:
    global _rag_agent_instance
    if _rag_agent_instance is None:
        _rag_agent_instance = RAGAgent()
    return _rag_agent_instance
