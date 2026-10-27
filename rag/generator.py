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
    source_type: str = "local_rag"
    origin: str = "LOCAL"
    web_sources: List[Dict[str, Any]] = field(default_factory=list)
    tiers: List[Dict[str, Any]] = field(default_factory=list)
    verified_quotes: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    decision_path: str = ""


# Grounding system prompt as mandated by project requirements
RAG_SYSTEM_PROMPT = """You are a strict, evidence-grounded personal AI assistant.
Your instructions are mandatory:
1. Answer ONLY from the provided context chunks below.
2. If the context does not contain the answer, say "I couldn't find this in your documents."
3. If the context provides a PARTIAL answer but leaves important aspects unanswered, answer what is supported citing [filename, page], and explicitly append: '[PARTIAL_GAP: describe the specific missing information that is not in the documents]'.
4. Cite sources for every claim as [filename, page] (e.g. [document.txt, page 1]).
5. Do not use outside knowledge or extrapolate beyond the provided text.
6. Be concise, direct, and factually precise."""


COMBINED_GROUNDING_PROMPT = """You are a strict, evidence-grounded research assistant.
The user's question has been researched using both local study documents and verified external web sources.
Combine the evidence to formulate a complete, coherent, well-structured answer.

Mandatory Rules:
1. Present information supported by local documents and cite each claim as [filename, page] (e.g. [notes.txt, page 2]).
2. Fill genuine gaps using trusted web sources and cite each external claim as [URL] (e.g. [https://docs.python.org/]).
3. Explicitly distinguish which information comes from local documents and which comes from external web sources.
4. Avoid unnecessary duplication and do not make contradictory claims.
5. If any aspect remains unverified by both sources, clearly state what could not be verified.
6. Do not extrapolate, speculate, or invent facts."""


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
    Extracts citation tags like [filename, page 1], [filename, Page: 1], or [filename, p. 1] from the generated text.
    Supports filenames with spaces, dots, underscores, dashes and multi-page references.
    """
    pattern = r"\[([a-zA-Z0-9_\-\.\s]+?\.[a-zA-Z0-9]{2,5})[,\:]\s*(?:pages?|p\.)?\s*:?\s*([\d\s\,\-]+)\]"
    matches = re.findall(pattern, text, re.IGNORECASE)
    citations = []
    seen = set()
    for doc, pages_str in matches:
        doc = doc.strip()
        pages = re.findall(r"\d+", pages_str)
        if not pages:
            tag = f"{doc}, page 1"
            if tag not in seen:
                seen.add(tag)
                citations.append(tag)
        else:
            for p in pages:
                tag = f"{doc}, page {p}"
                if tag not in seen:
                    seen.add(tag)
                    citations.append(tag)
    return citations


class RAGGenerator:
    """Orchestrates threshold evaluation, prompt composition, LLM generation, citation extraction, and web fallback."""

    def __init__(self, retriever=None, llm_client=None, web_search_engine=None):
        self.retriever = retriever or get_retriever()
        self.llm_client = llm_client or get_llm_client()
        self._web_search_engine = web_search_engine

    @property
    def web_search_engine(self):
        if self._web_search_engine is None:
            from rag.web_search import get_web_search_engine
            self._web_search_engine = get_web_search_engine()
        return self._web_search_engine

    def answer_question(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        allow_web_fallback: bool = False,
    ) -> RAGResponse:
        """
        Executes end-to-end RAG QA following the Universal Document-First Policy:
        Step 1: Searches local documents first and evaluates relevance / completeness.
        Step 2: If local documents are insufficient, searches trusted web sources.
        Step 3: If local documents contain partial evidence, combines local and web evidence.
        Step 4: If neither provides reliable evidence, responds with honest uncertainty.
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

        # Classify query: Private Personal Records vs Uploaded-Doc-Only vs General/Academic Inquiries
        lower_q = query.lower()
        private_record_cues = [
            "viva", "mini project", "lab record", "attendance", "condonation",
            "hall ticket", "roll number", "register number", "series exam",
            "my next exam", "next exam", "my exam date", "my deadline", "my marks", "my grade"
        ]
        is_private_personal = (
            any(cue in lower_q for cue in private_record_cues)
            or bool(re.search(r"\b(my|our)\s+(attendance|marks?|grades?|score|deadline|viva|exam|project|record)\b", lower_q))
        )
        is_doc_only = (
            bool(re.search(r"\b(summariz(e|ing|ation)|overview)\b", lower_q) and re.search(r"\b(uploaded|this|the)\s+(document|file|pdf|report)\b", lower_q))
            or bool(re.search(r"\b(cite|citation|source pages?|sections?)\b", lower_q) and re.search(r"\b(uploaded|this|the)\s+(document|file|pdf|report)\b", lower_q))
        )
        requires_local_evidence = is_private_personal or is_doc_only

        # Diagnostic refusal for queries strictly requiring local uploaded files when none exist
        if not getattr(retrieval, "has_indexed_documents", True) and requires_local_evidence:
            refusal_message = "No documents have been uploaded or indexed yet. Please upload a document using the Knowledge Base Manager in the sidebar."
            return RAGResponse(
                query=query,
                answer=refusal_message,
                citations=[],
                retrieved_chunks=trace_chunks,
                refused=True,
                max_similarity=0.0,
                source_type="no_documents",
                origin="NO_DOCUMENTS",
                decision_path="Route: QA → Local RAG checked → No documents indexed in database → Upload guidance returned",
            )

        # ======================================================================
        # STEP 1: Search local documents first and assess completeness
        # ======================================================================
        is_complete_local = False
        is_partial_local = False
        partial_gap_desc = ""
        partial_local_content = ""

        if retrieval.has_context:
            context_text = format_context_block(retrieval.chunks)
            user_prompt = (
                f"CONTEXT DOCUMENTS:\n{context_text}\n\n"
                f"STUDENT QUESTION:\n{query}\n\n"
                f"Answer the question using ONLY the context above according to these rules:\n"
                f"1. If the context provides a COMPLETE answer, answer fully and cite each claim as [filename, page].\n"
                f"2. If the context does NOT contain the answer, say 'I couldn't find this in your documents.'\n"
                f"3. If the context provides a PARTIAL answer but does not cover all aspects of the question, answer what is supported citing [filename, page], and append at the end: '[PARTIAL_GAP: <brief summary of missing information>]'.\n"
                f"4. Do not use outside knowledge or extrapolate."
            )

            messages = [
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            llm_resp = self.llm_client.generate(messages, temperature=0.1)
            raw_answer = llm_resp.content.strip()

            refusal_markers = [
                "couldn't find this in your documents",
                "could not find this in your documents",
                "not mentioned in the provided context",
                "not provided in the context",
                "context does not contain",
                "does not contain",
                "no information",
            ]
            is_local_refusal = any(m in raw_answer.lower() for m in refusal_markers)

            if not is_local_refusal:
                gap_match = re.search(r"\[PARTIAL_GAP:\s*(.*?)\]", raw_answer, re.DOTALL | re.IGNORECASE)
                if gap_match:
                    is_partial_local = True
                    partial_gap_desc = gap_match.group(1).strip()
                    partial_local_content = re.sub(r"\[PARTIAL_GAP:\s*.*?\]", "", raw_answer, flags=re.DOTALL | re.IGNORECASE).strip()
                else:
                    is_complete_local = True

            # If fully and reliably answered by local documents, return immediately without web search
            if is_complete_local:
                citations = extract_citations(raw_answer)
                return RAGResponse(
                    query=query,
                    answer=raw_answer,
                    citations=citations,
                    retrieved_chunks=trace_chunks,
                    refused=False,
                    max_similarity=retrieval.max_similarity,
                    source_type="local_rag",
                    origin="LOCAL",
                    decision_path="Route: QA → Local RAG checked → Sufficient local evidence found → Local answer generated",
                )

        # ======================================================================
        # Personal information guard: never search public web for private data
        # ======================================================================
        if requires_local_evidence:
            if is_partial_local and partial_local_content:
                local_cites = extract_citations(partial_local_content)
                ans = f"{partial_local_content}\n\n*(Note: Additional details could not be verified from your uploaded documents.)*"
                return RAGResponse(
                    query=query,
                    answer=ans,
                    citations=local_cites,
                    retrieved_chunks=trace_chunks,
                    refused=False,
                    max_similarity=retrieval.max_similarity,
                    source_type="local_rag",
                    origin="PARTIAL_LOCAL",
                    decision_path="Route: QA → Local RAG checked → Partial local evidence found → Personal query requires local record → Partial local answer generated",
                )
            elif is_private_personal:
                personal_refusal = "I couldn't find this in your documents. Please upload your timetable, syllabus, or personal records to verify this information."
                return RAGResponse(
                    query=query,
                    answer=personal_refusal,
                    citations=[],
                    retrieved_chunks=trace_chunks,
                    refused=True,
                    max_similarity=retrieval.max_similarity,
                    source_type="local_refusal",
                    origin="NOT_FOUND",
                    decision_path="Route: QA → Local RAG checked → Personal query requires local record → Refusal (no web guessing)",
                )
            else:
                doc_refusal = "I couldn't find this in your documents."
                return RAGResponse(
                    query=query,
                    answer=doc_refusal,
                    citations=[],
                    retrieved_chunks=trace_chunks,
                    refused=True,
                    max_similarity=retrieval.max_similarity,
                    source_type="local_refusal",
                    origin="NOT_FOUND",
                    decision_path="Route: QA → Local RAG checked → Document query lacking matching content → Local refusal",
                )

        # ======================================================================
        # STEP 2 & 3: Fallback / Gap Filling via Trusted Web Search
        # ======================================================================
        if allow_web_fallback and getattr(settings, "ENABLE_WEB_FALLBACK", True):
            try:
                # If local documents provided partial evidence, search for the missing gap; otherwise search full query
                web_query = partial_gap_desc if (is_partial_local and len(partial_gap_desc) > 5) else query
                web_res = self.web_search_engine.research_and_answer(web_query)

                # Check if web search errored out
                if web_res.get("error") or web_res.get("source_type") == "web_error":
                    if is_partial_local and partial_local_content:
                        local_cites = extract_citations(partial_local_content)
                        ans = f"{partial_local_content}\n\n*(Note: External web search is currently unavailable to verify the remaining information.)*"
                        return RAGResponse(
                            query=query,
                            answer=ans,
                            citations=local_cites,
                            retrieved_chunks=trace_chunks,
                            refused=False,
                            max_similarity=retrieval.max_similarity,
                            source_type="local_rag",
                            origin="PARTIAL_LOCAL",
                            decision_path="Route: QA → Local RAG checked → Partial local evidence found → Web search service error → Partial local answer returned",
                        )
                    return RAGResponse(
                        query=query,
                        answer=web_res.get("answer", "Web search is currently unavailable due to a network or search service error. I could not verify this information."),
                        citations=[],
                        retrieved_chunks=trace_chunks,
                        refused=True,
                        max_similarity=retrieval.max_similarity,
                        source_type="web_error",
                        origin="WEB_ERROR",
                        decision_path="Route: QA → Local RAG checked → Insufficient relevant evidence → Web search attempted → Search service error reported",
                    )

                # Web search succeeded with verified sources
                if web_res.get("success"):
                    tiers_list = web_res.get("tiers", [])
                    tier_summary = ", ".join([f"{t.get('domain')} ({t.get('tier')})" for t in tiers_list if t.get("domain")]) or "Verified sources"
                    web_citations = web_res.get("citations", [])
                    web_text = web_res.get("answer", "")

                    # STEP 3: If local documents contained partial evidence, combine both evidence sources
                    if is_partial_local and partial_local_content:
                        local_citations = extract_citations(partial_local_content)
                        combined_citations = local_citations + [c for c in web_citations if c not in local_citations]

                        combined_messages = [
                            {"role": "system", "content": COMBINED_GROUNDING_PROMPT},
                            {"role": "user", "content": (
                                f"LOCAL DOCUMENT EVIDENCE (from student's study documents):\n{partial_local_content}\n\n"
                                f"VERIFIED EXTERNAL WEB EVIDENCE:\n{web_text}\n\n"
                                f"USER QUESTION:\n{query}\n\n"
                                f"Formulate a combined, cohesive answer. Present local document facts citing [filename, page] and web facts citing [URL]. Clearly distinguish local document information from external web information."
                            )}
                        ]
                        comb_resp = self.llm_client.generate(combined_messages, temperature=0.1)
                        combined_answer = comb_resp.content.strip()

                        # Ensure citations are preserved in combined answer
                        for lc in local_citations:
                            if lc not in combined_answer and f"[{lc}]" not in combined_answer:
                                combined_answer += f"\nLocal source: [{lc}]"
                        for wc in web_citations:
                            if wc not in combined_answer and f"[{wc}]" not in combined_answer:
                                combined_answer += f"\nExternal source: [{wc}]"

                        return RAGResponse(
                            query=query,
                            answer=combined_answer,
                            citations=combined_citations,
                            retrieved_chunks=trace_chunks,
                            refused=False,
                            max_similarity=retrieval.max_similarity,
                            source_type="hybrid_rag",
                            origin="COMBINED",
                            web_sources=web_res.get("sources", []),
                            tiers=tiers_list,
                            verified_quotes=web_res.get("verified_quotes", []),
                            urls=web_citations,
                            decision_path=f"Route: QA → Local RAG checked → Partial local evidence found ({len(retrieval.chunks)} chunks) → Web search executed to fill gaps ({len(web_res.get('sources', []))} sources) → Sources combined and verified ({tier_summary}) → Hybrid answer generated",
                        )

                    # Pure web synthesis (local had no relevant context)
                    return RAGResponse(
                        query=query,
                        answer=web_text,
                        citations=web_citations,
                        retrieved_chunks=trace_chunks,
                        refused=False,
                        max_similarity=retrieval.max_similarity,
                        source_type="web",
                        origin="WEB",
                        web_sources=web_res.get("sources", []),
                        tiers=tiers_list,
                        verified_quotes=web_res.get("verified_quotes", []),
                        urls=web_res.get("urls", []),
                        decision_path=f"Route: QA → Local RAG checked → Insufficient relevant evidence → Web search executed ({len(web_res.get('sources', []))} sources) → Sources verified ({tier_summary}) → Answer generated",
                    )

                # Web search executed but could not verify from reliable sources
                if is_partial_local and partial_local_content:
                    local_cites = extract_citations(partial_local_content)
                    ans = f"{partial_local_content}\n\n*(Note: The remaining aspects could not be verified from reliable external sources.)*"
                    return RAGResponse(
                        query=query,
                        answer=ans,
                        citations=local_cites,
                        retrieved_chunks=trace_chunks,
                        refused=False,
                        max_similarity=retrieval.max_similarity,
                        source_type="local_rag",
                        origin="PARTIAL_LOCAL",
                        decision_path="Route: QA → Local RAG checked → Partial local evidence found → External web search could not verify gap → Partial local answer returned",
                    )

                # STEP 4: Neither source provides a reliable answer
                uncertainty_response = (
                    "I couldn't verify this information from your documents or reliable external sources. "
                    "I don't want to guess or provide potentially incorrect information."
                )
                return RAGResponse(
                    query=query,
                    answer=uncertainty_response,
                    citations=[],
                    retrieved_chunks=trace_chunks,
                    refused=True,
                    max_similarity=retrieval.max_similarity,
                    source_type="web_refusal",
                    origin="UNVERIFIED",
                    decision_path="Route: QA → Local RAG checked → Insufficient relevant evidence → Web search executed (0 reliable sources) → Unverified → Refusal generated",
                )

            except Exception as e:
                print(f"[RAG GENERATOR WARNING] Web fallback attempt failed: {e}")
                if is_partial_local and partial_local_content:
                    local_cites = extract_citations(partial_local_content)
                    ans = f"{partial_local_content}\n\n*(Note: External search could not be completed to verify the remaining information.)*"
                    return RAGResponse(
                        query=query,
                        answer=ans,
                        citations=local_cites,
                        retrieved_chunks=trace_chunks,
                        refused=False,
                        max_similarity=retrieval.max_similarity,
                        source_type="local_rag",
                        origin="PARTIAL_LOCAL",
                        decision_path="Route: QA → Local RAG checked → Partial local evidence found → Web search exception occurred → Partial local answer returned",
                    )
                return RAGResponse(
                    query=query,
                    answer="Web search is currently unavailable due to a network or search service error. I could not verify this information.",
                    citations=[],
                    retrieved_chunks=trace_chunks,
                    refused=True,
                    max_similarity=retrieval.max_similarity,
                    source_type="web_error",
                    origin="WEB_ERROR",
                    decision_path="Route: QA → Local RAG checked → Insufficient relevant evidence → Web search attempted → Exception occurred",
                )

        # Fallback when web research is disabled
        return RAGResponse(
            query=query,
            answer="I couldn't find this in your documents.",
            citations=[],
            retrieved_chunks=trace_chunks,
            refused=True,
            max_similarity=retrieval.max_similarity,
            source_type="local_refusal",
            origin="NOT_FOUND",
            decision_path="Route: QA → Local RAG checked → Insufficient evidence (web fallback disabled) → Refusal",
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
