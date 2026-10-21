"""
Trusted Sources
Searches 20 trusted news, fact-checking and official sources for coverage of a claim.

Two free channels, no API keys:
- RSS feeds published by the sources themselves (recent articles, ~days).
- GDELT DOC 2.0 search restricted to the trusted domains (articles from the last ~3 months).
  GDELT allows one request every 5 seconds, so calls are throttled and cached.

Matching is keyword-based on headlines and summaries: a match means a trusted source
covered the same topic, not that it confirms every detail of the claim.
"""

from __future__ import annotations

import asyncio
import html
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from backend.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; VisionX-NewsVerifier/1.0)"
FEED_TTL_SECONDS = 600
GDELT_MIN_INTERVAL = 5.5
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


@dataclass(frozen=True)
class TrustedSource:
    name: str
    domains: Tuple[str, ...]
    category: str  # wire | broadcaster | newspaper | fact_check | official | science
    credibility: float
    rss: Optional[str] = None


TRUSTED_SOURCES: Tuple[TrustedSource, ...] = (
    # Wire services (no public RSS: searched through GDELT)
    TrustedSource("Reuters", ("reuters.com",), "wire", 0.95),
    TrustedSource("Associated Press", ("apnews.com",), "wire", 0.95),
    # Public broadcasters
    TrustedSource("BBC News", ("bbc.com", "bbc.co.uk"), "broadcaster", 0.92, "https://feeds.bbci.co.uk/news/rss.xml"),
    TrustedSource("NPR", ("npr.org",), "broadcaster", 0.9, "https://feeds.npr.org/1001/rss.xml"),
    TrustedSource("PBS NewsHour", ("pbs.org",), "broadcaster", 0.9, "https://www.pbs.org/newshour/feeds/rss/headlines"),
    TrustedSource("Deutsche Welle", ("dw.com",), "broadcaster", 0.88, "https://rss.dw.com/rdf/rss-en-all"),
    TrustedSource("France 24", ("france24.com",), "broadcaster", 0.87, "https://www.france24.com/en/rss"),
    TrustedSource("CBC News", ("cbc.ca",), "broadcaster", 0.88, "https://www.cbc.ca/webfeed/rss/rss-topstories"),
    TrustedSource("ABC News Australia", ("abc.net.au",), "broadcaster", 0.88, "https://www.abc.net.au/news/feed/51120/rss.xml"),
    TrustedSource("Al Jazeera", ("aljazeera.com",), "broadcaster", 0.85, "https://www.aljazeera.com/xml/rss/all.xml"),
    # Newspapers
    TrustedSource("The Guardian", ("theguardian.com",), "newspaper", 0.87, "https://www.theguardian.com/world/rss"),
    TrustedSource("The New York Times", ("nytimes.com",), "newspaper", 0.88, "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    TrustedSource("The Hindu", ("thehindu.com",), "newspaper", 0.84, "https://www.thehindu.com/news/international/feeder/default.rss"),
    TrustedSource("The Kathmandu Post", ("kathmandupost.com",), "newspaper", 0.82, "https://kathmandupost.com/rss"),
    # Fact-checkers
    TrustedSource("Snopes", ("snopes.com",), "fact_check", 0.88, "https://www.snopes.com/feed/"),
    TrustedSource("FactCheck.org", ("factcheck.org",), "fact_check", 0.9, "https://www.factcheck.org/feed/"),
    # Official and scientific bodies
    TrustedSource("World Health Organization", ("who.int",), "official", 0.95, "https://www.who.int/rss-feeds/news-english.xml"),
    TrustedSource("UN News", ("news.un.org", "un.org"), "official", 0.93, "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
    TrustedSource("NASA", ("nasa.gov",), "official", 0.95, "https://www.nasa.gov/news-release/feed/"),
    TrustedSource("ScienceDaily", ("sciencedaily.com",), "science", 0.82, "https://www.sciencedaily.com/rss/all.xml"),
)

assert len(TRUSTED_SOURCES) == 20

# Searched through GDELT: sources without a public feed, plus fact-checkers for older claims
GDELT_DOMAINS = ("reuters.com", "apnews.com", "snopes.com", "factcheck.org", "bbc.co.uk")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "can", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "that", "this", "these", "those",
    "it", "its", "their", "they", "them", "he", "she", "his", "her", "we", "our", "you", "your", "not", "no",
    "said", "says", "say", "new", "after", "before", "about", "over", "more", "than", "also", "who", "what",
    "when", "where", "why", "how", "which", "all", "any", "some", "just", "now", "out", "up", "one", "two",
}
_DEBUNK_WORDS = ("false", "fake", "hoax", "misleading", "debunk", "no evidence", "fabricated", "doctored",
                 "not true", "untrue", "baseless", "conspiracy", "fact check", "fact-check", "satire")


@dataclass
class Article:
    source: TrustedSource
    title: str
    url: str
    published: str = ""
    summary: str = ""
    channel: str = "rss"  # rss | gdelt


@dataclass
class SourceMatch:
    article: Article
    relevance: float
    matched_terms: List[str] = field(default_factory=list)
    debunk_signal: bool = False


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'\-]*", text.lower())
    return [w.strip("'-") for w in words if len(w) > 2 and w not in _STOPWORDS]


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def _iso(date_text: str) -> str:
    if not date_text:
        return ""
    try:
        return parsedate_to_datetime(date_text).isoformat()
    except (TypeError, ValueError):
        return date_text.strip()


def _source_for_url(url: str) -> Optional[TrustedSource]:
    host = (urlparse(url).hostname or "").lower()
    for src in TRUSTED_SOURCES:
        if any(host == d or host.endswith("." + d) for d in src.domains):
            return src
    return None


def parse_feed(xml_data: bytes | str, source: TrustedSource) -> List[Article]:
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom into articles.

    Pass raw bytes so the parser honours the feed's declared encoding.
    """
    try:
        root = ET.fromstring(xml_data.encode("utf-8") if isinstance(xml_data, str) else xml_data)
    except ET.ParseError:
        return []
    articles: List[Article] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        fields: Dict[str, str] = {}
        for child in el:
            ctag = child.tag.rsplit("}", 1)[-1]
            if ctag == "link" and child.get("href"):
                fields.setdefault("link", child.get("href", ""))
            elif child.text:
                fields.setdefault(ctag, child.text.strip())
        title = _strip_html(fields.get("title", ""))
        link = fields.get("link", "") or fields.get("guid", "")
        if not title or not link.startswith("http"):
            continue
        articles.append(Article(
            source=source,
            title=title,
            url=link,
            published=_iso(fields.get("pubDate") or fields.get("date") or fields.get("published") or fields.get("updated", "")),
            summary=_strip_html(fields.get("description") or fields.get("summary") or "")[:400],
        ))
    return articles


class TrustedSourceSearch:
    """Searches the trusted sources; feed and GDELT results are cached briefly."""

    def __init__(self) -> None:
        self._feed_cache: Dict[str, Tuple[float, List[Article]]] = {}
        self._gdelt_cache: Dict[str, Tuple[float, List[Article]]] = {}
        self._gdelt_lock = asyncio.Lock()
        self._gdelt_last_call = 0.0

    async def _fetch_feed(self, client: httpx.AsyncClient, src: TrustedSource) -> Tuple[TrustedSource, List[Article], Optional[str]]:
        cached = self._feed_cache.get(src.name)
        if cached and time.time() - cached[0] < FEED_TTL_SECONDS:
            return src, cached[1], None
        try:
            resp = await client.get(src.rss)
            resp.raise_for_status()
            articles = parse_feed(resp.content, src)
            self._feed_cache[src.name] = (time.time(), articles)
            return src, articles, None
        except Exception as exc:
            return src, [], f"{type(exc).__name__}"

    async def _gdelt_search(self, client: httpx.AsyncClient, terms: List[str]) -> Tuple[List[Article], Optional[str]]:
        if not terms:
            return [], "no search terms"
        phrase = " ".join(terms[:4])
        cache_key = phrase.lower()
        cached = self._gdelt_cache.get(cache_key)
        if cached and time.time() - cached[0] < FEED_TTL_SECONDS:
            return cached[1], None

        # GDELT rejects long OR-lists; RSS already covers the other sources
        query = f"{phrase} ({' OR '.join('domain:' + d for d in GDELT_DOMAINS)})"
        params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": "75",
                  "timespan": "3months", "sort": "HybridRel"}

        async with self._gdelt_lock:
            for attempt in range(2):
                wait = GDELT_MIN_INTERVAL - (time.time() - self._gdelt_last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._gdelt_last_call = time.time()
                try:
                    resp = await client.get(GDELT_URL, params=params, timeout=25)
                except Exception as exc:
                    return [], f"{type(exc).__name__}"
                if resp.status_code == 429 and attempt == 0:
                    continue
                if resp.status_code != 200:
                    return [], f"HTTP {resp.status_code}"
                try:
                    data = resp.json()
                except ValueError:
                    # GDELT answers plain text for malformed/too-short queries
                    return [], resp.text[:80].strip() or "invalid response"
                break
            else:
                return [], "rate limited"

        articles = []
        for item in data.get("articles", []):
            src = _source_for_url(item.get("url", ""))
            if not src:
                continue
            seen = item.get("seendate", "")
            published = f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}T{seen[9:11]}:{seen[11:13]}:00Z" if len(seen) >= 15 else seen
            articles.append(Article(source=src, title=_strip_html(item.get("title", "")), url=item["url"],
                                    published=published, channel="gdelt"))
        self._gdelt_cache[cache_key] = (time.time(), articles)
        return articles, None

    @staticmethod
    def score(article: Article, terms: List[str], weights: Optional[Dict[str, float]] = None) -> SourceMatch:
        """Relevance = share of the claim's term weight found in the article.

        Rare terms (e.g. names) weigh more than common ones (e.g. "scientists").
        """
        text = f"{article.title} {article.summary}".lower()
        tokens = set(tokenize(text))
        matched = [t for t in terms if t in tokens or (" " in t and t in text)]
        weights = weights or {}
        total = sum(weights.get(t, 1.0) for t in terms) or 1.0
        relevance = sum(weights.get(t, 1.0) for t in matched) / total
        debunk = article.source.category == "fact_check" or any(w in text for w in _DEBUNK_WORDS)
        return SourceMatch(article=article, relevance=round(relevance, 3), matched_terms=matched,
                           debunk_signal=debunk and any(w in text for w in _DEBUNK_WORDS))

    async def search(self, terms: List[str], min_matches: int = 2, min_relevance: float = 0.5,
                     limit: int = 25) -> Dict[str, Any]:
        """Search all 20 sources for articles sharing the given key terms.

        Returns matches (best first) and a per-source coverage report.
        """
        terms = [t.lower() for t in dict.fromkeys(terms) if t]
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            feed_tasks = [self._fetch_feed(client, s) for s in TRUSTED_SOURCES if s.rss]
            feed_results, (gdelt_articles, gdelt_error) = await asyncio.gather(
                asyncio.gather(*feed_tasks), self._gdelt_search(client, terms))

        coverage: Dict[str, Dict[str, Any]] = {
            s.name: {"source": s.name, "category": s.category, "credibility": s.credibility,
                     "channels": [], "articles_scanned": 0, "matches": 0, "errors": []}
            for s in TRUSTED_SOURCES
        }
        articles: List[Article] = []
        for src, items, err in feed_results:
            entry = coverage[src.name]
            entry["channels"].append("rss")
            entry["articles_scanned"] += len(items)
            if err:
                entry["errors"].append(f"rss: {err}")
            articles.extend(items)
        for s in TRUSTED_SOURCES:
            if any(d in GDELT_DOMAINS for d in s.domains):
                coverage[s.name]["channels"].append("gdelt")
                if gdelt_error:
                    coverage[s.name]["errors"].append(f"gdelt: {gdelt_error}")
        for a in gdelt_articles:
            coverage[a.source.name]["articles_scanned"] += 1
        articles.extend(gdelt_articles)

        # Inverse document frequency over everything scanned: common words count less
        n_docs = max(len(articles), 1)
        doc_tokens = [set(tokenize(f"{a.title} {a.summary}")) for a in articles]
        weights = {t: math.log((n_docs + 1) / (1 + sum(1 for d in doc_tokens if t in d))) + 1.0 for t in terms}

        need = min(min_matches, max(len(terms), 1))
        seen_urls = set()
        matches: List[SourceMatch] = []
        for art in articles:
            if art.url in seen_urls:
                continue
            seen_urls.add(art.url)
            m = self.score(art, terms, weights)
            # GDELT already filtered by the query terms, so its results need less local evidence
            if art.channel == "gdelt":
                keep = len(m.matched_terms) >= 1
            else:
                keep = len(m.matched_terms) >= need and m.relevance >= min_relevance
            if keep:
                matches.append(m)
        matches.sort(key=lambda m: (m.relevance, m.article.source.credibility), reverse=True)
        matches = matches[:limit]
        for m in matches:
            coverage[m.article.source.name]["matches"] += 1

        reachable = sum(1 for c in coverage.values() if c["articles_scanned"] > 0 or not c["errors"])
        logger.info(f"[TrustedSources] terms={terms[:6]} scanned={len(articles)} matches={len(matches)} "
                    f"gdelt={'error: ' + gdelt_error if gdelt_error else len(gdelt_articles)}")
        return {
            "terms": terms,
            "matches": matches,
            "coverage": list(coverage.values()),
            "summary": {
                "sources_total": len(TRUSTED_SOURCES),
                "sources_reachable": reachable,
                "sources_with_matches": sum(1 for c in coverage.values() if c["matches"]),
                "articles_scanned": len(articles),
                "matches": len(matches),
                "gdelt_status": gdelt_error or "ok",
            },
        }


trusted_source_search = TrustedSourceSearch()
