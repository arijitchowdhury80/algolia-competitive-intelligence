"""Tests for the semantic synthesizer -- the doctrine enforcement core."""

from __future__ import annotations

import pytest

from cios.brain.synthesizer import MalformedSynthesisOutput, Synthesizer
from cios.brain.types import (
    BrainEventType,
    CoverageReport,
    LaneStatus,
    SynthesisInput,
    Verdict,
)
from cios.collect.types import Delta

from .conftest import FakeModel, signal_payload


def _delta(url: str = "https://rival.com/pricing") -> Delta:
    return Delta(
        competitor_id=7,
        delta_type="pricing change",
        materiality_score=0.8,
        what_changed="entry tier dropped",
        evidence_urls=[url],
    )


def _clean_coverage() -> CoverageReport:
    return CoverageReport(
        lanes=[LaneStatus(lane="web", ran=True), LaneStatus(lane="news", ran=True)]
    )


def _input(**overrides) -> SynthesisInput:
    base = dict(
        tenant_id=1,
        competitor_id=7,
        competitor_name="Rival Inc",
        deltas=[_delta()],
        coverage=_clean_coverage(),
    )
    base.update(overrides)
    return SynthesisInput(**base)


async def test_promotes_material_signal_with_evidence() -> None:
    model = FakeModel([{"signals": [signal_payload()]}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.verdict is Verdict.SIGNALS
    assert len(result.signals) == 1
    assert result.signals[0].evidence_urls == ["https://rival.com/pricing"]
    assert result.signals[0].owner == "PMM"
    assert result.signals[0].team_to_involve == "Marketing"


async def test_signal_missing_team_to_involve_is_suppressed() -> None:
    payload = signal_payload()
    payload["team_to_involve"] = "Marketing Ops"  # not in the doctrine's valid set
    model = FakeModel([{"signals": [payload]}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.signals == []
    assert any(e.event_type is BrainEventType.MATERIALITY_SUPPRESSED for e in result.events)


async def test_tenant_own_position_omitted_when_no_evidence_supplied() -> None:
    """evidence-or-silence extends to the tenant's own position: with no
    own_position_facts, the data block must say so rather than inventing a
    'where you are' claim, and must never state a company name we were not
    given."""
    model = FakeModel([{"signals": []}])
    inp = _input()
    data_block = Synthesizer._build_data_block(inp)
    assert "do not fabricate" in data_block.lower()


async def test_tenant_own_position_surfaced_when_evidence_supplied() -> None:
    model = FakeModel([{"signals": []}])
    inp = _input(
        tenant_company_name="Acme Corp",
        own_position_facts=["Acme holds 30% share in the mid-market segment per its own Q2 investor deck."],
    )
    data_block = Synthesizer._build_data_block(inp)
    assert "Acme Corp" in data_block
    assert "30% share" in data_block


async def test_signal_without_url_is_rejected_not_promoted() -> None:
    model = FakeModel([{"signals": [signal_payload(evidence_urls=[])]}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.signals == []
    assert any(e.event_type is BrainEventType.EVIDENCE_REJECTED for e in result.events)


async def test_signal_citing_fabricated_url_is_rejected() -> None:
    model = FakeModel([{"signals": [signal_payload(evidence_urls=["https://made-up.example/x"])]}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.signals == []
    ev = [e for e in result.events if e.event_type is BrainEventType.EVIDENCE_REJECTED]
    assert ev and "fabricated_urls" in ev[0].payload


async def test_below_materiality_floor_is_suppressed() -> None:
    model = FakeModel([{"signals": [signal_payload(materiality_score=0.10)]}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.signals == []
    assert any(e.event_type is BrainEventType.MATERIALITY_SUPPRESSED for e in result.events)


async def test_missing_owner_or_action_is_suppressed() -> None:
    model = FakeModel([{"signals": [signal_payload(owner="Marketing", recommended_action="")]}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.signals == []
    assert any(e.event_type is BrainEventType.MATERIALITY_SUPPRESSED for e in result.events)


async def test_quiet_only_when_coverage_clean() -> None:
    model = FakeModel([{"signals": []}])
    result = await Synthesizer(model).synthesize(_input())
    assert result.verdict is Verdict.QUIET


async def test_no_signal_without_full_coverage_is_coverage_failure_not_quiet() -> None:
    broken = CoverageReport(
        lanes=[LaneStatus(lane="web", ran=True), LaneStatus(lane="news", ran=False, error="timeout")]
    )
    model = FakeModel([{"signals": []}])
    result = await Synthesizer(model).synthesize(_input(coverage=broken))
    assert result.verdict is Verdict.COVERAGE_FAILURE
    ev = [e for e in result.events if e.event_type is BrainEventType.COVERAGE_FAILURE]
    assert ev and ev[0].payload["failed_lanes"] == ["news"]


async def test_malformed_json_retries_once_then_succeeds() -> None:
    model = FakeModel(["not json at all", {"signals": [signal_payload()]}])
    result = await Synthesizer(model).synthesize(_input())
    assert len(model.calls) == 2  # one retry
    assert result.verdict is Verdict.SIGNALS
    assert any(e.event_type is BrainEventType.MALFORMED_LLM_OUTPUT for e in result.events)


async def test_malformed_json_twice_hard_fails_no_fabrication() -> None:
    model = FakeModel(["garbage one", "garbage two"])
    with pytest.raises(MalformedSynthesisOutput):
        await Synthesizer(model).synthesize(_input())
    assert len(model.calls) == 2


async def test_tenant_id_flows_to_model_request() -> None:
    model = FakeModel([{"signals": []}])
    await Synthesizer(model).synthesize(_input(tenant_id=42))
    assert model.calls[0].tenant_id == "42"


# -- within-run signal dedup (task #25 root-cause fix) -----------------------


async def test_two_candidates_describing_same_story_merge_into_one_signal() -> None:
    p1 = signal_payload(
        headline="Rival cuts entry price 20 percent",
        evidence_urls=["https://rival.com/pricing"],
        materiality_score=0.6,
    )
    p2 = signal_payload(
        headline="Rival cuts its entry tier price by 20 percent",
        evidence_urls=["https://rival.com/announcement"],
        materiality_score=0.8,
    )
    model = FakeModel([{"signals": [p1, p2]}])
    result = await Synthesizer(model).synthesize(_input(deltas=[
        _delta("https://rival.com/pricing"),
        _delta("https://rival.com/announcement"),
    ]))
    assert result.verdict is Verdict.SIGNALS
    assert len(result.signals) == 1
    assert result.signals[0].materiality_score == 0.8  # higher-materiality wording wins
    assert set(result.signals[0].evidence_urls) == {
        "https://rival.com/pricing", "https://rival.com/announcement",
    }  # evidence unioned, nothing dropped
    assert any(e.event_type == BrainEventType.SIGNAL_DEDUPED for e in result.events)


async def test_two_candidates_describing_different_stories_both_ship() -> None:
    p1 = signal_payload(headline="Rival cuts entry price 20 percent")
    # A genuinely different story carries different body text too -- two
    # distinct events never share an identical what_changed sentence.
    p2 = signal_payload(headline="Rival lays off part of its sales team",
                        what_changed="About 15 percent of the sales org was let go this week.")
    model = FakeModel([{"signals": [p1, p2]}])
    result = await Synthesizer(model).synthesize(_input())
    assert len(result.signals) == 2
    assert not any(e.event_type == BrainEventType.SIGNAL_DEDUPED for e in result.events)
