from __future__ import annotations

from cios.dashboard.state_builder import DashboardStateBuilder
from cios.dashboard.types import AttentionLevel

from .conftest import (
    FakeBuildStatusProvider,
    FakeCoverageRepository,
    FakePrescriptionsRepository,
    FakeReportHistoryRepository,
    FakeRunRepository,
    FakeSignalsRepository,
    FakeSuppressedSignalsRepository,
    FakeThesesRepository,
    broken_coverage,
    build_status_ok,
    delta,
    full_coverage,
    prescription_row,
    report_row,
    suppressed_row,
    thesis,
)


def make_builder(
    *,
    signals=None,
    theses=None,
    coverage=None,
    runs=None,
    build_status=None,
    report_history=None,
    suppressed_signals=None,
    prescriptions=None,
) -> DashboardStateBuilder:
    return DashboardStateBuilder(
        signals=FakeSignalsRepository(signals or {}),
        theses=FakeThesesRepository(theses or {}),
        coverage=FakeCoverageRepository(coverage or {}),
        runs=FakeRunRepository(runs or {}),
        build_status=FakeBuildStatusProvider(build_status) if build_status is not None else None,
        report_history=FakeReportHistoryRepository(report_history) if report_history is not None else None,
        suppressed_signals=FakeSuppressedSignalsRepository(suppressed_signals) if suppressed_signals is not None else None,
        prescriptions=FakePrescriptionsRepository(prescriptions) if prescriptions is not None else None,
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
    # Bug-4 fix: level now derives from the composite score (materiality +
    # capped volume + capped evidence breadth), not raw materiality alone.
    # A single delta/single evidence url at materiality 0.9 composites to
    # 50/100 -> "watch", not "act_now" (which now requires more
    # corroboration than one lone signal).
    assert state.top_attention_level == AttentionLevel.WATCH


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
    # Bug-4 fix: see comment in test_competitor_cards_are_materiality_ranked_descending.
    assert state.competitor_cards[0].attention_level == AttentionLevel.WATCH


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


# -- report history + suppressed signals -------------------------------------


def test_report_history_empty_when_no_provider_injected():
    builder = make_builder(coverage={1: full_coverage()})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.report_history == []


def test_report_history_populated_from_repo():
    builder = make_builder(
        coverage={1: full_coverage()},
        report_history={1: [report_row(id=1), report_row(id=2, cadence="weekly")]},
    )
    state = builder.build(tenant_id=1, cadence="daily")
    assert [r.report_id for r in state.report_history] == [1, 2]
    assert state.report_history[0].status == "rendered"
    assert state.report_history[1].cadence == "weekly"


def test_report_history_is_tenant_scoped():
    builder = make_builder(
        coverage={1: full_coverage(), 2: full_coverage()},
        report_history={1: [report_row(id=1)], 2: [report_row(id=2)]},
    )
    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=2, cadence="daily")
    assert [r.report_id for r in state1.report_history] == [1]
    assert [r.report_id for r in state2.report_history] == [2]


def test_suppressed_signals_empty_when_no_provider_injected():
    builder = make_builder(coverage={1: full_coverage()})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.suppressed_signals == []


def test_suppressed_signals_populated_from_repo():
    builder = make_builder(
        coverage={1: full_coverage()},
        suppressed_signals={1: [suppressed_row(id=1, finding_ids=[1, 2, 3])]},
    )
    state = builder.build(tenant_id=1, cadence="daily")
    assert len(state.suppressed_signals) == 1
    assert state.suppressed_signals[0].finding_count == 3
    assert state.suppressed_signals[0].reason == "Below materiality threshold"


# -- cross-run signal dedup (task #25 root-cause fix) ------------------------


def _dupe_delta(**overrides) -> dict:
    base = delta(**{k: v for k, v in overrides.items() if k != "what_changed"})
    if "what_changed" in overrides:
        base["what_changed"] = overrides["what_changed"]
    return base


def test_same_story_same_competitor_merges_into_one_card_with_count_badge():
    signals = {
        1: [
            _dupe_delta(id=1, competitor_id=1, materiality_score=0.6,
                        what_changed="Heap rebrands as Contentsquare product", evidence_ids=["https://a.com"]),
            _dupe_delta(id=2, competitor_id=1, materiality_score=0.8,
                        what_changed="Heap now brands its product as Contentsquare", evidence_ids=["https://b.com"]),
            _dupe_delta(id=3, competitor_id=1, materiality_score=0.7,
                        what_changed="Heap has rebranded its product as Contentsquare", evidence_ids=["https://c.com"]),
        ]
    }
    builder = make_builder(coverage={1: full_coverage()}, signals=signals)
    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.competitor_cards) == 1
    card = state.competitor_cards[0]
    assert card.duplicate_count == 3
    # highest-materiality member's fields win.
    assert card.materiality_score == 0.8
    # evidence is unioned across all merged members, nothing dropped.
    assert set(card.evidence_ids) == {"https://a.com", "https://b.com", "https://c.com"}


