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
