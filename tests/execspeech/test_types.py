"""Evidence-rule tests for SpeechSignal (types.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cios.execspeech.types import SpeechSignal


def test_signal_requires_quote() -> None:
    with pytest.raises(ValidationError):
        SpeechSignal(
            tenant_id=1,
            competitor_id=1,
            source_url="https://example.com/interview",
            quote=None,
        )


def test_signal_requires_nonblank_quote() -> None:
    with pytest.raises(ValidationError):
        SpeechSignal(
            tenant_id=1,
            competitor_id=1,
            source_url="https://example.com/interview",
            quote="   ",
        )


def test_signal_requires_source_url() -> None:
    with pytest.raises(ValidationError):
        SpeechSignal(
            tenant_id=1,
            competitor_id=1,
            source_url="",
            quote="We are pivoting our strategy.",
        )


def test_signal_valid_with_quote_and_url() -> None:
    signal = SpeechSignal(
        tenant_id=1,
        competitor_id=1,
        source_url="https://example.com/interview",
        quote="We are pivoting our strategy.",
    )
    assert signal.quote == "We are pivoting our strategy."
    assert signal.source_url == "https://example.com/interview"
