"""
News Evidence Collector - Evidence collection for news verification.
No LLM calls. Searches 20 trusted sources (see trusted_sources.py) for coverage of the
article's main claims and packages real, linkable articles as evidence.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.logging import get_logger
from backend.services.trusted_sources import SourceMatch, tokenize, trusted_source_search

logger = get_logger(__name__)

MAX_SEARCH_TERMS = 7
SUPPORT_RELEVANCE = 0.5


@dataclass
class EvidenceItem:
    """Structured evidence item."""
    url: str
    title: str
    publisher: str
    publication_date: str
    credibility_score: float
    summary: str
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    evidence_type: str = "news_source"
    metadata: Dict[str, Any] = field(default_factory=dict)


class NewsEvidenceCollector:
    """Collects evidence for an article's claims from trusted sources."""

    async def collect_evidence(
        self,
        claims: List[Dict],
        entities: Dict,
        content: str,
        source_url: Optional[str],
        input_type: str,
    ) -> Dict[str, Any]:
        """Search trusted sources and return a structured evidence package."""
        terms = self._search_terms(claims, entities, content)
        logger.info(f"[EvidenceCollector] Search terms: {terms}")

        if terms:
            result = await trusted_source_search.search(terms)
        else:
            result = {"terms": [], "matches": [], "coverage": [], "summary": {
                "sources_total": 20, "sources_reachable": 0, "sources_with_matches": 0,
                "articles_scanned": 0, "matches": 0, "gdelt_status": "skipped: no search terms"}}

        evidence = [self._to_evidence(m) for m in result["matches"]]
        supporting = [e for e, m in zip(evidence, result["matches"])
                      if not m.debunk_signal and m.relevance >= SUPPORT_RELEVANCE]
        contradicting = [e for e, m in zip(evidence, result["matches"]) if m.debunk_signal]

        logger.info(f"[EvidenceCollector] {len(evidence)} matches, {len(supporting)} supporting, "
                    f"{len(contradicting)} contradicting; {result['summary']}")
        return self._build_evidence_package(claims, entities, evidence, supporting, contradicting,
                                            result, source_url, content)

    def _search_terms(self, claims: List[Dict], entities: Dict, content: str) -> List[str]:
        """Pick the most specific words from the headline/first claims, names first."""
        text = " ".join(c.get("claim", "") for c in claims[:2]) or content[:400]
        tokens = tokenize(text)
        # Capitalized words in the original text are usually names, places or organizations
        proper = {w.lower() for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text)}
        for values in entities.values():
            if isinstance(values, list):
                for v in values:
                    proper.update(tokenize(str(v)))
        counts = Counter(tokens)
        ranked = sorted(dict.fromkeys(tokens), key=lambda t: (t not in proper, -counts[t], -len(t)))
        return ranked[:MAX_SEARCH_TERMS]

    @staticmethod
    def _to_evidence(m: SourceMatch) -> EvidenceItem:
        a = m.article
        return EvidenceItem(
            url=a.url,
            title=a.title,
            publisher=a.source.name,
            publication_date=a.published,
            credibility_score=a.source.credibility,
            summary=a.summary or a.title,
            evidence_type=a.source.category,
            metadata={
                "relevance": m.relevance,
                "matched_terms": m.matched_terms,
                "channel": a.channel,
                "debunk_signal": m.debunk_signal,
            },
        )

    def _build_evidence_package(
        self,
        claims: List[Dict],
        entities: Dict,
        evidence: List[EvidenceItem],
        supporting: List[EvidenceItem],
        contradicting: List[EvidenceItem],
        search: Dict[str, Any],
        source_url: Optional[str],
        content: str,
    ) -> Dict[str, Any]:
        """Build the final evidence package for reasoning."""
        summary = search["summary"]
        missing = []
        if not evidence:
            missing.append(
                f"None of the {summary['sources_total']} trusted sources covered these terms "
                f"({summary['sources_reachable']} reachable, {summary['articles_scanned']} articles scanned). "
                "RSS feeds cover recent days; older claims may need a manual search."
            )

        def avg(items: List[EvidenceItem]) -> float:
            return sum(e.credibility_score for e in items) / len(items) if items else 0

        return {
            "article": content[:5000],
            "claims": claims,
            "entities": entities,
            "timeline": [],
            "sources": [e.__dict__ for e in evidence[:20]],
            "supporting_evidence": [e.__dict__ for e in supporting[:10]],
            "contradicting_evidence": [e.__dict__ for e in contradicting[:10]],
            "missing_information": missing,
            "source_coverage": {**summary, "search_terms": search["terms"], "per_source": search["coverage"]},
            "metadata": {
                "source_url": source_url,
                "collection_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_evidence_items": len(evidence),
            },
            "image_analysis": {},
            "ocr_text": "",
            "credibility_scores": {
                "overall": avg(evidence) if evidence else 0.5,
                "supporting": avg(supporting),
                "contradicting": avg(contradicting),
            },
        }


# Global instance
news_evidence_collector = NewsEvidenceCollector()
