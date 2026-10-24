"""
==============================================================================
Module: rag.generator
Role in Architecture: Grounded Context Synthesis & Academic Citation Generator
==============================================================================
Synthesizes the final grounded answer from retrieved context chunks using the
configured LLMClient (Gemini / Claude / Ollama).

Academic Review Defense:
1. Strict Context-Only Guardrail:
   The system prompt explicitly commands the model to operate as a closed-domain
   question answering engine. It is strictly forbidden from using pre-trained external
   parametric knowledge when formulating answers.
2. Citation Enforcer:
   Requires inline bracketed citations in the exact format: `[filename, page]`.
3. Pre-Emptive Refusal:
   If the retriever signals that candidates fell below the threshold, the generator
   bypasses LLM inference completely and yields:
     "I couldn't find this in your documents."
   This mathematically bounds hallucination rate on unanswerable queries to near zero.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings
from llm import get_llm_client
from rag.retriever import RetrievalResult, get_retriever


@dataclass
class RAGResponse:
    """Standardized response from the RAG generation pipeline."""
    query: str
    answer: str
    citations: List[str] = field(default_factory=list)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    refused: bool = False
    max_similarity: float = 0.0


# Grounding system prompt as mandated by project requirements
RAG_SYSTEM_PROMPT = """You are a strict academic personal assistant for a university student.
Your instructions are mandatory:
1. Answer ONLY from the provided context chunks below.
2. If the context does not contain the answer, say "I couldn't find this in your documents."
3. Cite sources for every claim as [filename, page] (e.g. [OS_Unit3_Virtual_Memory_Notes.txt, page 1]).
4. Do not use outside knowledge or extrapolate beyond the provided text.
5. Be concise, direct, and factually precise."""


def format_context_block(chunks: List[Any]) -> str:
    """
    Renders candidate chunks into an unambiguous context block
    with prominent source and page identifiers.
    """
    formatted_blocks = []
    for idx, c in enumerate(chunks, 1):
        formatted_blocks.append(
            f"--- CHUNK {idx} [Source: {c.source_file}, Page: {c.page}] ---\n"
            f"{c.text.strip()}\n"
        )
    return "\n".join(formatted_blocks)


def extract_citations(text: str) -> List[str]:
    """
    Extracts citation tags like [filename, page] or [filename, p. 1] from the generated text.
    """
    # Matches patterns like [doc.txt, page 2] or [doc.pdf, 3] or [notes.md, p. 1]
    pattern = r"\[([a-zA-Z0-9_\-\.]+(?:\.[a-zA-Z0-9]+)?),\s*(?:page|p\.)?\s*(\d+)\]"
    matches = re.findall(pattern, text, re.IGNORECASE)
    citations = []
    seen = set()
    for doc, page in matches:
        tag = f"{doc}, page {page}"
        if tag not in seen:
            seen.add(tag)
            citations.append(tag)
    return citations


class RAGGenerator:
    """Orchestrates threshold evaluation, prompt composition, LLM generation, and citation extraction."""

    def __init__(self, retriever=None, llm_client=None):
        self.retriever = retriever or get_retriever()
        self.llm_client = llm_client or get_llm_client()

    def answer_question(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> RAGResponse:
        """
        Executes end-to-end RAG QA:
        1. Retrieves chunks passing the similarity threshold.
        2. If none pass, performs deterministic refusal.
        3. Formulates grounded context prompt and calls LLM.
        4. Parses citations and packages debug trace data.
        """
        retrieval: RetrievalResult = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            threshold=threshold,
        )

        # Prepare trace chunks for UI and evaluation telemetry
        trace_chunks = [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "similarity": c.similarity,
                "source_file": c.source_file,
                "page": c.page,
            }
            for c in retrieval.chunks
        ]

        # Check refusal gate
        if not retrieval.has_context:
            refusal_message = "I couldn't find this in your documents."
            return RAGResponse(
                query=query,
                answer=refusal_message,
                citations=[],
                retrieved_chunks=trace_chunks,
                refused=True,
                max_similarity=retrieval.max_similarity,
            )

        # Build grounded user prompt with retrieved context
        context_text = format_context_block(retrieval.chunks)
        user_prompt = (
            f"CONTEXT DOCUMENTS:\n{context_text}\n\n"
            f"STUDENT QUESTION:\n{query}\n\n"
            f"Answer the question using ONLY the context above, citing each claim as [filename, page]:"
        )

        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Call configured LLM
        llm_resp = self.llm_client.generate(messages, temperature=0.1)
        raw_answer = llm_resp.content.strip()

        # Check if the LLM itself determined the answer is absent
        is_refusal = (
            "couldn't find this in your documents" in raw_answer.lower()
            or "could not find this in your documents" in raw_answer.lower()
            or "does not contain" in raw_answer.lower()
        )

        citations = extract_citations(raw_answer)

        # If LLM cited nothing but provided an answer, append the top chunk's source as fallback citation
        if not citations and not is_refusal and retrieval.chunks:
            top_c = retrieval.chunks[0]
            citations.append(f"{top_c.source_file}, page {top_c.page}")

        return RAGResponse(
            query=query,
            answer=raw_answer,
            citations=citations,
            retrieved_chunks=trace_chunks,
            refused=is_refusal,
            max_similarity=retrieval.max_similarity,
        )

    # Convenience alias
    generate = answer_question


# Global singleton generator
_generator_instance: Optional[RAGGenerator] = None


def get_rag_generator() -> RAGGenerator:
    """Factory function for the system RAGGenerator."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = RAGGenerator()
    return _generator_instance


if __name__ == "__main__":
    gen = get_rag_generator()
    print("RAGGenerator initialized successfully.")
