"""Tests for PrescriptionEngine: evidence guard (ungrounded + fabricated
evidence rejection), platitude rejection, team+urgency required, cap+ranking,
and the empty-input short circuit."""

from __future__ import annotations

from datetime import date

import pytest

from cios.brain.types import Signal, Thesis
from cios.horizon.types import Horizon, DotConnection
from cios.ownbrand.types import BrandPositionRead, BrandTheme
from cios.prescribe.engine import MalformedPrescriptionOutput, PrescriptionEngine
from cios.prescribe.types import Team, UrgencyWindow

from .conftest import FakeModel


def _signal(url: str = "https://rival.com/pricing") -> Signal:
    return Signal(
        competitor_id=7,
        signal_type="pricing change",
        headline="Rival cuts entry price 20%",
        what_changed="entry tier dropped",
        recommended_action="Brief the field.",
        owner="PMM",
        team_to_involve="Sales Enablement",
        materiality_score=0.8,
        evidence_urls=[url],
    )


def _connection(
    signal_url: str = "https://rival.com/pricing", horizon_url: str = "https://industry.com/trend"
) -> DotConnection:
    return DotConnection(
        tenant_id=1,
        horizon=Horizon.D30,
        connection="this week's price cut fits the 30-day compression trend",
        signal_evidence_urls=[signal_url],
        horizon_evidence_urls=[horizon_url],
    )


def _thesis(thesis_id: int = 3) -> Thesis:
    return Thesis(
        id=thesis_id,
        tenant_id=1,
        competitor_id=7,
        thesis="Rival is racing to the bottom on price.",
    )


def _brand_position(url: str = "https://tenant.com/blog/post") -> BrandPositionRead:
    return BrandPositionRead(
        tenant_id=1,
        tenant_company_name="Meridian Retail",
        themes=[
            BrandTheme(
                label="reliability",
                summary="We are positioned as the reliable choice.",
                observation_urls=[url],
            )
        ],
    )


def _valid_candidate(**overrides) -> dict:
    base = {
        "title": "Publish a comparison landing page while the gap is open",
        "play": [
            "Write a 900-word page naming the exact pricing cut and date.",
            "Brief the SEO team today to target the relevant keyword phrases.",
            "Link the page from the homepage hero within 3 business days.",
        ],
        "team": "Marketing",
        "urgency_window": "act_now",
        "expected_effect": "capture searches comparing the two pricing pages",
        "effort": "M",
        "materiality_score": 0.8,
        "signal_evidence_urls": ["https://rival.com/pricing"],
        "connection_evidence_urls": [],
        "thesis_ids": [],
        "evidence_urls": ["https://rival.com/pricing"],
    }
    base.update(overrides)
    return base


