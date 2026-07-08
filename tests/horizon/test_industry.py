"""Tests for HorizonSynthesizer: single-source theme flagging, evidence
guard, empty-input short circuit, tenant scoping."""

from __future__ import annotations

from datetime import date

import pytest

from cios.horizon.industry import HorizonSynthesizer, MalformedHorizonOutput
from cios.horizon.types import Horizon, IndustryObservation, ThemeConfidence

from .conftest import FakeModel


def _obs(url: str, summary: str = "something happened", days_ago: int = 1) -> IndustryObservation:
    return IndustryObservation(
        competitor_id=1,
        observed_at=date(2026, 7, 8),
        kind="event",
        summary=summary,
        source_url=url,
    )


async def test_confirmed_theme_needs_two_distinct_sources() -> None:
    observations = [_obs("https://a.com/1"), _obs("https://b.com/1")]
    model = FakeModel(
        [
            {
                "notable_movements": ["broad shift"],
                "themes": [
                    {
                        "theme": "industry consolidating",
                        "evidence_urls": ["https://a.com/1", "https://b.com/1"],
                    }
                ],
                "relevance": {"score": 0.6, "rationale": "affects the tenant's segment"},
            }
        ]
    )
    read = await HorizonSynthesizer(model).synthesize(
        tenant_id=1,
        horizon=Horizon.D30,
        as_of=date(2026, 7, 8),
        ledger_observations=observations,
        window=(date(2026, 6, 9), date(2026, 7, 8)),
    )
    assert len(read.themes) == 1
    assert read.themes[0].confidence is ThemeConfidence.CONFIRMED
    assert read.relevance is not None
    assert read.relevance.score == 0.6


async def test_single_source_theme_is_flagged_unconfirmed() -> None:
    observations = [_obs("https://a.com/1")]
    model = FakeModel(
        [
            {
                "notable_movements": [],
                "themes": [
                    {"theme": "one player moved", "evidence_urls": ["https://a.com/1"]}
                ],
                "relevance": {"score": 0.3, "rationale": "minor"},
            }
        ]
    )
    read = await HorizonSynthesizer(model).synthesize(
        tenant_id=1,
        horizon=Horizon.D10,
        as_of=date(2026, 7, 8),
        ledger_observations=observations,
        window=(date(2026, 6, 29), date(2026, 7, 8)),
    )
    assert len(read.themes) == 1
    assert read.themes[0].confidence is ThemeConfidence.SINGLE_SOURCE_UNCONFIRMED


async def test_theme_citing_fabricated_evidence_is_dropped() -> None:
    observations = [_obs("https://a.com/1")]
    model = FakeModel(
        [
            {
                "notable_movements": [],
                "themes": [
                    {"theme": "made up", "evidence_urls": ["https://not-in-input.com/x"]}
                ],
                "relevance": None,
            }
        ]
    )
    read = await HorizonSynthesizer(model).synthesize(
        tenant_id=1,
        horizon=Horizon.D10,
        as_of=date(2026, 7, 8),
        ledger_observations=observations,
        window=(date(2026, 6, 29), date(2026, 7, 8)),
    )
    assert read.themes == []


async def test_empty_observations_short_circuits_without_model_call() -> None:
    model = FakeModel([])
    read = await HorizonSynthesizer(model).synthesize(
        tenant_id=1,
        horizon=Horizon.D10,
        as_of=date(2026, 7, 8),
        ledger_observations=[],
        window=(date(2026, 6, 29), date(2026, 7, 8)),
    )
    assert read.themes == []
    assert read.notable_movements == []
    assert model.calls == []


async def test_malformed_output_twice_raises() -> None:
    observations = [_obs("https://a.com/1")]
    model = FakeModel(["not json", "still not json"])
    with pytest.raises(MalformedHorizonOutput):
        await HorizonSynthesizer(model).synthesize(
            tenant_id=1,
            horizon=Horizon.D10,
            as_of=date(2026, 7, 8),
            ledger_observations=observations,
            window=(date(2026, 6, 29), date(2026, 7, 8)),
        )


async def test_external_feed_is_merged_with_ledger_observations() -> None:
    class FakeFeed:
        def observations_in_window(self, tenant_id: int, start: date, end: date):
            return [_obs("https://external.com/1", summary="external event")]

    observations = [_obs("https://a.com/1")]
    model = FakeModel(
        [
            {
                "notable_movements": [],
                "themes": [
                    {
                        "theme": "cross-source pattern",
                        "evidence_urls": ["https://a.com/1", "https://external.com/1"],
                    }
                ],
                "relevance": None,
            }
        ]
    )
    read = await HorizonSynthesizer(model, feed=FakeFeed()).synthesize(
        tenant_id=1,
        horizon=Horizon.D10,
        as_of=date(2026, 7, 8),
        ledger_observations=observations,
        window=(date(2026, 6, 29), date(2026, 7, 8)),
    )
    assert read.themes[0].confidence is ThemeConfidence.CONFIRMED