def test_different_stories_same_competitor_stay_separate_cards():
    signals = {
        1: [
            _dupe_delta(id=1, competitor_id=1, materiality_score=0.6,
                        what_changed="Heap rebrands as Contentsquare product"),
            _dupe_delta(id=2, competitor_id=1, materiality_score=0.5,
                        what_changed="Heap lays off part of its engineering team"),
        ]
    }
    builder = make_builder(coverage={1: full_coverage()}, signals=signals)
    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.competitor_cards) == 2
    assert all(c.duplicate_count == 1 for c in state.competitor_cards)


# -- Bug 4: composite attention score (materiality alone was degenerate) ----


def test_same_top_materiality_but_more_signals_and_evidence_scores_higher():
    # Competitor 1: one signal, one evidence url, materiality 0.8.
    # Competitor 2: same top materiality (0.8), but three signals (two of
    # them distinct stories, so they don't cluster-merge with the top one)
    # and more distinct evidence urls. Under the old formula
    # (materiality * 100) both would score identically (80/80) -- the
    # composite score must differentiate them.
    signals = {
        1: [
            delta(id=1, competitor_id=1, materiality_score=0.8,
                  evidence_ids=["https://rival-a.com/pricing"]),
        ],
        2: [
            delta(id=2, competitor_id=2, materiality_score=0.8,
                  evidence_ids=["https://rival-b.com/pricing"]),
            delta(id=3, competitor_id=2, materiality_score=0.4,
                  recommended_action="Track the new hire.",
                  evidence_ids=["https://rival-b.com/careers"]),
            delta(id=4, competitor_id=2, materiality_score=0.3,
                  recommended_action="Track the feature launch.",
                  evidence_ids=["https://rival-b.com/blog"]),
        ],
    }
    signals[2][1]["what_changed"] = "Rival B hires a new VP of Product."
    signals[2][1]["why_it_matters"] = "Signals a product-org shakeup."
    signals[2][2]["what_changed"] = "Rival B ships a new search feature."
    signals[2][2]["why_it_matters"] = "Directly overlaps our roadmap."

    builder = make_builder(coverage={1: full_coverage(), 2: full_coverage()}, signals=signals)
    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=2, cadence="daily")

    card1 = state1.competitor_cards[0]
    # Competitor 2's top-materiality card (the 0.8 one).
    card2 = next(c for c in state2.competitor_cards if c.materiality_score == 0.8)

    assert card1.materiality_score == card2.materiality_score == 0.8
    assert card1.attention_score != card2.attention_score
    assert card2.attention_score > card1.attention_score
    assert 0 <= card1.attention_score <= 100
    assert 0 <= card2.attention_score <= 100


def test_signal_volume_contribution_is_capped():
    # A competitor spamming signals must not blow past the 30%-weight,
    # 10-signal cap on the volume component.
    def _distinct_delta(i: int) -> dict:
        row = delta(id=i, competitor_id=1, materiality_score=0.8,
                     evidence_ids=[f"https://rival.com/{i}"])
        row["what_changed"] = f"Distinct story number {i} happens."
        return row

    many_signals = {1: [_distinct_delta(i) for i in range(1, 21)]}
    fewer_signals = {1: [_distinct_delta(i) for i in range(1, 11)]}
    builder_many = make_builder(coverage={1: full_coverage()}, signals=many_signals)
    builder_fewer = make_builder(coverage={1: full_coverage()}, signals=fewer_signals)
    state_many = builder_many.build(tenant_id=1, cadence="daily")
    state_fewer = builder_fewer.build(tenant_id=1, cadence="daily")
    top_many = max(c.attention_score for c in state_many.competitor_cards)
    top_fewer = max(c.attention_score for c in state_fewer.competitor_cards)
    # 20 signals must not outscore 10 signals -- the cap makes them equal.
    assert top_many == top_fewer


# -- prescription competitor attribution (barometer-filters-lenses fix) -----


def test_prescription_is_attributed_to_the_competitor_whose_evidence_it_shares():
    signals = {
        1: [
            delta(id=1, competitor_id=7, competitor_name="Coveo",
                  evidence_ids=["https://coveo.com/pricing"]),
        ]
    }
    prescriptions = {
        1: [prescription_row(evidence_urls=["https://coveo.com/pricing"])],
    }
    builder = make_builder(coverage={1: full_coverage()}, signals=signals, prescriptions=prescriptions)
    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.prescriptions) == 1
    play = state.prescriptions[0]
    assert play.competitor_id == 7
    assert play.competitor_name == "Coveo"


def test_prescription_with_no_matching_evidence_is_honestly_unattributed():
    signals = {1: [delta(id=1, competitor_id=7, evidence_ids=["https://coveo.com/pricing"])]}
    prescriptions = {1: [prescription_row(evidence_urls=["https://unrelated.example.com/post"])]}
    builder = make_builder(coverage={1: full_coverage()}, signals=signals, prescriptions=prescriptions)
    state = builder.build(tenant_id=1, cadence="daily")

    assert state.prescriptions[0].competitor_id is None
    assert state.prescriptions[0].competitor_name is None


