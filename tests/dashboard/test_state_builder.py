from __future__ import annotations

from cios.dashboard.state_builder import DashboardStateBuilder
from cios.dashboard.types import AttentionLevel

from .conftest import (
    FakeBuildStatusProvider,
    FakeCoverageRepository,
    FakeRunRepository,
    FakeSignalsRepository,
    FakeThesesRepository,
    broken_coverage,
    build_status_ok,
    delta,
    full_coverage,
    thesis,
)


def make_builder(
    *,
    signals=None,
    theses=None,
    coverage=None,
    runs=None,
    build_status=None,
) -> DashboardStateBuilder:
    return DashboardStateBuilder(
        signals=FakeSignalsRepository(signals or {}),
        theses=FakeThesesRepository(theses or {}),
        coverage=FakeCoverageRepository(coverage or {}),
        runs=FakeRunRepository(runs or {}),
        build_status=FakeBuildStatusProvider(build_status) if build_status is not None else None,
    )


# -- no-green-quiet enforcement -------------------------------------------


def test_no_coverage_record_is_never_quiet():
    builder = make_builder(coverage={}, signals={1: []})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.coverage.all_lanes_ran is False
    assert state.is_quiet is False


def test_incomplete_coverage_is_never_quiet_even_with_zero_signals():
    builder = make_builder(coverage={1: broken_coverage()}, signals={1: []})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.coverage.all_lanes_ran is False
    assert state.material_delta_ids == []
    assert state.competitor_cards == []
    # zero signals + broken coverage must NOT read as quiet-green.
    assert state.is_quiet is False


def test_complete_coverage_with_zero_signals_is_quiet():
    builder = make_builder(coverage={1: full_coverage()}, signals={1: []})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.coverage.all_lanes_ran is True
    assert state.is_quiet is True


def test_complete_coverage_with_material_signals_is_not_quiet():
    builder = make_builder(
        coverage={1: full_coverage()},
        signals={1: [delta(id=1, materiality_score=0.9)]},
    )
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.coverage.all_lanes_ran is True
    assert state.is_quiet is False


def test_false_negative_audit_at_risk_blocks_quiet_even_if_all_lanes_ran():
    coverage = full_coverage()
    coverage["false_negative_audit_status"] = "at_risk"
    builder = make_builder(coverage={1: coverage}, signals={1: []})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.coverage.all_lanes_ran is True
    assert state.is_quiet is False


# -- materiality ordering ---------------------------------------------------


def test_competitor_cards_are_materiality_ranked_descending():
    signals = {
        1: [
            delta(id=1, competitor_id=1, materiality_score=0.3),
            delta(id=2, competitor_id=2, materiality_score=0.9),
            delta(id=3, competitor_id=3, materiality_score=0.6),
        ]
    }
    builder = make_builder(coverage={1: full_coverage()}, signals=signals)
    state = builder.build(tenant_id=1, cadence="daily")
    scores = [c.attention_score for c in state.competitor_cards]
    assert scores == sorted(scores, reverse=True)
    assert state.competitor_cards[0].competitor_id == 2
    assert state.top_attention_level == AttentionLevel.ACT_NOW


def test_materiality_ties_break_deterministically_by_competitor_id():
    signals = {
        1: [
            delta(id=1, competitor_id=5, materiality_score=0.5),
            delta(id=2, competitor_id=2, materiality_score=0.5),
        ]
    }
    builder = make_builder(coverage={1: full_coverage()}, signals=signals)
    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=1, cadence="daily")
    ids1 = [c.competitor_id for c in state1.competitor_cards]
    ids2 = [c.competitor_id for c in state2.competitor_cards]
    assert ids1 == ids2 == [2, 5]


def test_every_card_has_a_non_empty_action_cue():
    signals = {1: [delta(id=1, materiality_score=0.9, recommended_action=None)]}
    builder = make_builder(coverage={1: full_coverage()}, signals=signals)
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.competitor_cards[0].action_cue
    assert state.competitor_cards[0].attention_level == AttentionLevel.ACT_NOW


# -- tenant scoping ----------------------------------------------------------


def test_tenant_scoping_does_not_leak_across_tenants():
    signals = {
        1: [delta(id=1, competitor_id=1, materiality_score=0.9)],
        2: [delta(id=2, competitor_id=99, materiality_score=0.9)],
    }
    coverage = {1: full_coverage(), 2: full_coverage()}
    builder = make_builder(coverage=coverage, signals=signals)

    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=2, cadence="daily")

    assert [c.competitor_id for c in state1.competitor_cards] == [1]
    assert [c.competitor_id for c in state2.competitor_cards] == [99]
    assert state1.tenant_id == 1
    assert state2.tenant_id == 2


def test_theses_are_tenant_scoped():
    theses = {
        1: [thesis(id=1, competitor_id=1)],
        2: [thesis(id=2, competitor_id=99)],
    }
    builder = make_builder(coverage={1: full_coverage(), 2: full_coverage()}, theses=theses)
    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=2, cadence="daily")
    assert [t.thesis_id for t in state1.theses] == [1]
    assert [t.thesis_id for t in state2.theses] == [2]


# -- build/system status section --------------------------------------------


def test_build_status_present_when_provider_injected():
    builder = make_builder(coverage={1: full_coverage()}, build_status=build_status_ok())
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.build_status.build_id == "2026.07.08-1"
    assert state.build_status.all_services_ok is True


def test_build_status_flags_absence_when_no_provider_injected():
    builder = make_builder(coverage={1: full_coverage()})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.build_status.last_error is not None
    assert state.build_status.all_services_ok is False


def test_build_status_flags_provider_returning_nothing():
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({}),
        theses=FakeThesesRepository({}),
        coverage=FakeCoverageRepository({1: full_coverage()}),
        runs=FakeRunRepository({}),
        build_status=FakeBuildStatusProvider(None),
    )
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.build_status.last_error is not None
