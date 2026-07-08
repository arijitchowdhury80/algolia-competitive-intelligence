"""Signal-type classification and relevance scoring for executive statements.

Deterministic keyword heuristics only. LLM-based classification is Gate 4
brain territory (docs/planning/CI-OS-Fable-build-goal-spec.md) -- the
`SignalClassifier` Protocol below is the extension point: swap in an
LLM-backed implementation later without touching scanner.py.
"""

from __future__ import annotations

from typing import Protocol

from cios.execspeech.types import SignalType

# Longest/most specific phrase match wins within a category; category order
# below is also the tie-break order when multiple categories match (a
# statement mentioning both a competitor and a strategy pivot is filed as
# the strategy shift -- the stronger claim for a strategic thesis engine).
_KEYWORDS: dict[SignalType, tuple[str, ...]] = {
    SignalType.STRATEGY_SHIFT: (
        "pivot", "strategic shift", "shifting our strategy", "new strategy",
        "rethinking", "reposition", "double down", "refocus",
    ),
    SignalType.PRODUCT_DIRECTION: (
        "roadmap", "launching", "new product", "we are building",
        "we're building", "next generation", "coming release", "beta",
        "generally available", "ga next",
    ),
    SignalType.GTM_CHANGE: (
        "go-to-market", "gtm", "pricing model", "channel partner",
        "self-serve", "enterprise motion", "sales-led", "product-led",
    ),
    SignalType.COMPETITIVE_MENTION: (
        "competitor", "compared to", "unlike", "versus", "vs.",
        "in the market against",
    ),
    SignalType.HIRING_ORG: (
        "hiring", "headcount", "reorg", "restructuring", "new hire",
        "layoffs", "org chart", "appointed", "joins as",
    ),
}

# Classification order: first category with a keyword hit wins.
_CLASSIFICATION_ORDER: tuple[SignalType, ...] = (
    SignalType.STRATEGY_SHIFT,
    SignalType.PRODUCT_DIRECTION,
    SignalType.GTM_CHANGE,
    SignalType.COMPETITIVE_MENTION,
    SignalType.HIRING_ORG,
)


def classify_signal_type(text: str) -> SignalType:
    """Classify a quote/claim into a SignalType by keyword match.

    Returns SignalType.UNCLASSIFIED when nothing matches -- callers should
    not fabricate a category for an ambiguous statement.
    """
    lowered = text.lower()
    for signal_type in _CLASSIFICATION_ORDER:
        if any(kw in lowered for kw in _KEYWORDS[signal_type]):
            return signal_type
    return SignalType.UNCLASSIFIED


def score_relevance(text: str, signal_type: SignalType) -> float:
    """Deterministic relevance/confidence score in [0, 1].

    Heuristic: a classified signal starts at 0.5; each additional matched
    keyword (any category) adds 0.1, capped at 0.9. Unclassified statements
    score 0.2 -- they are evidence but weak signal for downstream synthesis.
    Never returns 1.0: that certainty is reserved for a human/LLM reviewer
    upgrade in Gate 4.
    """
    if signal_type is SignalType.UNCLASSIFIED:
        return 0.2

    lowered = text.lower()
    hits = sum(
        1
        for keywords in _KEYWORDS.values()
        for kw in keywords
        if kw in lowered
    )
    score = 0.5 + 0.1 * max(hits - 1, 0)
    return min(score, 0.9)


class SignalClassifier(Protocol):
    """Extension point for a smarter (e.g. LLM-backed, Gate 4) classifier.

    Implementations replace the deterministic heuristics above without
    changing scanner.py, which only depends on this Protocol shape.
    """

    def classify(self, text: str) -> tuple[SignalType, float]:
        """Return (signal_type, confidence) for a quote/claim string."""
        ...


class HeuristicClassifier:
    """Default SignalClassifier backed by classify_signal_type/score_relevance."""

    def classify(self, text: str) -> tuple[SignalType, float]:
        signal_type = classify_signal_type(text)
        return signal_type, score_relevance(text, signal_type)