async def test_no_input_short_circuits_without_calling_model() -> None:
    model = FakeModel([{"prescriptions": [_valid_candidate()]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[])
    assert result == []
    assert model.calls == []


async def test_valid_grounded_prescription_is_accepted() -> None:
    model = FakeModel([{"prescriptions": [_valid_candidate()]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert len(result) == 1
    assert result[0].team is Team.MARKETING
    assert result[0].urgency_window is UrgencyWindow.ACT_NOW
    assert result[0].grounding.signal_evidence_urls == ["https://rival.com/pricing"]


async def test_prescription_citing_fabricated_evidence_is_rejected() -> None:
    cand = _valid_candidate(
        evidence_urls=["https://not-real.com"],
        signal_evidence_urls=["https://not-real.com"],
    )
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_prescription_with_no_grounding_reference_is_rejected() -> None:
    # cites a real evidence URL but ties it to nothing (no signal/connection
    # url and no thesis id) -- Grounding's own validator should reject this.
    cand = _valid_candidate(
        signal_evidence_urls=[],
        connection_evidence_urls=[],
        thesis_ids=[],
        evidence_urls=["https://rival.com/pricing"],
    )
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_prescription_citing_thesis_id_not_supplied_is_rejected() -> None:
    cand = _valid_candidate(thesis_ids=[999], evidence_urls=["https://rival.com/pricing"])
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(
        1, signals=[_signal()], theses=[_thesis(3)]
    )
    assert result == []


async def test_prescription_grounded_via_connection_is_accepted() -> None:
    cand = _valid_candidate(
        signal_evidence_urls=[],
        connection_evidence_urls=["https://industry.com/trend"],
        evidence_urls=["https://industry.com/trend"],
    )
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(
        1, signals=[_signal()], connections=[_connection()]
    )
    assert len(result) == 1


async def test_prescription_grounded_via_brand_position_is_accepted() -> None:
    cand = _valid_candidate(
        signal_evidence_urls=[],
        evidence_urls=["https://tenant.com/blog/post"],
        connection_evidence_urls=["https://tenant.com/blog/post"],
    )
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(
        1, signals=[], brand_position=_brand_position()
    )
    assert len(result) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", " "),
        ("play", []),
        ("expected_effect", ""),
    ],
)
async def test_missing_required_field_is_rejected(field: str, value) -> None:
    cand = _valid_candidate(**{field: value})
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_invalid_team_is_rejected() -> None:
    cand = _valid_candidate(team="Growth Hacking")
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_invalid_urgency_window_is_rejected() -> None:
    cand = _valid_candidate(urgency_window="eventually")
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_below_materiality_floor_is_rejected() -> None:
    cand = _valid_candidate(materiality_score=0.1)
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model, materiality_floor=0.35).prescribe(
        1, signals=[_signal()]
    )
    assert result == []


@pytest.mark.parametrize(
    "phrase",
    [
        "leverage synergies",
        "consider a strategy",
        "monitor the situation",
    ],
)
async def test_banned_platitude_in_title_is_rejected(phrase: str) -> None:
    cand = _valid_candidate(title=f"We should {phrase} here")
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_banned_platitude_in_play_step_is_rejected() -> None:
    cand = _valid_candidate(play=["Consider a strategy to respond."])
    model = FakeModel([{"prescriptions": [cand]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert result == []


async def test_cap_and_ranking_by_urgency_times_materiality() -> None:
    candidates = [
        _valid_candidate(
            title=f"Play {i}",
            urgency_window=window,
            materiality_score=score,
        )
        for i, (window, score) in enumerate(
            [
                ("this_month", 0.4),   # rank 0.4
                ("act_now", 0.9),      # rank 2.7 (highest)
                ("this_week", 0.9),    # rank 1.8
                ("this_week", 0.5),    # rank 1.0
                ("act_now", 0.4),      # rank 1.2
                ("this_month", 0.9),   # rank 0.9
                ("this_week", 0.36),   # rank 0.72
            ]
        )
    ]
    model = FakeModel([{"prescriptions": candidates}])
    result = await PrescriptionEngine(model, max_per_cycle=5).prescribe(
        1, signals=[_signal()]
    )
    assert len(result) == 5
    scores = [p.rank_score for p in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0].title == "Play 1"  # act_now x 0.9 = 2.7, the top score


async def test_malformed_json_twice_raises() -> None:
    model = FakeModel(["not json", "still not json"])
    with pytest.raises(MalformedPrescriptionOutput):
        await PrescriptionEngine(model).prescribe(1, signals=[_signal()])


async def test_malformed_json_once_then_valid_recovers() -> None:
    model = FakeModel(["not json", {"prescriptions": [_valid_candidate()]}])
    result = await PrescriptionEngine(model).prescribe(1, signals=[_signal()])
    assert len(result) == 1
    assert len(model.calls) == 2


async def test_no_vendor_literals_in_prompt_templates() -> None:
    from cios.prescribe.prompts import PRESCRIPTION_SYSTEM

    banned_real_vendors = ["algolia", "constructor.io", "coveo", "bloomreach", "klue"]
    lowered = PRESCRIPTION_SYSTEM.lower()
    for vendor in banned_real_vendors:
        assert vendor not in lowered
