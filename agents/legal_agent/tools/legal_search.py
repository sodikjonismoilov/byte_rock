from __future__ import annotations

import json
import hashlib
import re
from functools import lru_cache
from pathlib import Path

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import LegalSource, LegalSourceHit
else:
    from models.schemas import LegalSource, LegalSourceHit

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "legal_sources.json"
_TOKEN_RE = re.compile(r"[a-z0-9§.-]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text) if len(token) > 1]


@lru_cache(maxsize=1)
def load_legal_sources(path: str | None = None) -> list[LegalSource]:
    source_path = Path(path) if path else DATA_PATH
    with source_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    sources=[LegalSource.model_validate(item) for item in payload]
    for source in sources:
        expected=source.excerpt_provenance.get('excerpt_sha256')
        if expected and (not source.excerpt or hashlib.sha256(source.excerpt.encode()).hexdigest()!=expected):
            raise ValueError('Legal authority excerpt hash mismatch')
    return sources


class LegalSearchTool:
    """Keyword retrieval over the curated local legal-source catalog."""

    def __init__(self, sources: list[LegalSource] | None = None, path: str | None = None):
        self.sources = [source.model_copy(deep=True) for source in (sources if sources is not None else load_legal_sources(path))]

    def search(self, query: str, limit: int = 5) -> list[LegalSourceHit]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        hits: list[LegalSourceHit] = []
        for source in self.sources:
            # Topic boundaries prevent a generic shared word from substituting unrelated guidance.
            if source.id=='hpd-heat-hot-water' and re.search(r'litigation|court|eviction',query,re.I) and not re.search(r'heat|hot water',query,re.I):continue
            if source.id=='dob-boilers' and re.search(r'permit|demolition|construction',query,re.I) and not re.search(r'boiler',query,re.I):continue
            haystack = " ".join(
                [
                    source.title,
                    source.identifier,
                    source.summary,
                    source.excerpt or "",
                    " ".join(source.topics),
                ]
            )
            hay_tokens = set(_tokenize(haystack))
            matched = sorted(query_tokens & hay_tokens)
            topic_bonus = sum(1 for topic in source.topics if topic.lower() in query.lower())
            score = float(len(matched) + (2 * topic_bonus))
            if source.identifier.lower() in query.lower():
                score += 3
            if score <= 0:
                continue
            hits.append(LegalSourceHit(source=source, score=score, matched_terms=matched))

        hits.sort(key=lambda hit: (-hit.score, hit.source.id))
        return hits[:limit]


def search_legal_sources(query: str, limit: int = 5) -> list[LegalSourceHit]:
    return LegalSearchTool().search(query, limit=limit)
