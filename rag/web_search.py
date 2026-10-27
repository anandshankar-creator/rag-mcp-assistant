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
3. If the provided web text does not contain sufficient reliable evidence to answer the question, explicitly state:
   "I couldn't verify this information from your documents or reliable external sources. I don't want to guess or provide potentially incorrect information."
4. Calendar Variations: For calendar-dependent events (such as Christmas celebrations), explain both the Gregorian calendar date (December 25) and Eastern Orthodox / Julian calendar date (January 7) if present in the context.
5. Conflicting Sources: If retrieved sources present conflicting information or differing dates/rules, explicitly explain the disagreement and cite which source supports each claim.
6. University & Official Regulations: For university regulations or policies (such as KTU schemes), distinguish between the original regulations and any subsequent amendments or revisions mentioned in the sources.
7. Do not speculate, invent, or extrapolate beyond the provided text.
8. Provide a direct, professional, concise explanation."""


STANDARD_REFUSAL = (
    "I couldn't verify this information from your documents or reliable external sources. "
    "I don't want to guess or provide potentially incorrect information."
)


class WebSearchEngine:
    """Manages web search queries, page text fetching, and grounded evidence synthesis."""

    def __init__(self, trust_ranker: Optional[DomainTrustRanker] = None, llm_client=None):
        self.ranker = trust_ranker or get_trust_ranker()
        self.llm = llm_client or get_llm_client()
        self.last_search_error: Optional[str] = None
        self.http_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    @staticmethod
    def rewrite_query_for_topic(query: str) -> str:
        """
        Optimizes search query keywords based on detected topic
        (KTU, programming, science, current affairs) to prioritize
        authoritative primary sources.
        """
        clean_q = query.strip()
        lower_q = clean_q.lower()

        # 1. KTU Academic Topic
        ktu_cues = ["ktu", "b.tech", "btech", "m.tech", "mtech", "kerala technological university", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
        if any(c in lower_q for c in ktu_cues):
            if "ktu" not in lower_q and "kerala technological university" not in lower_q:
                return f"KTU {clean_q}"
            return clean_q

        # 2. Programming & Technical Documentation
        programming_cues = [
            "python", "java", "c++", "golang", "rust", "javascript", "typescript",
            "docker", "kubernetes", "git", "asyncio", "decorator", "algorithm",
            "data structure", "quicksort", "sql", "sqlite"
        ]
        if any(c in lower_q for c in programming_cues):
            if not any(k in lower_q for k in ["docs", "documentation", "tutorial", "reference"]):
                return f"{clean_q} official documentation"
            return clean_q

        return clean_q

    def search(
        self,
        query: str,
        max_results: int = 5,
        min_trust: float = 0.40,
    ) -> List[Dict[str, Any]]:
        """
        Executes free DuckDuckGo web search and ranks results by domain credibility.
        """
        self.last_search_error = None
        raw_results: List[Dict[str, Any]] = []
        search_query = self.rewrite_query_for_topic(query)
        try:
            ddgs_client = DDGS()
            # Fetch slightly more raw items to allow trust filtering
            fetch_count = min(max_results * 3, 15)
            generator = ddgs_client.text(search_query, max_results=fetch_count)
            if generator:
                raw_results = list(generator)
        except Exception as e:
            self.last_search_error = str(e)
            print(f"[WEB SEARCH ERROR] Search request failed for '{search_query}': {e}")
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
        self.last_search_error = None
        try:
            ranked_results = self.search(query, max_results=4, min_trust=0.45)
        except Exception as e:
            return {
                "success": False,
                "answer": "Web search is currently unavailable due to a network or search service error. I could not verify this information.",
                "citations": [],
                "sources": [],
                "source_type": "web_error",
                "error": True,
            }

        if self.last_search_error:
            return {
                "success": False,
                "answer": "Web search is currently unavailable due to a network or search service error. I could not verify this information.",
                "citations": [],
                "sources": [],
                "source_type": "web_error",
                "error": True,
            }

        if not ranked_results:
            return {
                "success": False,
                "answer": STANDARD_REFUSAL,
                "citations": [],
                "sources": [],
                "source_type": "web_refusal",
                "error": False,
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
                "answer": STANDARD_REFUSAL,
                "citations": [],
                "sources": ranked_results,
                "source_type": "web_refusal",
                "error": False,
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

        refusal_patterns = [
            "couldn't verify", "could not verify",
            "don't want to guess", "do not want to guess",
            "cannot be verified", "can't be verified",
            "does not contain", "cannot answer",
            "not enough information", "insufficient information",
        ]
        is_refusal = any(p in raw_answer.lower() for p in refusal_patterns)
        if is_refusal:
            raw_answer = STANDARD_REFUSAL

        # Quote verification in code: extract candidate quotes and verify presence in fetched text
        raw_quotes = re.findall(r'"([^"\n]{10,})"', raw_answer)
        verified_quotes = []
        if not is_refusal:
            for q in raw_quotes:
                clean_q = re.sub(r"\s+", " ", q.strip())
                if clean_q.lower() in combined_context.lower():
                    verified_quotes.append(clean_q)

        tiers = [
            {
                "domain": r.get("domain", ""),
                "tier": r.get("tier", "Tier 3"),
                "score": r.get("trust_score", 0.5),
                "url": r.get("href") or r.get("url", ""),
            }
            for r in ranked_results[:3]
        ]

        return {
            "success": not is_refusal,
            "answer": raw_answer,
            "citations": [] if is_refusal else valid_citations,
            "sources": ranked_results,
            "source_type": "web_refusal" if is_refusal else "web",
            "tiers": tiers,
            "verified_quotes": verified_quotes,
            "urls": [] if is_refusal else valid_citations,
            "error": False,
        }


# Global singleton engine
_engine_instance: Optional[WebSearchEngine] = None


def get_web_search_engine() -> WebSearchEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = WebSearchEngine()
    return _engine_instance
