"""
==============================================================================
Module: rag.web_search
Role in Architecture: Grounded Web Fallback & Live Research Engine
==============================================================================
Provides verifiable, cost-free web search and page text extraction when local
knowledge is insufficient or misses the similarity threshold.

Key Architectural Guarantees:
1. Free & Resilient: Uses `ddgs` (DuckDuckGo Search) without external API keys.
2. Trust-Ranked: Only pulls and prioritizes domains verified by `DomainTrustRanker`.
3. Grounded Synthesis: Prompts LLM to answer strictly from fetched page text.
4. Verified Citations: Enforces clickable URL citations matching verified source pages.
==============================================================================
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.config import settings
from llm import get_llm_client, LLMResponse
from rag.trust_ranker import get_trust_ranker, DomainTrustRanker


WEB_GROUNDING_PROMPT = """You are a strict, evidence-grounded research assistant.
Answer the user's question using ONLY the provided web page excerpts below.

Mandatory Rules:
1. Answer strictly using factual claims supported by the provided text.
2. Cite the source URL for every claim as [URL] (e.g. [https://docs.python.org/]).
3. If the provided web text does not contain the answer, explicitly state:
   "I couldn't verify this information from trusted web sources."
4. Do not speculate, invent, or extrapolate beyond the provided text.
5. Provide a direct, professional, concise explanation."""


class WebSearchEngine:
    """Manages web search queries, page text fetching, and grounded evidence synthesis."""

    def __init__(self, trust_ranker: Optional[DomainTrustRanker] = None, llm_client=None):
        self.ranker = trust_ranker or get_trust_ranker()
        self.llm = llm_client or get_llm_client()
        self.http_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def search(
        self,
        query: str,
        max_results: int = 5,
        min_trust: float = 0.40,
    ) -> List[Dict[str, Any]]:
        """
        Executes free DuckDuckGo web search and ranks results by domain credibility.
        """
        raw_results: List[Dict[str, Any]] = []
        try:
            ddgs_client = DDGS()
            # Fetch slightly more raw items to allow trust filtering
            fetch_count = min(max_results * 3, 15)
            generator = ddgs_client.text(query, max_results=fetch_count)
            if generator:
                raw_results = list(generator)
        except Exception as e:
            print(f"[WEB SEARCH ERROR] Search request failed for '{query}': {e}")
            return []

        # Filter & rank by trust authority
        ranked = self.ranker.rank_and_filter_results(raw_results, min_trust=min_trust)
        return ranked[:max_results]

    def fetch_page_content(self, url: str, timeout: int = 6) -> str:
        """
        Retrieves and cleans plain readable text from an external web page.
        """
        if not url:
            return ""

        try:
            with httpx.Client(headers=self.http_headers, timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return ""

                # Parse and clean HTML
                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove non-content tags
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                    tag.decompose()

                # Extract paragraph and body text
                paragraphs = soup.find_all(["p", "article", "section"])
                if paragraphs:
                    text_parts = [p.get_text(separator=" ", strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40]
                    clean_text = " ".join(text_parts)
                else:
                    clean_text = soup.get_text(separator=" ", strip=True)

                # Collapse redundant whitespace
                clean_text = re.sub(r"\s+", " ", clean_text).strip()
                # Return top 2000 chars of relevant page content
                return clean_text[:2000]

        except Exception as e:
            print(f"[WEB FETCH WARNING] Could not fetch page '{url}': {e}")
            return ""

    def research_and_answer(self, query: str) -> Dict[str, Any]:
        """
        End-to-end fallback: searches web, scrapes top trusted pages,
        and generates a strictly grounded answer with URL citations.
        """
        ranked_results = self.search(query, max_results=4, min_trust=0.45)

        if not ranked_results:
            return {
                "success": False,
                "answer": "I couldn't find verified, trusted web sources for this query.",
                "citations": [],
                "sources": [],
                "source_type": "web_refusal",
            }

        # Fetch contents for top trusted sources
        context_blocks = []
        fetched_urls = []

        for item in ranked_results[:3]:
            url = item.get("href") or item.get("url", "")
            title = item.get("title", "Web Source")
            tier = item.get("tier", "Web Source")
            snippet = item.get("body", "")

            # Attempt live page fetch; fallback to search snippet if network fails
            page_text = self.fetch_page_content(url)
            content = page_text if len(page_text) > 100 else snippet

            if content:
                context_blocks.append(
                    f"--- SOURCE: {title} [URL: {url}] (Credibility: {tier}) ---\n"
                    f"{content}\n"
                )
                fetched_urls.append(url)

        if not context_blocks:
            return {
                "success": False,
                "answer": "I retrieved web search results, but could not safely extract page content.",
                "citations": [],
                "sources": ranked_results,
                "source_type": "web_refusal",
            }

        combined_context = "\n".join(context_blocks)
        user_prompt = f"VERIFIED WEB CONTEXT:\n{combined_context}\n\nQUESTION: {query}"

        messages = [
            {"role": "system", "content": WEB_GROUNDING_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        resp: LLMResponse = self.llm.generate(messages, temperature=0.1)
        raw_answer = resp.content.strip()

        # Extract and verify citations
        extracted_urls = re.findall(r"\[(https?://[^\s\]]+)\]", raw_answer)
        valid_citations = []
        for u in extracted_urls:
            # Normalize trailing punctuation
            u_clean = u.rstrip(".,;)")
            if any(u_clean.startswith(f) or f.startswith(u_clean) for f in fetched_urls):
                if u_clean not in valid_citations:
                    valid_citations.append(u_clean)

        # If LLM cited nothing but answered, attach the top verified source URL
        if not valid_citations and fetched_urls:
            valid_citations.append(fetched_urls[0])

        is_refusal = (
            "couldn't verify" in raw_answer.lower()
            or "could not verify" in raw_answer.lower()
            or "does not contain" in raw_answer.lower()
        )

        return {
            "success": not is_refusal,
            "answer": raw_answer,
            "citations": valid_citations,
            "sources": ranked_results,
            "source_type": "web",
        }


# Global singleton engine
_engine_instance: Optional[WebSearchEngine] = None


def get_web_search_engine() -> WebSearchEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = WebSearchEngine()
    return _engine_instance
