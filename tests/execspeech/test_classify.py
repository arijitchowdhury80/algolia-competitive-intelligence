"""Classification-path tests for classify.py heuristics."""

from __future__ import annotations

from cios.execspeech.classify import (
    HeuristicClassifier,
    classify_signal_type,
    score_relevance,
)
from cios.execspeech.types import SignalType


def test_classifies_strategy_shift() -> None:
    assert classify_signal_type(
        "We are pivoting our strategy toward AI-native search."
    ) is SignalType.STRATEGY_SHIFT


def test_classifies_product_direction() -> None:
    assert classify_signal_type(
        "Our roadmap includes a new product launching next quarter."
    ) is SignalType.PRODUCT_DIRECTION


def test_classifies_gtm_change() -> None:
    assert classify_signal_type(
        "We're moving to a product-led go-to-market motion."
    ) is SignalType.GTM_CHANGE


def test_classifies_competitive_mention() -> None:
    assert classify_signal_type(
        "Unlike our competitor, we ship weekly."
    ) is SignalType.COMPETITIVE_MENTION


def test_classifies_hiring_org() -> None:
    assert classify_signal_type(
        "We are hiring aggressively and growing headcount."
    ) is SignalType.HIRING_ORG


def test_unclassified_when_no_keywords_match() -> None:
    assert classify_signal_type(
        "It was a sunny day at the conference."
    ) is SignalType.UNCLASSIFIED


def test_unclassified_scores_low_confidence() -> None:
    assert score_relevance("sunny day", SignalType.UNCLASSIFIED) == 0.2


def test_classified_scores_at_least_baseline() -> None:
    score = score_relevance("We are pivoting our strategy.", SignalType.STRATEGY_SHIFT)
    assert 0.5 <= score <= 0.9


def test_heuristic_classifier_returns_type_and_confidence() -> None:
    classifier = HeuristicClassifier()
    signal_type, confidence = classifier.classify(
        "We are pivoting our strategy and launching a new product."
    )
    assert signal_type is SignalType.STRATEGY_SHIFT
    assert 0.0 <= confidence <= 1.0
