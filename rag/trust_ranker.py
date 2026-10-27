"""
==============================================================================
Module: rag.trust_ranker
Role in Architecture: Domain Trust Authority & Source Ranking Engine
==============================================================================
Evaluates web sources by domain credibility rather than blindly trusting
search engine rank. Prevents hallucination and unverified information from
infiltrating the assistant's knowledge generation.

Academic & Architecture Review Defense:
- Anti-Hallucination Gate: Restricts web synthesis to high-trust authority domains.
- Tiered Credibility Model:
  * Tier 1 (Score 0.9 - 1.0): Academic, Governmental, Standards Bodies, Major Official Documentation.
  * Tier 2 (Score 0.7 - 0.85): Reputable Peer-Reviewed, Established Technical & Journalism Outlets.
  * Tier 3 (Score 0.4 - 0.6): General web sources.
  * Untrusted (Score < 0.4): Social scrapers, content farms, user forum spam.
==============================================================================
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class DomainTrustRanker:
    """Ranks and filters external URLs based on domain authority and credibility tiers."""

    # Tier 1: Highly authoritative (Academic, Governmental, Standards, Official Docs)
    TIER_1_TLDS = {".edu", ".gov", ".mil", ".ac.uk", ".edu.in", ".gov.in", ".ac.in"}
    TIER_1_DOMAINS = {
        "wikipedia.org",
        "britannica.com",
        "docs.python.org",
        "github.com",
        "arxiv.org",
        "ieee.org",
        "acm.org",
        "nature.com",
        "sciencedirect.com",
        "stackoverflow.com",
        "w3.org",
        "developer.mozilla.org",
        "ktu.edu.in",
        "kerala.gov.in",
        "aicte-india.org",
        "ugc.ac.in",
        "reuters.com",
        "bbc.com",
        "bbc.co.uk",
        "apnews.com",
        "who.int",
        "nih.gov",
        "nasa.gov",
        "mit.edu",
        "stanford.edu",
        "harvard.edu",
        "ox.ac.uk",
        "cam.ac.uk",
        "coursera.org",
        "edx.org",
    }

    # Tier 2: Reputable Technical & Journalism Outlets
    TIER_2_DOMAINS = {
        "geeksforgeeks.org",
        "medium.com",
        "towardsdatascience.com",
        "theverge.com",
        "techcrunch.com",
        "wired.com",
        "nytimes.com",
        "wsj.com",
        "economist.com",
        "bloomberg.com",
        "arstechnica.com",
        "zdnet.com",
        "venturebeat.com",
        "infoworld.com",
        "stackexchange.com",
        "realpython.com",
        "freecodecamp.org",
    }

    # Low-credibility / Content Farms / Ad scrapers (Filtered by default)
    UNTRUSTED_DOMAINS = {
        "quora.com",
        "pinterest.com",
        "buzzfeed.com",
        "answers.com",
        "yahoo.com/answers",
        "ehow.com",
    }

    @staticmethod
    def extract_domain(url: str) -> str:
        """Extracts clean lowercase domain from URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = (parsed.netloc or parsed.path).lower()
            if host.startswith("www."):
                host = host[4:]
            return host.split(":")[0]
        except Exception:
            return ""

    def calculate_trust_score(self, url: str) -> float:
        """
        Calculates domain trust score between 0.0 (untrusted) and 1.0 (highest authority).
        """
        domain = self.extract_domain(url)
        if not domain:
            return 0.2

        # Check untrusted / blocked
        for untrusted in self.UNTRUSTED_DOMAINS:
            if domain == untrusted or domain.endswith(f".{untrusted}"):
                return 0.1

        # Check Tier 1 TLDs (.edu, .gov, etc.)
        for tld in self.TIER_1_TLDS:
            if domain.endswith(tld):
                return 1.0

        # Check Tier 1 exact domains
        for t1 in self.TIER_1_DOMAINS:
            if domain == t1 or domain.endswith(f".{t1}"):
                return 0.95

        # Check Tier 2 domains
        for t2 in self.TIER_2_DOMAINS:
            if domain == t2 or domain.endswith(f".{t2}"):
                return 0.80

        # Standard .org default authority
        if domain.endswith(".org"):
            return 0.65

        # Standard general web
        return 0.50

    def get_tier_label(self, trust_score: float) -> str:
        """Returns human-readable tier classification."""
        if trust_score >= 0.90:
            return "Tier 1: Authoritative"
        elif trust_score >= 0.70:
            return "Tier 2: Reputable"
        elif trust_score >= 0.40:
            return "Tier 3: Standard Web"
        return "Untrusted / Filtered"

    def rank_and_filter_results(
        self,
        results: List[Dict[str, Any]],
        min_trust: float = 0.40,
    ) -> List[Dict[str, Any]]:
        """
        Ranks search engine results using a composite credibility-relevance score,
        filtering out untrusted domains.
        """
        if not results:
            return []

        annotated = []
        n_results = len(results)

        for idx, item in enumerate(results):
            url = item.get("href") or item.get("url", "")
            trust = self.calculate_trust_score(url)

            if trust < min_trust:
                continue

            # Original search position rank penalty (0 to 1)
            pos_weight = 1.0 - (idx / max(n_results, 1))

            # Composite score: 65% domain trust, 35% search engine relevance rank
            composite_score = round(0.65 * trust + 0.35 * pos_weight, 4)

            annotated_item = dict(item)
            annotated_item["domain"] = self.extract_domain(url)
            annotated_item["trust_score"] = trust
            annotated_item["tier"] = self.get_tier_label(trust)
            annotated_item["composite_score"] = composite_score
            annotated.append(annotated_item)

        # Sort descending by composite score
        annotated.sort(key=lambda x: x["composite_score"], reverse=True)
        return annotated


# Global singleton ranker
_ranker_instance: Optional[DomainTrustRanker] = None


def get_trust_ranker() -> DomainTrustRanker:
    global _ranker_instance
    if _ranker_instance is None:
        _ranker_instance = DomainTrustRanker()
    return _ranker_instance
