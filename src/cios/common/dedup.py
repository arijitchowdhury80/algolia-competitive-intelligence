"""Deterministic near-duplicate clustering.

Root-cause fix for the "same story repeated" class of bug: both the
synthesizer's within-run candidate list (same competitor, same underlying
event described twice) and the dashboard's cross-run competitor cards /
living theses (same story surfacing across several days' published deltas)
need the same test -- is this text describing the same thing as that text,
for the same subject?

Deliberately NOT an LLM call: a merge decision that changes what the reader
sees must be reproducible and auditable. Uses normalized token-set (Jaccard)
similarity over stdlib sets -- no external dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

# Same-story threshold. Chosen conservative: two sentences sharing most of
# their vocabulary (headline + what-changed) are almost always paraphrases
# of one event; below this, they are more often two distinct events about
# the same competitor and must stay separate cards/theses.
DEFAULT_SIMILARITY_THRESHOLD = 0.6

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalized_tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def token_set_similarity(a: str, b: str) -> float:
    """Same-story similarity over normalized token sets: the max of Jaccard
    and containment (overlap / smaller set). 0.0 if either side has no
    tokens (never treat two empty/unknown strings as duplicates of each
    other).

    Why containment too (2026-07-08 live-page regression): LLM paraphrases
    of one story often share a long verbatim core but one version adds a
    trailing sentence or swaps a word form ("rebrands" vs "brands"). Pure
    Jaccard punishes the length difference and scores such pairs ~0.5,
    below the same-story threshold; containment scores the shared core
    directly. Genuinely distinct stories about the same competitor measured
    <= 0.35 on both metrics against real production deltas."""
    ta, tb = normalized_tokens(a), normalized_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))
    return max(jaccard, containment)


T = TypeVar("T")


@dataclass
class DuplicateCluster(Generic[T]):
    """One merged group produced by cluster_by_similarity. `representative`
    is the first item that opened the cluster (input order); `members`
    includes it. Callers pick their own merge rule (e.g. highest
    materiality) over `members` -- this dataclass only records the grouping."""

    representative: T
    members: list[T] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.members)


def cluster_by_similarity(
    items: list[T],
    *,
    group_key: Callable[[T], object],
    text: Callable[[T], str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[DuplicateCluster[T]]:
    """Groups `items` sharing the same group_key(item) whose text() is a
    near-duplicate of an existing cluster's representative text
    (similarity >= threshold). Deterministic, single-pass, order-preserving:
    each item joins the first matching cluster it finds, else opens a new
    one. Items with different group_key() values never merge, regardless of
    text similarity (e.g. never merge two different competitors' stories).
    """
    clusters: list[DuplicateCluster[T]] = []
    for item in items:
        key = group_key(item)
        item_text = text(item)
        placed = False
        for cluster in clusters:
            if group_key(cluster.representative) != key:
                continue
            if token_set_similarity(item_text, text(cluster.representative)) >= threshold:
                cluster.members.append(item)
                placed = True
                break
        if not placed:
            clusters.append(DuplicateCluster(representative=item, members=[item]))
    return clusters
