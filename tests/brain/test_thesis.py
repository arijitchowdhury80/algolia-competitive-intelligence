"""Tests for the living competitor thesis engine."""

from __future__ import annotations

import pytest

from cios.brain.thesis import ThesisEngine, ThesisEvidenceError, find_similar_active_thesis


def _open(engine: ThesisEngine):
    return engine.open_thesis(
        tenant_id=1,
        competitor_id=7,
        thesis="Rival is wedging on agentic shopping.",
        confidence=0.5,
        evidence_ids=["d1"],
    )


def test_open_requires_evidence() -> None:
    engine = ThesisEngine()
    with pytest.raises(ThesisEvidenceError):
        engine.open_thesis(
            tenant_id=1, competitor_id=7, thesis="x", confidence=0.5, evidence_ids=[]
        )


def test_update_requires_new_evidence() -> None:
    engine = ThesisEngine()
    _open(engine)
    with pytest.raises(ThesisEvidenceError):
        engine.update(competitor_id=7, thesis="revised", confidence=0.6, new_evidence_ids=[])


def test_update_preserves_history_and_bumps_confidence() -> None:
    engine = ThesisEngine()
    _open(engine)
    updated = engine.update(
        competitor_id=7,
        thesis="Rival is doubling down on agentic shopping with pricing to match.",
        confidence=0.75,
        new_evidence_ids=["d2"],
    )
    assert updated.confidence == 0.75
    assert set(updated.evidence_ids) == {"d1", "d2"}
    # prior state preserved, never rewritten.
    assert len(updated.history) == 1
    assert updated.history[0].thesis == "Rival is wedging on agentic shopping."
    assert updated.history[0].confidence == 0.5


def test_status_transition_recorded() -> None:
    engine = ThesisEngine()
    _open(engine)
    updated = engine.update(
        competitor_id=7,
        thesis="Confirmed: agentic shopping is the wedge.",
        confidence=0.9,
        new_evidence_ids=["d3"],
        status="confirmed",
    )
    assert updated.status == "confirmed"
    assert updated.history[0].status == "active"


def test_update_unknown_competitor_raises() -> None:
    engine = ThesisEngine()
    with pytest.raises(KeyError):
        engine.update(competitor_id=99, thesis="x", confidence=0.5, new_evidence_ids=["d1"])


# -- thesis merge (task #25 root-cause fix) ----------------------------------
# find_similar_active_thesis is what the daily production runner consults
# before deciding whether to attach new evidence to an existing thesis or
# spawn a brand-new competitor_theses row -- see scripts/daily_production_run.py.


def test_similar_thesis_for_same_competitor_is_found_attach_branch() -> None:
    active = [
        {"id": 1, "competitor_id": 7, "thesis": "Rival is wedging into agentic shopping search."},
        {"id": 2, "competitor_id": 3, "thesis": "Other Co is expanding into EMEA."},
    ]
    found = find_similar_active_thesis(
        active, competitor_id=7, candidate_thesis="Rival is wedging agentic shopping into search."
    )
    assert found is not None
    assert found["id"] == 1


def test_dissimilar_thesis_for_same_competitor_is_not_found_spawn_branch() -> None:
    active = [
        {"id": 1, "competitor_id": 7, "thesis": "Rival is wedging into agentic shopping search."},
    ]
    found = find_similar_active_thesis(
        active, competitor_id=7, candidate_thesis="Rival's CFO resigned amid a restructuring."
    )
    assert found is None


def test_similar_thesis_for_a_different_competitor_never_matches() -> None:
    active = [
        {"id": 1, "competitor_id": 3, "thesis": "Rival is wedging into agentic shopping search."},
    ]
    found = find_similar_active_thesis(
        active, competitor_id=7, candidate_thesis="Rival is wedging into agentic shopping search."
    )
    assert found is None
