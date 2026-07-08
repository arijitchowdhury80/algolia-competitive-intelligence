"""Tests for prescribe.types: grounding and concrete-play invariants."""

from __future__ import annotations

import pytest

from cios.prescribe.types import Effort, Grounding, Prescription, Team, UrgencyWindow


def _grounding(**overrides) -> Grounding:
    base = dict(
        signal_evidence_urls=["https://rival.com/pricing"],
        connection_evidence_urls=[],
        thesis_ids=[],
        evidence_urls=["https://rival.com/pricing"],
    )
    base.update(overrides)
    return Grounding(**base)


def test_grounding_requires_evidence_urls() -> None:
    with pytest.raises(ValueError):
        Grounding(signal_evidence_urls=["https://rival.com/pricing"], evidence_urls=[])


def test_grounding_requires_a_traceable_reference() -> None:
    with pytest.raises(ValueError):
        Grounding(evidence_urls=["https://rival.com/pricing"])


def test_grounding_accepts_thesis_only_reference() -> None:
    g = Grounding(thesis_ids=[3], evidence_urls=["https://rival.com/pricing"])
    assert g.thesis_ids == [3]


def test_prescription_requires_concrete_play_steps() -> None:
    with pytest.raises(ValueError):
        Prescription(
            tenant_id=1,
            title="Do something",
            play=[],
            team=Team.MARKETING,
            urgency_window=UrgencyWindow.THIS_WEEK,
            grounding=_grounding(),
            expected_effect="more traffic",
            effort=Effort.S,
        )


def test_prescription_requires_title_and_expected_effect() -> None:
    with pytest.raises(ValueError):
        Prescription(
            tenant_id=1,
            title="",
            play=["do the thing"],
            team=Team.MARKETING,
            urgency_window=UrgencyWindow.THIS_WEEK,
            grounding=_grounding(),
            expected_effect="more traffic",
            effort=Effort.S,
        )


def test_prescription_rank_score_is_urgency_times_materiality() -> None:
    p = Prescription(
        tenant_id=1,
        title="Ship the comparison page",
        play=["write the page", "brief SEO", "link from homepage"],
        team=Team.MARKETING,
        urgency_window=UrgencyWindow.ACT_NOW,
        grounding=_grounding(),
        expected_effect="capture the keyword gap",
        effort=Effort.M,
        materiality_score=0.5,
    )
    assert p.rank_score == pytest.approx(3.0 * 0.5)
