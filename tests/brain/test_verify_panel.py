"""Tests for the adversarial verify panel (refute + evidence-URL audit)."""

from __future__ import annotations

from cios.brain.types import Signal
from cios.brain.verify_panel import VerifyPanel

from .conftest import FakeModel

ALLOWED = {"https://rival.com/pricing"}


def _signal(evidence_urls=None, headline="Rival cuts entry price 20%") -> Signal:
    return Signal(
        competitor_id=7,
        signal_type="pricing change",
        headline=headline,
        what_changed="entry tier 500 -> 400",
        why_it_matters="undercuts mid-market",
        recommended_action="Brief the field.",
        owner="PMM",
        materiality_score=0.8,
        evidence_urls=evidence_urls if evidence_urls is not None else ["https://rival.com/pricing"],
    )


async def test_signal_survives_when_evidence_ok_and_refute_holds() -> None:
    model = FakeModel([{"holds": True, "rebuttal": None}])
    report = await VerifyPanel(model).run([_signal()], ALLOWED)
    assert report.all_passed
    assert report.survivors == ["Rival cuts entry price 20%"]


async def test_signal_knocked_down_when_refute_wins() -> None:
    model = FakeModel([{"holds": False, "rebuttal": "routine promo, not structural"}])
    report = await VerifyPanel(model).run([_signal()], ALLOWED)
    assert not report.all_passed
    v = report.verdicts[0]
    assert v.evidence_ok is True
    assert v.refute_held is False
    assert v.rebuttal == "routine promo, not structural"


async def test_fabricated_url_fails_evidence_audit_and_skips_refute() -> None:
    model = FakeModel([{"holds": True}])  # would pass if reached
    report = await VerifyPanel(model).run([_signal(evidence_urls=["https://fake.example/x"])], ALLOWED)
    assert not report.all_passed
    assert report.verdicts[0].evidence_ok is False
    assert model.calls == []  # refute never called; evidence already failed


async def test_missing_url_fails_evidence_audit() -> None:
    model = FakeModel([{"holds": True}])
    report = await VerifyPanel(model).run([_signal(evidence_urls=[])], ALLOWED)
    assert not report.all_passed
    assert "no evidence URL" in report.verdicts[0].reasons


async def test_unparseable_refute_fails_closed() -> None:
    model = FakeModel(["not json"])
    report = await VerifyPanel(model).run([_signal()], ALLOWED)
    assert not report.all_passed
    assert report.verdicts[0].refute_held is False


async def test_mixed_batch_reports_survivors_and_knockdowns() -> None:
    model = FakeModel([{"holds": True}, {"holds": False, "rebuttal": "noise"}])
    signals = [_signal(headline="A"), _signal(headline="B")]
    report = await VerifyPanel(model).run(signals, ALLOWED)
    assert report.survivors == ["A"]
    assert report.knocked_down == ["B"]
