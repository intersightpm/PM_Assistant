from __future__ import annotations

import re
from hashlib import sha1

from .models import Evidence, FeatureConfig


def text_matches_feature(text: str, config: FeatureConfig) -> bool:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return False
    if any(" ".join(term.lower().split()) in lowered for term in config.exclude_terms):
        return False
    if any(term in lowered for term in config.anchor_terms()):
        return True
    if config.related_terms_match_without_feature:
        related_terms = [" ".join(str(term).strip().lower().split()) for term in config.related_terms]
        return any(term and term in lowered for term in related_terms)
    return False


def filter_evidence(items: list[Evidence], config: FeatureConfig) -> list[Evidence]:
    return [item for item in items if text_matches_feature(f"{item.title}\n{item.text}", config)]


def dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[str] = set()
    unique: list[Evidence] = []
    for item in items:
        compact = re.sub(r"\W+", "", f"{item.source}:{item.requester}:{item.title}:{item.text}".lower())[:260]
        key = sha1(compact.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def score_text(query: str, item: Evidence) -> int:
    query_terms = [term for term in re.split(r"\W+", query.lower()) if term]
    haystack = f"{item.title} {item.text} {item.requester} {item.author}".lower()
    return sum(haystack.count(term) for term in query_terms)