def test_prescription_carries_effort_and_materiality_through():
    prescriptions = {1: [prescription_row(effort="L", materiality_score=0.42)]}
    builder = make_builder(coverage={1: full_coverage()}, prescriptions=prescriptions)
    state = builder.build(tenant_id=1, cadence="daily")

    assert state.prescriptions[0].effort == "L"
    assert state.prescriptions[0].materiality_score == 0.42


def test_different_stories_same_competitor_never_merge():
    signals = {
        1: [
            _dupe_delta(id=1, competitor_id=1, materiality_score=0.6,
                        what_changed="Launches a new AI search feature"),
            _dupe_delta(id=2, competitor_id=2, materiality_score=0.6,
                        what_changed="Launches a new AI search feature"),
        ]
    }
    builder = make_builder(coverage={1: full_coverage()}, signals=signals)
    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.competitor_cards) == 2
    assert {c.competitor_id for c in state.competitor_cards} == {1, 2}
    assert all(c.duplicate_count == 1 for c in state.competitor_cards)


def test_cards_merge_llm_paraphrases_of_same_story():
    """Regression for the 2026-07-08 live brief page: three LLM paraphrases
    of the same Elastic 'context engineering' story (and two of the same
    Gartner MQ story) shipped as five separate cards. The cluster text mixed
    what_changed with the highly variable why_it_matters, diluting Jaccard
    similarity to ~0.3 and defeating dedup. Same-story paraphrases must
    merge into one card, distinct stories must stay separate."""
    paraphrase = (
        "Elastic currently promotes 'context engineering for AI agents' as a "
        "primary Elasticsearch use case, framing the product as infrastructure "
        "that delivers 'the most relevant context to agents so that they "
        "deliver accurate and trusted outcomes.'"
    )
    paraphrase2 = (
        "Elastic currently promotes a dedicated 'context engineering' "
        "capability across its Elasticsearch product pages, framing the "
        "platform as infrastructure that delivers 'the most relevant context "
        "to agents so that they deliver accurate and trusted outcomes.'"
    )
    paraphrase3 = (
        "Elastic currently positions a dedicated 'context engineering' "
        "capability, framing Elasticsearch as infrastructure that delivers "
        "'the most relevant context to agents so that they deliver accurate "
        "and trusted outcomes.' This is surfaced prominently across their "
        "product pages."
    )
    gartner = (
        "Elastic is currently positioned as a Leader in the 2025 Gartner "
        "Magic Quadrant for Observability Platforms for the second "
        "consecutive year, and separately claims Forrester Wave Leader "
        "status for Q2 2025."
    )
    whys = [
        "Positions Elastic against retrieval rivals in the agent stack conversation.",
        "A category framing shift that could reset evaluation criteria for buyers comparing search vendors.",
        "Signals sustained marketing investment behind the agent-infrastructure narrative.",
        "Analyst placement strengthens their enterprise credibility with observability buyers.",
    ]
    deltas = [
        {"id": i, "competitor_id": 5, "competitor_name": "Elastic",
         "what_changed": wc, "why_it_matters": why,
         "materiality_score": 0.8 - i * 0.01, "evidence_ids": [i]}
        for i, (wc, why) in enumerate(zip([paraphrase, paraphrase2, paraphrase3, gartner], whys))
    ]
    builder = make_builder(signals={1: deltas}, coverage={})
    state = builder.build(tenant_id=1, cadence="daily")
    assert len(state.competitor_cards) == 2
    counts = sorted(c.duplicate_count for c in state.competitor_cards)
    assert counts == [1, 3]


def test_theses_merge_paraphrases_of_same_hypothesis():
    """Regression for the 2026-07-08 live brief page: the Living Theses
    section showed the same Elastic 'context engineering repositioning'
    hypothesis six-plus times in slightly different words. _build_theses had
    no dedup at all. Paraphrases of one hypothesis (same competitor) must
    merge into one thesis, keeping the highest-confidence wording and
    unioning evidence counts; distinct hypotheses stay separate."""
    theses = {
        1: [
            thesis(id=1, competitor_id=5, competitor_name="Elastic", confidence=0.5,
                   text="Elastic is reframing search infrastructure as the retrieval layer for AI agents, signaling that context engineering will become a contested battleground.",
                   supporting=2),
            thesis(id=2, competitor_id=5, competitor_name="Elastic", confidence=0.8,
                   text="Elastic is repositioning search infrastructure as the retrieval layer for agents, and context engineering will become the contested battleground for that layer.",
                   supporting=3),
            thesis(id=3, competitor_id=5, competitor_name="Elastic", confidence=0.6,
                   text="Elastic is pivoting from search-for-humans to retrieval-for-agents, positioning Elasticsearch as AI infrastructure.",
                   supporting=1),
        ]
    }
    builder = make_builder(coverage={1: full_coverage()}, theses=theses)
    state = builder.build(tenant_id=1, cadence="daily")
    # theses 1 and 2 are one hypothesis; 3 is related but distinct wording --
    # at minimum the 1/2 pair must merge.
    texts = [t.thesis for t in state.theses]
    assert len(state.theses) < 3
    # highest-confidence wording is kept for the merged pair.
    assert any(t.startswith("Elastic is repositioning search infrastructure") for t in texts)
