"""Tests for the weekly pattern-identification and monthly roll-up passes
(cadence ladder: daily -> weekly -> monthly, per the product doctrine)."""

from __future__ import annotations

from datetime import date

import pytest

from cios.brain.cadence import MalformedCadenceOutput, MonthlySynthesizer, WeeklySynthesizer
from cios.brain.types import BrainEventType, CadenceActionItem, Pattern, Signal, Verdict, WeeklySynthesisResult

from .conftest import FakeModel, weekly_action_payload, weekly_pattern_payload


def _signal(headline: str = "Rival cuts entry price 20%", url: str = "https://rival.com/pricing") -> Signal:
    return Signal(
        competitor_id=7,
        signal_type="pricing change",
        headline=headline,
        what_changed="entry tier dropped",
        recommended_action="Brief the field.",
        owner="PMM",
        team_to_involve="Sales Enablement",
        materiality_score=0.8,
        evidence_urls=[url],
    )


class FakeDailySignalLedger:
    def __init__(self, signals: list[Signal]) -> None:
        self._signals = signals

    def signals_for_week(self, tenant_id: int, competitor_id: int, week_start: date) -> list[Signal]:
        return self._signals


class FakeWeeklyResultLedger:
    def __init__(self, weeklies: list[WeeklySynthesisResult]) -> None:
        self._weeklies = weeklies

    def weeklies_for_month(self, tenant_id: int, competitor_id: int, month_start: date) -> list[WeeklySynthesisResult]:
        return self._weeklies


async def test_weekly_promotes_pattern_with_evidence() -> None:
    signals = [_signal()]
    model = FakeModel([{"patterns": [weekly_pattern_payload()], "action_plan": [weekly_action_payload()]}])
    result = await WeeklySynthesizer(model, FakeDailySignalLedger(signals)).synthesize(1, 7, date(2026, 7, 6))
    assert result.verdict is Verdict.SIGNALS
    assert len(result.patterns) == 1
    assert result.patterns[0].evidence_urls == ["https://rival.com/pricing"]
    assert len(result.action_plan) == 1
    assert result.action_plan[0].team_to_involve == "Sales Enablement"


async def test_weekly_pattern_without_evidence_is_rejected() -> None:
    signals = [_signal()]
    model = FakeModel([{"patterns": [weekly_pattern_payload(evidence_urls=[])], "action_plan": []}])
    result = await WeeklySynthesizer(model, FakeDailySignalLedger(signals)).synthesize(1, 7, date(2026, 7, 6))
    assert result.patterns == []
    assert any(e.event_type is BrainEventType.EVIDENCE_REJECTED for e in result.events)


async def test_weekly_pattern_citing_fabricated_url_is_rejected() -> None:
    signals = [_signal()]
    model = FakeModel(
        [{"patterns": [weekly_pattern_payload(evidence_urls=["https://made-up.example/x"])], "action_plan": []}]
    )
    result = await WeeklySynthesizer(model, FakeDailySignalLedger(signals)).synthesize(1, 7, date(2026, 7, 6))
    assert result.patterns == []
    ev = [e for e in result.events if e.event_type is BrainEventType.EVIDENCE_REJECTED]
    assert ev and "fabricated_urls" in ev[0].payload


async def test_weekly_action_missing_team_is_suppressed() -> None:
    signals = [_signal()]
    model = FakeModel(
        [{"patterns": [], "action_plan": [weekly_action_payload(team_to_involve="Marketing Ops")]}]
    )
    result = await WeeklySynthesizer(model, FakeDailySignalLedger(signals)).synthesize(1, 7, date(2026, 7, 6))
    assert result.action_plan == []
    assert any(e.event_type is BrainEventType.MATERIALITY_SUPPRESSED for e in result.events)


async def test_weekly_no_pattern_is_quiet_not_failure() -> None:
    signals = [_signal()]
    model = FakeModel([{"patterns": [], "action_plan": []}])
    result = await WeeklySynthesizer(model, FakeDailySignalLedger(signals)).synthesize(1, 7, date(2026, 7, 6))
    assert result.verdict is Verdict.QUIET


async def test_weekly_malformed_json_twice_hard_fails() -> None:
    model = FakeModel(["garbage one", "garbage two"])
    with pytest.raises(MalformedCadenceOutput):
        await WeeklySynthesizer(model, FakeDailySignalLedger([_signal()])).synthesize(1, 7, date(2026, 7, 6))


async def test_monthly_rolls_up_weekly_patterns() -> None:
    weekly = WeeklySynthesisResult(
        tenant_id=1,
        competitor_id=7,
        week_start=date(2026, 7, 6),
        verdict=Verdict.SIGNALS,
        patterns=[Pattern(pattern="Sustained pricing pressure", materiality_score=0.7, evidence_urls=["https://rival.com/pricing"])],
        action_plan=[
            CadenceActionItem(
                action="Brief the field", team_to_involve="Sales Enablement", evidence_urls=["https://rival.com/pricing"]
            )
        ],
    )
    model = FakeModel(
        [
            {
                "patterns": [weekly_pattern_payload(pattern="Month-long pricing squeeze")],
                "action_plan": [weekly_action_payload()],
            }
        ]
    )
    result = await MonthlySynthesizer(model, FakeWeeklyResultLedger([weekly])).synthesize(1, 7, date(2026, 7, 1))
    assert result.verdict is Verdict.SIGNALS
    assert result.patterns[0].pattern == "Month-long pricing squeeze"


async def test_monthly_pattern_citing_url_outside_weeklies_is_rejected() -> None:
    weekly = WeeklySynthesisResult(
        tenant_id=1,
        competitor_id=7,
        week_start=date(2026, 7, 6),
        verdict=Verdict.SIGNALS,
        patterns=[Pattern(pattern="p", materiality_score=0.7, evidence_urls=["https://rival.com/pricing"])],
    )
    model = FakeModel(
        [{"patterns": [weekly_pattern_payload(evidence_urls=["https://made-up.example/x"])], "action_plan": []}]
    )
    result = await MonthlySynthesizer(model, FakeWeeklyResultLedger([weekly])).synthesize(1, 7, date(2026, 7, 1))
    assert result.patterns == []
    assert any(e.event_type is BrainEventType.EVIDENCE_REJECTED for e in result.events)
