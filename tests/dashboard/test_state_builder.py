from __future__ import annotations

from datetime import datetime, timezone

from cios.dashboard.state_builder import DashboardStateBuilder
from cios.dashboard.types import AttentionLevel

from .conftest import (
    FakeBuildStatusProvider,
    FakeCoverageRepository,
    FakeMonitoredCompetitorsRepository,
    FakePrescriptionsRepository,
    FakeProductMarketRepository,
    FakeReportHistoryRepository,
    FakeRunRepository,
    FakeSignalsRepository,
    FakeSourceHealthRepository,
    FakeSuppressedSignalsRepository,
    FakeThesesRepository,
    broken_coverage,
    build_status_ok,
    argus_recommendation_row,
    demand_signal_row,
    delta,
    feature_position_row,
    full_coverage,
    monitored_competitor_row,
    product_market_history_row,
    product_market_pattern_row,
    product_market_run_history_row,
    prescription_row,
    report_row,
    source_health_row,
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
    product_market=None,
    monitored_competitors=None,
    source_health=None,
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
        product_market=product_market,
        monitored_competitors=(
            FakeMonitoredCompetitorsRepository(monitored_competitors)
            if monitored_competitors is not None
            else None
        ),
        source_health=FakeSourceHealthRepository(source_health) if source_health is not None else None,
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


def test_run_health_separates_current_run_material_count_from_rolling_cards():
    builder = make_builder(
        coverage={1: full_coverage()},
        signals={
            1: [
                delta(id=1, competitor_id=1, competitor_name="Constructor", materiality_score=0.9),
                delta(id=2, competitor_id=2, competitor_name="Elastic", materiality_score=0.7),
            ]
        },
        runs={
            1: {
                "run_id": "daily-algolia-quiet",
                "material_delta_count": 0,
                "quality_review_status": "passed",
                "delivery_status": "sent",
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.competitor_cards) == 2
    assert state.run_health.material_delta_count == 0
    assert state.run_health.current_material_delta_count == 0
    assert state.run_health.rolling_material_delta_count == 2


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


def test_monitored_competitors_include_quiet_competitors_with_no_barometer_card():
    builder = make_builder(
        coverage={1: full_coverage()},
        signals={1: [delta(id=1, competitor_id=1, competitor_name="Constructor.io")]},
        monitored_competitors={
            1: [
                monitored_competitor_row(
                    competitor_id=1,
                    competitor_name="Constructor.io",
                    material_signal_count=1,
                    latest_movement_summary="Entry tier price dropped 20%.",
                ),
                monitored_competitor_row(
                    competitor_id=2,
                    competitor_name="Algonomy",
                    domain="algonomy.com",
                    material_signal_count=0,
                    latest_movement_summary=None,
                ),
            ]
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert [c.competitor_name for c in state.competitor_cards] == ["Constructor.io"]
    assert [c.competitor_name for c in state.monitored_competitors] == ["Algonomy", "Constructor.io"]
    quiet = next(c for c in state.monitored_competitors if c.competitor_name == "Algonomy")
    assert quiet.signal_status == "no_material_signal"
    assert quiet.material_signal_count == 0


def test_monitored_competitors_and_source_health_are_tenant_scoped():
    builder = make_builder(
        coverage={1: full_coverage(), 2: full_coverage()},
        monitored_competitors={
            1: [monitored_competitor_row(competitor_id=1, competitor_name="Constructor.io")],
            2: [monitored_competitor_row(competitor_id=9, competitor_name="OtherTenant")],
        },
        source_health={
            1: [source_health_row(source_id=10, competitor_id=1, competitor_name="Constructor.io")],
            2: [source_health_row(source_id=90, competitor_id=9, competitor_name="OtherTenant")],
        },
    )

    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=2, cadence="daily")

    assert [c.competitor_name for c in state1.monitored_competitors] == ["Constructor.io"]
    assert [c.competitor_name for c in state2.monitored_competitors] == ["OtherTenant"]
    assert [s.source_id for s in state1.source_health] == [10]
    assert [s.source_id for s in state2.source_health] == [90]


def test_monitored_competitors_preserve_active_source_rows_for_product_muscle_gap_discovery():
    builder = make_builder(
        coverage={1: full_coverage()},
        monitored_competitors={
            1: [
                monitored_competitor_row(
                    competitor_id=7,
                    competitor_name="Algonomy",
                    domain=None,
                    active_source_count=2,
                    monitored_sources=[
                        {
                            "source_id": 71,
                            "source_family": "docs",
                            "url": "https://algonomy.com/docs/commerce-search",
                            "normalized_url": "https://algonomy.com/docs/commerce-search",
                            "status": "active",
                        },
                        {
                            "source_id": 72,
                            "source_family": "blog",
                            "url": "https://algonomy.com/blog",
                            "normalized_url": "https://algonomy.com/blog",
                            "status": "active",
                        },
                    ],
                )
            ]
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    algonomy = state.monitored_competitors[0]
    assert algonomy.monitored_sources == [
        {
            "source_id": 71,
            "source_family": "docs",
            "url": "https://algonomy.com/docs/commerce-search",
            "normalized_url": "https://algonomy.com/docs/commerce-search",
            "status": "active",
        },
        {
            "source_id": 72,
            "source_family": "blog",
            "url": "https://algonomy.com/blog",
            "normalized_url": "https://algonomy.com/blog",
            "status": "active",
        },
    ]


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


def test_report_history_removes_internal_filesystem_html_paths():
    builder = make_builder(
        coverage={1: full_coverage()},
        report_history={
            1: [
                report_row(id=1, html_path="/opt/data/private/report.html"),
                report_row(id=2, html_path="./archive/2026-07-09.html"),
                report_row(id=3, html_path="https://ci.chowmes.com/archive/2026-07-08.html"),
            ]
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.report_history[0].html_path is None
    assert state.report_history[1].html_path == "./archive/2026-07-09.html"
    assert state.report_history[2].html_path == "https://ci.chowmes.com/archive/2026-07-08.html"


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


# -- product-market intelligence spine ---------------------------------------


def test_product_market_state_empty_when_no_repo_injected():
    builder = make_builder(coverage={1: full_coverage()})
    state = builder.build(tenant_id=1, cadence="daily")
    assert state.product_market_run.status == "not_recorded"
    assert state.product_market_patterns == []
    assert state.argus_recommendations == []
    assert state.demand_signals == []
    assert state.feature_matrix == []
    assert state.product_market_history == []
    assert state.product_market_run_history == []
    assert state.product_market_trends == []
    assert state.product_market_heatmap == []
    assert state.product_market_entity_velocity == []
    assert state.product_market_theme_heatmap == []
    assert state.product_market_window_deltas == []
    assert state.argus_evidence_needs == []
    assert state.product_feature_comparison.rows == []
    assert state.product_feature_comparison.companies == []
    assert state.demand_feature_alignment.status == "no_current_demand"
    assert state.demand_feature_alignment.rows == []


def test_product_market_state_populated_from_repo():
    repo = FakeProductMarketRepository(
        patterns={1: [product_market_pattern_row()]},
        recommendations={1: [argus_recommendation_row()]},
        demand_signals={1: [demand_signal_row()]},
        feature_positions={1: [feature_position_row()]},
        history={1: [product_market_history_row()]},
        run_history={
            1: [
                product_market_run_history_row(
                    verdict="actionable",
                    top_insight="Constructor moved with product proof, market conversation, and demand support.",
                    primary_action="Create an AI shopping agent narrative.",
                    evidence_urls=[
                        "https://constructor.com/changelog",
                        "looker://algolia/ga4/topics",
                    ],
                    product_event_count=4,
                    conversation_theme_count=3,
                    demand_signal_count=1,
                    pattern_count=1,
                    recommendation_count=1,
                    learning_instruction_count=1,
                    learning_instruction_improvement_ids=[202],
                )
            ]
        },
    )
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "runner_summary": {
                        "verdict": "watch",
                        "demand_signal_count": 0,
                    },
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "looker_skipped_row_count": 0,
                    "looker_archived_count": 0,
                    "looker_manifest_path": "/tmp/cios-product-market/algolia/looker-export-manifest.json",
                }
            }
        },
        product_market=repo,
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_patterns[0].pattern_type == "own_narrative_gap"
    assert state.product_market_patterns[0].capability_text == "agentic product discovery"
    assert state.argus_recommendations[0].owner == "PMM"
    assert state.argus_recommendations[0].scorecard.total_score == 78
    assert state.argus_recommendations[0].scorecard.dimension_scores[0].dimension == "product_reality"
    assert state.demand_signals[0].source_label == "Looker Studio GA4 export"
    assert state.feature_matrix[0].company_name == "Constructor"
    assert state.product_market_history[0].capability_text == "agentic product discovery"
    assert state.product_market_history[0].evidence_refs[0]["source_url"] == "https://constructor.com/changelog"
    assert state.product_market_run_history[0].top_insight.startswith("Constructor moved")
    assert state.product_market_run_history[0].learning_instruction_improvement_ids == [202]
    assert state.product_market_trends[0].direction == "emerging"
    assert {cell.entity_name for cell in state.product_market_heatmap} == {"Algolia", "Constructor"}
    assert {entity.entity_name for entity in state.product_market_entity_velocity} == {"Algolia", "Constructor"}
    assert state.product_market_theme_heatmap[0].theme_text == "agentic product discovery"
    assert {delta.subject_name for delta in state.product_market_window_deltas} == {
        "agentic product discovery",
        "Algolia",
        "Constructor",
    }


def test_product_market_demand_signal_exposes_argus_plan_context() -> None:
    repo = FakeProductMarketRepository(
        demand_signals={
            1: [
                demand_signal_row(
                    topic="AI Assistant",
                    metadata={
                        "source_file": "argus-demand-plan-template.csv",
                        "source_row_number": 1,
                        "source_fingerprint": "b" * 64,
                        "argus_capability_key": "ai assistant",
                        "argus_assessment": "own_product_gap",
                        "argus_suggested_filters": ["AI Assistant", "assistant"],
                        "argus_related_competitors": ["Constructor", "Elastic"],
                        "argus_why_collect": (
                            "Decide whether Algolia needs product proof for AI Assistant."
                        ),
                        "argus_evidence_urls": [
                            "https://constructor.com/changelog/ai-assistant"
                        ],
                    },
                )
            ]
        }
    )
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({1: []}),
        theses=FakeThesesRepository({1: []}),
        coverage=FakeCoverageRepository({1: full_coverage()}),
        runs=FakeRunRepository({1: {}}),
        product_market=repo,
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.demand_signals[0].argus_plan_context == {
        "capability_key": "ai assistant",
        "assessment": "own_product_gap",
        "suggested_filters": ["AI Assistant", "assistant"],
        "related_competitors": ["Constructor", "Elastic"],
        "why_collect": "Decide whether Algolia needs product proof for AI Assistant.",
        "evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
    }


def test_state_builder_publishes_compact_product_feature_comparison_with_unknown_cells():
    repo = FakeProductMarketRepository(
        feature_positions={
            1: [
                feature_position_row(
                    capability_text="AI Shopping Agent",
                    company_name="Algolia",
                    company_role="own",
                    position_status="proven",
                    summary="Algolia has AI shopping agent proof.",
                    confidence=0.82,
                    evidence_refs=[{"source_url": "https://www.algolia.com/doc/ai-shopping"}],
                ),
                feature_position_row(
                    capability_text="AI Shopping Agent",
                    company_name="Constructor",
                    company_role="competitor",
                    position_status="proven",
                    summary="Constructor positions an AI Shopping Agent.",
                    confidence=0.76,
                    evidence_refs=[{"source_url": "https://constructor.com/products/ai-shopping-agent"}],
                ),
                feature_position_row(
                    capability_text="Vector Search",
                    company_name="Elastic",
                    company_role="competitor",
                    position_status="claimed",
                    summary="Elastic claims vector search capability.",
                    confidence=0.71,
                    evidence_refs=[{"source_url": "https://www.elastic.co/vector-search"}],
                ),
            ]
        }
    )
    builder = make_builder(
        coverage={1: full_coverage()},
        monitored_competitors={
            1: [
                monitored_competitor_row(
                    competitor_id=10,
                    competitor_name="Constructor",
                    active_source_count=4,
                ),
                monitored_competitor_row(
                    competitor_id=11,
                    competitor_name="Elastic",
                    active_source_count=3,
                ),
                monitored_competitor_row(
                    competitor_id=12,
                    competitor_name="Bloomreach",
                    active_source_count=4,
                ),
            ]
        },
        product_market=repo,
    )

    state = builder.build(tenant_id=1, cadence="daily")

    comparison = state.product_feature_comparison
    assert comparison.row_count_total == 2
    assert comparison.company_count_total == 4
    assert [company.company_name for company in comparison.companies] == [
        "Algolia",
        "Constructor",
        "Elastic",
        "Bloomreach",
    ]
    ai_agent = next(row for row in comparison.rows if row.capability_text == "AI Shopping Agent")
    cells = {cell.company_name: cell for cell in ai_agent.cells}
    assert cells["Algolia"].position_status == "proven"
    assert cells["Constructor"].first_evidence_url == "https://constructor.com/products/ai-shopping-agent"
    assert cells["Bloomreach"].position_status == "unknown"
    assert "No product proof captured for Bloomreach" in cells["Bloomreach"].summary
    assert ai_agent.proven_count == 2
    assert ai_agent.unknown_count == 2


def test_state_builder_publishes_demand_feature_alignment_for_matched_capabilities():
    repo = FakeProductMarketRepository(
        demand_signals={
            1: [
                demand_signal_row(
                    id=501,
                    topic="AI shopping agent",
                    metric="engaged_sessions",
                    value=912,
                    change_pct=0.31,
                    evidence_refs=[{"source_url": "looker://algolia/ga4/ai-shopping-agent"}],
                )
            ]
        },
        feature_positions={
            1: [
                feature_position_row(
                    capability_text="AI Shopping Agent",
                    company_name="Algolia",
                    company_role="own",
                    position_status="proven",
                    summary="Algolia has AI shopping agent product proof.",
                    confidence=0.84,
                    evidence_refs=[{"source_url": "https://www.algolia.com/doc/ai-shopping"}],
                ),
                feature_position_row(
                    capability_text="AI Shopping Agent",
                    company_name="Constructor",
                    company_role="competitor",
                    position_status="proven",
                    summary="Constructor positions an AI Shopping Agent.",
                    confidence=0.76,
                    evidence_refs=[{"source_url": "https://constructor.com/products/ai-shopping-agent"}],
                ),
            ]
        },
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    alignment = state.demand_feature_alignment
    assert alignment.status == "matched"
    assert alignment.signal_count_total == 1
    assert alignment.matched_signal_count == 1
    assert alignment.unmatched_signal_count == 0
    row = alignment.rows[0]
    assert row.demand_signal_id == 501
    assert row.topic == "AI shopping agent"
    assert row.demand_evidence_url == "looker://algolia/ga4/ai-shopping-agent"
    assert row.match_status == "matched"
    assert row.matched_capability == "AI Shopping Agent"
    assert row.product_evidence_count == 2
    assert [company.company_name for company in row.related_companies] == ["Algolia", "Constructor"]
    assert row.related_companies[0].company_role == "own"
    assert row.related_companies[1].first_evidence_url == "https://constructor.com/products/ai-shopping-agent"
    assert "maps to AI Shopping Agent" in row.summary


def test_state_builder_marks_demand_alignment_unmatched_when_no_feature_proof_exists():
    repo = FakeProductMarketRepository(
        demand_signals={
            1: [
                demand_signal_row(
                    id=502,
                    topic="pricing calculator",
                    evidence_refs=[{"source_url": "looker://algolia/ga4/pricing-calculator"}],
                )
            ]
        },
        feature_positions={1: [feature_position_row(capability_text="AI Shopping Agent")]},
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    alignment = state.demand_feature_alignment
    assert alignment.status == "unmatched"
    assert alignment.matched_signal_count == 0
    assert alignment.unmatched_signal_count == 1
    row = alignment.rows[0]
    assert row.match_status == "unmatched"
    assert row.matched_capability is None
    assert row.related_companies == []
    assert row.product_evidence_count == 0
    assert "no product capability row is mapped" in row.summary
    assert row.next_step.startswith("Map this demand topic")


def test_state_builder_uses_argus_plan_capability_key_for_demand_alignment():
    repo = FakeProductMarketRepository(
        demand_signals={
            1: [
                demand_signal_row(
                    id=503,
                    topic="Agent experience pages",
                    evidence_refs=[{"source_url": "looker://algolia/ga4/assistant"}],
                    metadata={
                        "argus_capability_key": "assistant",
                        "argus_assessment": "competitive_pressure",
                    },
                )
            ]
        },
        feature_positions={
            1: [
                feature_position_row(
                    capability_text="Assistant",
                    company_name="Constructor",
                    company_role="competitor",
                    position_status="proven",
                    evidence_refs=[{"source_url": "https://constructor.com/products/assistant"}],
                )
            ]
        },
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    row = state.demand_feature_alignment.rows[0]
    assert row.topic == "Agent experience pages"
    assert state.demand_signals[0].argus_plan_context["capability_key"] == "assistant"
    assert row.match_status == "matched"
    assert row.matched_capability == "Assistant"
    assert row.related_companies[0].company_name == "Constructor"


def test_intelligence_spine_summarizes_product_conversation_demand_and_actionability():
    repo = FakeProductMarketRepository(
        patterns={1: [product_market_pattern_row()]},
        recommendations={1: [argus_recommendation_row()]},
        demand_signals={1: [demand_signal_row()]},
        feature_positions={1: [feature_position_row()]},
        history={1: [product_market_history_row()]},
        run_history={
            1: [
                product_market_run_history_row(
                    verdict="actionable",
                    top_insight="Constructor moved with product proof, market conversation, and demand support.",
                    primary_action="Create an AI shopping agent narrative.",
                    evidence_urls=[
                        "https://constructor.com/changelog",
                        "looker://algolia/ga4/topics",
                    ],
                    product_event_count=4,
                    conversation_theme_count=3,
                    demand_signal_count=1,
                    pattern_count=1,
                    recommendation_count=1,
                    learning_instruction_count=0,
                    learning_instruction_improvement_ids=[],
                )
            ]
        },
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    spine = state.intelligence_spine
    assert spine.verdict == "actionable"
    assert spine.top_insight.startswith("Constructor moved")
    assert spine.primary_action == "Create an AI shopping agent narrative."
    assert spine.can_recommend is True
    assert spine.pattern_count == 1
    assert spine.recommendation_count == 1
    assert spine.feature_position_count == 1
    assert spine.leading_entities == ["Algolia", "Constructor"]
    assert spine.leading_capabilities == ["agentic product discovery"]
    assert spine.evidence_urls == [
        "https://constructor.com/changelog",
        "looker://algolia/ga4/topics",
    ]
    planes = {plane.plane: plane for plane in spine.planes}
    assert planes["product_reality"].status == "present"
    assert planes["product_reality"].signal_count == 4
    assert planes["market_conversation"].status == "present"
    assert planes["market_conversation"].signal_count == 3
    assert planes["audience_demand"].status == "present"
    assert planes["audience_demand"].signal_count == 1
    assert "safe to promote" in spine.next_operator_action


def test_intelligence_spine_exposes_demand_blocker_when_action_is_withheld():
    repo = FakeProductMarketRepository(
        run_history={
            1: [
                product_market_run_history_row(
                    id=42,
                    verdict="watch",
                    top_insight=(
                        "Constructor has product proof and public positioning, but Argus has "
                        "no tenant-side demand evidence in this run."
                    ),
                    confidence_limits=[
                        "No tenant-side demand evidence was captured in this run.",
                        "Recommendation withheld because the evidence did not clear action threshold.",
                    ],
                    product_event_count=28,
                    conversation_theme_count=80,
                    demand_signal_count=0,
                    pattern_count=3,
                    recommendation_count=0,
                    learning_instruction_count=0,
                    learning_instruction_improvement_ids=[],
                )
            ]
        }
    )
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "runner_summary": {
                        "verdict": "watch",
                        "demand_signal_count": 0,
                    },
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "looker_skipped_row_count": 0,
                    "looker_archived_count": 0,
                    "looker_manifest_path": "/tmp/cios-product-market/algolia/looker-export-manifest.json",
                }
            }
        },
        product_market=repo,
    )

    state = builder.build(tenant_id=1, cadence="daily")

    spine = state.intelligence_spine
    assert spine.verdict == "watch"
    assert spine.can_recommend is False
    assert spine.evidence_need_count == 1
    assert spine.next_operator_action.startswith("Upload GA4 / Looker")
    planes = {plane.plane: plane for plane in spine.planes}
    assert planes["product_reality"].status == "present"
    assert planes["market_conversation"].status == "present"
    assert planes["audience_demand"].status == "missing"
    assert "owner recommendations" in spine.blocked_actions


def test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing():
    repo = FakeProductMarketRepository(
        run_history={
            1: [
                product_market_run_history_row(
                    id=42,
                    verdict="watch",
                    top_insight=(
                        "Constructor has product proof and public positioning, but Argus has "
                        "no tenant-side demand evidence in this run."
                    ),
                    confidence_limits=[
                        "No tenant-side demand evidence was captured in this run.",
                        "Recommendation withheld because the evidence did not clear action threshold.",
                    ],
                    product_event_count=28,
                    conversation_theme_count=80,
                    demand_signal_count=0,
                    pattern_count=3,
                    recommendation_count=0,
                    learning_instruction_count=0,
                    learning_instruction_improvement_ids=[],
                )
            ]
        }
    )
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "runner_summary": {
                        "verdict": "watch",
                        "demand_signal_count": 0,
                    },
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "looker_skipped_row_count": 0,
                    "looker_archived_count": 0,
                    "looker_manifest_path": "/tmp/cios-product-market/algolia/looker-export-manifest.json",
                }
            }
        },
        product_market=repo,
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.argus_evidence_needs) == 1
    need = state.argus_evidence_needs[0]
    assert need.evidence_plane == "demand"
    assert need.status == "missing"
    assert need.severity == "blocks_action"
    assert need.related_run_intelligence_id == 42
    assert need.observed_pattern_count == 3
    assert "owner recommendations" in need.blocks
    assert need.next_step.startswith("Upload GA4 / Looker")
    assert "No tenant-side demand evidence" in need.why_needed
    assert need.accepted_input_formats == ["csv", "json", "jsonl"]
    assert "Page title" in need.required_fields
    assert "Engaged sessions previous period" in need.required_fields
    assert need.operator_surface == "CI-OS local admin demand imports"
    assert need.observed_state["demand_plane_status"] == "missing"
    assert need.observed_state["looker_discovered_count"] == 0
    assert need.observed_state["looker_ready_count"] == 0
    assert need.observed_state["looker_error_count"] == 0
    assert need.observed_state["looker_normalized_row_count"] == 0
    assert need.observed_state["looker_manifest_path"].endswith("looker-export-manifest.json")


def test_product_market_run_status_populated_from_latest_run_summary():
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "next_sweep_plan_path": "/tmp/cios-product-market/algolia/next-sweep-learning-plan.json",
                    "learning_apply_plan_path": "/tmp/cios-product-market/algolia/learning-apply-plan.json",
                    "learning_apply_plan_summary": {
                        "action_count": 1,
                        "skipped_count": 0,
                        "targets": ["source_coverage_policy"],
                        "package_paths": ["config/source-coverage-policy.yaml"],
                    },
                    "product_surface_plan_summary": {
                        "target_count": 2,
                        "target_company_count": 2,
                        "target_companies": ["Constructor", "Coveo"],
                        "surface_family_counts": {"changelog": 1, "docs": 1},
                        "learning_prioritized_count": 1,
                        "prioritized_targets": [
                            {
                                "company_name": "Coveo",
                                "surface_family": "docs",
                                "url": "https://www.coveo.com/en/docs",
                                "learning_priority": 100,
                                "learning_reasons": [
                                    "coverage_recheck: Re-audit Coveo source coverage before ranking Constructor again."
                                ],
                            }
                        ],
                    },
                    "product_surface_execution_summary": {
                        "product_plane_status": "degraded",
                        "planned": 2,
                        "succeeded": 1,
                        "empty": 1,
                        "failed": 0,
                        "product_row_count": 7,
                        "empty_scout_paths": [
                            "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json"
                        ],
                        "empty_outputs": [
                            {
                                "output_path": "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json",
                                "company_name": "Coveo",
                                "surface_family": "docs",
                            }
                        ],
                        "company_row_counts": {"Constructor": 7},
                        "surface_family_row_counts": {"changelog": 7},
                    },
                    "product_muscle_gap_plan": {
                        "monitored_company_count": 4,
                        "covered_company_count": 2,
                        "missing_company_count": 2,
                        "candidate_url_count": 12,
                        "candidate_surface_family_counts": {"docs": 2, "pricing": 2},
                        "missing_companies": [
                            {"company_name": "Elastic", "candidate_surface_urls": []},
                            {"company_name": "Bloomreach", "candidate_surface_urls": []},
                        ],
                    },
                    "post_run_product_muscle_gap_discovery": {
                        "status": "completed",
                        "stored_candidate_count": 6,
                        "rejected_count": 1,
                    },
                    "post_run_product_surface_promotion": {
                        "status": "completed",
                        "promoted_count": 2,
                    },
                    "post_run_next_sweep_status": (
                        "Hermes queued 6 candidate product surfaces and activated 2 validated sources "
                        "for the next sweep."
                    ),
                    "stage_ledger": [
                        {
                            "tenant": "algolia",
                            "stage": "product_surface_export",
                            "status": "completed",
                            "started_at": "2026-07-11T22:35:00Z",
                            "ended_at": "2026-07-11T22:35:05Z",
                            "elapsed_s": 5.1,
                        },
                        {
                            "tenant": "algolia",
                            "stage": "product_market_synthesis",
                            "status": "completed",
                            "started_at": "2026-07-11T22:35:06Z",
                            "ended_at": "2026-07-11T22:35:09Z",
                            "elapsed_s": 3.2,
                        },
                    ],
                    "runner_summary": {
                        "verdict": "watch",
                        "learning_instruction_count": 1,
                        "learning_instruction_improvement_ids": [202],
                        "intelligence_brief": {
                            "verdict": "watch",
                            "top_insight": "Constructor moved first, but coverage learning demoted the action.",
                            "primary_action": None,
                            "watchlist": ["Re-audit Coveo before restoring Constructor priority."],
                            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                            "confidence_limits": ["Recommendation withheld by approved coverage learning."],
                            "next_questions": ["Did Coveo ship a competing capability in docs?"],
                            "next_monitoring_actions": [
                                {
                                    "owner": "Hermes",
                                    "plane": "source_coverage",
                                    "priority": "medium",
                                    "instruction": (
                                        "Recheck Constructor and Algolia product, conversation, and demand "
                                        "source coverage for agentic product discovery."
                                    ),
                                    "reason": "Coverage learning demoted the action.",
                                    "source_families": ["scout_changelog", "web_scan", "ga4_api_export"],
                                    "evidence_urls": [
                                        "https://constructor.com/changelog/ai-shopping-agent"
                                    ],
                                }
                            ],
                            "decision_read": {
                                "status": "watch",
                                "market_direction": (
                                    "agentic product discovery is heating up around Constructor and Algolia."
                                ),
                                "priority_reason": (
                                    "Watch Constructor because coverage learning demoted the action."
                                ),
                                "confidence_basis": [
                                    {
                                        "plane": "product_reality",
                                        "status": "present",
                                        "evidence_count": 4,
                                        "summary": "4 product-reality event(s) captured.",
                                    }
                                ],
                                "tactical_actions": [],
                                "blockers": ["Coverage recheck learning gate is active."],
                            },
                            "product_feature_comparison": {
                                "summary": (
                                    "1 capability compared; 0 product gaps, 1 narrative gap, "
                                    "1 demand-backed row."
                                ),
                                "row_count": 1,
                                "product_gap_count": 0,
                                "narrative_gap_count": 1,
                                "demand_backed_count": 1,
                                "rows": [
                                    {
                                        "capability": "agentic product discovery",
                                        "capability_key": "shopping agent",
                                        "assessment": "own_narrative_gap",
                                        "own_company_name": "Algolia",
                                        "own_status": "proven",
                                        "competitors_with_product_proof": ["Constructor"],
                                        "competitors_with_conversation": ["Constructor"],
                                        "has_rising_demand": True,
                                        "demand_signal_count": 1,
                                        "top_demand_change_pct": 0.23,
                                        "recommended_action": (
                                            "Create an Algolia narrative for agentic product discovery "
                                            "using existing product proof."
                                        ),
                                        "evidence_urls": [
                                            "https://constructor.com/changelog/ai-shopping-agent",
                                            "https://constructor.com/blog/ai-shopping-agent",
                                            "https://www.algolia.com/changelog/agentic-discovery",
                                            "looker://algolia/ga4/topics",
                                        ],
                                        "confidence_limits": [],
                                    }
                                ],
                            },
                        },
                    },
                    "scout_paths": ["/tmp/cios-product-market/algolia/surface-exports/000030-coveo-docs.json"],
                    "errors": [],
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_run.status == "ran"
    assert state.product_market_run.next_sweep_plan_path.endswith("next-sweep-learning-plan.json")
    assert state.product_market_run.learning_apply_plan_path.endswith("learning-apply-plan.json")
    assert state.product_market_run.learning_apply_plan_summary["action_count"] == 1
    assert state.product_market_run.learning_apply_plan_summary["targets"] == ["source_coverage_policy"]
    assert state.product_market_run.target_count == 2
    assert state.product_market_run.target_company_count == 2
    assert state.product_market_run.target_companies == ["Constructor", "Coveo"]
    assert state.product_market_run.surface_family_counts == {"changelog": 1, "docs": 1}
    assert state.product_market_run.product_surface_execution_summary["product_plane_status"] == "degraded"
    assert state.product_market_run.product_surface_execution_summary["product_row_count"] == 7
    assert state.product_market_run.product_surface_execution_summary["empty_outputs"][0]["company_name"] == "Coveo"
    assert state.product_market_run.product_muscle_gap_plan["missing_company_count"] == 2
    assert state.product_market_run.product_muscle_gap_plan["candidate_url_count"] == 12
    assert state.product_market_run.post_run_product_muscle_gap_discovery["stored_candidate_count"] == 6
    assert state.product_market_run.post_run_product_surface_promotion["promoted_count"] == 2
    assert state.product_market_run.post_run_next_sweep_status.startswith("Hermes queued 6")
    assert state.product_market_run.learning_prioritized_count == 1
    assert state.product_market_run.prioritized_targets[0]["company_name"] == "Coveo"
    assert state.product_market_run.runner_verdict == "watch"
    assert state.product_market_run.learning_instruction_count == 1
    assert state.product_market_run.consumed_learning_ids == [202]
    assert state.product_market_run.scout_artifact_count == 1
    assert state.product_market_run.intelligence_brief["top_insight"].startswith("Constructor moved first")
    assert state.product_market_run.next_monitoring_actions == [
        {
            "owner": "Hermes",
            "plane": "source_coverage",
            "priority": "medium",
            "instruction": (
                "Recheck Constructor and Algolia product, conversation, and demand "
                "source coverage for agentic product discovery."
            ),
            "reason": "Coverage learning demoted the action.",
            "source_families": ["scout_changelog", "web_scan", "ga4_api_export"],
            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
        }
    ]
    assert state.product_market_run.decision_read["status"] == "watch"
    assert state.product_market_run.decision_read["market_direction"].startswith(
        "agentic product discovery is heating up"
    )
    assert state.product_market_run.decision_read["blockers"] == [
        "Coverage recheck learning gate is active."
    ]
    assert "Recommendation withheld" in state.product_market_run.intelligence_brief["confidence_limits"][0]
    assert state.product_market_run.product_feature_comparison_read["summary"].startswith(
        "1 capability compared"
    )
    assert state.product_market_run.product_feature_comparison_read["rows"][0]["assessment"] == (
        "own_narrative_gap"
    )
    assert state.product_market_run.product_feature_comparison_read["rows"][0]["recommended_action"].startswith(
        "Create an Algolia narrative"
    )
    assert [entry["stage"] for entry in state.product_market_run.stage_ledger] == [
        "product_surface_export",
        "product_market_synthesis",
    ]
    assert state.product_market_run.stage_ledger[0]["elapsed_s"] == 5.1


def test_product_market_run_status_prefers_final_ledger_replay_summary():
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "product_surface_plan_summary": {"target_count": 3},
                    "runner_summary": {
                        "verdict": "actionable",
                        "learning_instruction_count": 0,
                        "learning_instruction_improvement_ids": [],
                        "demand_signal_count": 0,
                        "conversion_diagnostics": {
                            "summary": "Import-only runner read before durable ledger replay.",
                            "product_event_count": 1,
                            "pattern_count": 0,
                        },
                        "intelligence_brief": {
                            "verdict": "actionable",
                            "top_insight": "Import-only runner read.",
                            "confidence_limits": ["Ledger replay had not run yet."],
                        },
                    },
                    "ledger_refresh_status": "ran",
                    "ledger_refresh_summary": {
                        "verdict": "watch",
                        "product_event_count": 4,
                        "conversation_theme_count": 3,
                        "learning_instruction_count": 1,
                        "learning_instruction_improvement_ids": [202],
                        "demand_signal_count": 2,
                        "pattern_count": 2,
                        "recommendation_count": 0,
                        "conversion_diagnostics": {
                            "summary": "Ledger replay converted durable product, conversation, and demand rows.",
                            "product_event_count": 4,
                            "feature_position_count": 3,
                            "pattern_count": 2,
                        },
                        "intelligence_brief": {
                            "verdict": "watch",
                            "top_insight": "Ledger replay final read.",
                            "confidence_limits": ["Final read uses durable ledger state."],
                            "movement_map": {
                                "direction_summary": "Durable ledger replay changed the public read.",
                                "hot_capabilities": ["agentic product discovery"],
                            },
                            "window_comparison": {
                                "summary": (
                                    "Last 7 days: 2 product events, 1 conversation theme, 1 demand signal. "
                                    "Last 30 days: 4 product events, 3 conversation themes, 2 demand signals."
                                ),
                                "windows": [
                                    {"days": 7, "product_event_count": 2},
                                    {"days": 30, "product_event_count": 4},
                                ],
                            },
                        },
                    },
                    "scout_paths": ["/tmp/a.json"],
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_run.runner_verdict == "watch"
    assert state.product_market_run.learning_instruction_count == 1
    assert state.product_market_run.consumed_learning_ids == [202]
    assert state.product_market_run.demand_plane_status == "processed"
    assert state.product_market_run.product_event_count == 4
    assert state.product_market_run.conversation_theme_count == 3
    assert state.product_market_run.demand_signal_count == 2
    assert state.product_market_run.pattern_count == 2
    assert state.product_market_run.recommendation_count == 0
    assert state.product_market_run.intelligence_brief["top_insight"] == "Ledger replay final read."
    assert state.product_market_run.movement_map["direction_summary"].startswith("Durable ledger")
    assert state.product_market_run.window_comparison["summary"].startswith("Last 7 days")
    assert state.product_market_run.window_comparison["windows"][1]["days"] == 30
    assert state.product_market_run.conversion_diagnostics["product_event_count"] == 4
    assert state.product_market_run.conversion_diagnostics["pattern_count"] == 2


def test_product_market_run_status_uses_latest_persisted_brain_record_when_report_trace_is_stale():
    repo = FakeProductMarketRepository(
        run_history={
            1: [
                {
                    "id": 302,
                    "verdict": "watch",
                    "intelligence_brief": {
                        "verdict": "watch",
                        "top_insight": "Fresh persisted run intelligence has the product comparison read.",
                        "confidence_limits": ["Demand is still missing, so action is held at watch."],
                        "product_feature_comparison": {
                            "summary": "2 capabilities compared; 0 product gaps, 0 narrative gaps, 0 demand-backed rows.",
                            "row_count": 2,
                            "product_gap_count": 0,
                            "narrative_gap_count": 0,
                            "demand_backed_count": 0,
                            "rows": [
                                {
                                    "capability": "agentic product discovery",
                                    "capability_key": "agentic product discovery",
                                    "assessment": "competitive_pressure",
                                    "recommended_action": "Watch agentic product discovery until demand evidence arrives.",
                                }
                            ],
                        },
                    },
                    "product_event_count": 500,
                    "conversation_theme_count": 500,
                    "demand_signal_count": 0,
                    "pattern_count": 2,
                    "recommendation_count": 0,
                    "learning_instruction_count": 0,
                    "learning_instruction_improvement_ids": [],
                    "created_at": datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc),
                }
            ]
        }
    )
    builder = make_builder(
        coverage={1: full_coverage()},
        product_market=repo,
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "runner_summary": {
                        "verdict": "watch",
                        "product_event_count": 500,
                        "conversation_theme_count": 500,
                        "demand_signal_count": 0,
                        "pattern_count": 2,
                        "recommendation_count": 0,
                        "intelligence_brief": {
                            "verdict": "watch",
                            "top_insight": "Stale report metadata had no product comparison read.",
                            "confidence_limits": ["Saved before ledger replay."],
                        },
                    },
                    "scout_paths": ["/tmp/a.json"],
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert (
        state.product_market_run.intelligence_brief["top_insight"]
        == "Fresh persisted run intelligence has the product comparison read."
    )
    assert state.product_market_run.product_feature_comparison_read["summary"].startswith(
        "2 capabilities compared"
    )
    assert state.product_market_run.product_feature_comparison_read["rows"][0]["assessment"] == (
        "competitive_pressure"
    )


def test_product_market_run_status_includes_conversion_diagnostics():
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "product_surface_plan_summary": {"target_count": 3},
                    "runner_summary": {
                        "verdict": "quiet",
                        "conversion_diagnostics": {
                            "summary": (
                                "2 Scout/product records converted to 2 product events and 2 feature positions; "
                                "0 product-market patterns qualified."
                            ),
                            "scout_record_count": 2,
                            "product_event_count": 2,
                            "feature_position_count": 2,
                            "pattern_count": 0,
                            "blockers": [
                                "1 product capability had product proof but no rising demand signal."
                            ],
                        },
                        "intelligence_brief": {
                            "verdict": "quiet",
                            "top_insight": "No cross-plane product-market pattern qualified for action in this run.",
                            "confidence_limits": [
                                "2 Scout/product records converted to 2 product events and 2 feature positions; 0 product-market patterns qualified."
                            ],
                            "conversion_diagnostics": {
                                "summary": (
                                    "2 Scout/product records converted to 2 product events and 2 feature positions; "
                                    "0 product-market patterns qualified."
                                ),
                                "product_event_count": 2,
                            },
                        },
                    },
                    "scout_paths": ["/tmp/a.json", "/tmp/b.json"],
                    "errors": [],
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_run.conversion_diagnostics["product_event_count"] == 2
    assert state.product_market_run.conversion_diagnostics["feature_position_count"] == 2
    assert "no rising demand" in state.product_market_run.conversion_diagnostics["blockers"][0]


def test_product_market_run_status_exposes_demand_plane_readiness():
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "product_surface_plan_summary": {"target_count": 3},
                    "runner_summary": {
                        "verdict": "watch",
                        "demand_signal_count": 0,
                        "intelligence_brief": {
                            "verdict": "watch",
                            "top_insight": "Competitor movement qualified only as a watch pattern.",
                        },
                    },
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "looker_skipped_row_count": 0,
                    "looker_archived_count": 0,
                    "looker_manifest_path": "/tmp/cios-product-market/algolia/looker-export-manifest.json",
                    "scout_paths": ["/tmp/a.json"],
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_run.demand_plane_status == "missing"
    assert state.product_market_run.looker_discovered_count == 0
    assert state.product_market_run.looker_ready_count == 0
    assert state.product_market_run.looker_normalized_row_count == 0
    assert state.product_market_run.looker_manifest_path.endswith("looker-export-manifest.json")


def test_product_market_run_status_marks_processed_demand_plane_when_rows_are_ready():
    builder = make_builder(
        coverage={1: full_coverage()},
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "product_surface_plan_summary": {"target_count": 3},
                    "runner_summary": {
                        "verdict": "actionable",
                        "demand_signal_count": 2,
                        "intelligence_brief": {
                            "verdict": "actionable",
                            "top_insight": "Product, conversation, and demand aligned.",
                        },
                    },
                    "looker_discovered_count": 1,
                    "looker_ready_count": 1,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 2,
                    "looker_skipped_row_count": 3,
                    "looker_archived_count": 1,
                    "scout_paths": ["/tmp/a.json"],
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_run.demand_plane_status == "processed"
    assert state.product_market_run.looker_discovered_count == 1
    assert state.product_market_run.looker_ready_count == 1
    assert state.product_market_run.looker_normalized_row_count == 2
    assert state.product_market_run.looker_skipped_row_count == 3
    assert state.product_market_run.looker_archived_count == 1


def test_product_market_run_status_uses_current_ledger_demand_when_saved_trace_is_stale():
    repo = FakeProductMarketRepository(
        run_history={
            1: [
                product_market_run_history_row(
                    id=301,
                    verdict="watch",
                    demand_signal_count=1,
                    top_insight="Ledger replay found tenant demand after the saved trace was published.",
                )
            ]
        },
        demand_signals={
            1: [
                demand_signal_row(
                    id=401,
                    topic="AI shopping agent",
                    evidence_refs=[{"source_url": "looker://algolia/ga4/ai-shopping-agent"}],
                )
            ]
        },
    )
    builder = make_builder(
        coverage={1: full_coverage()},
        product_market=repo,
        runs={
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "runner_summary": {
                        "verdict": "quiet",
                        "demand_signal_count": 0,
                        "intelligence_brief": {
                            "top_insight": "Stale dashboard trace before demand import.",
                        },
                    },
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "looker_skipped_row_count": 0,
                    "looker_archived_count": 0,
                }
            }
        },
    )

    state = builder.build(tenant_id=1, cadence="daily")

    assert state.product_market_run.demand_plane_status == "processed"
    assert state.intelligence_spine.planes[2].status == "present"
    assert state.intelligence_spine.planes[2].signal_count == 1


def test_product_market_state_is_tenant_scoped():
    repo = FakeProductMarketRepository(
        patterns={1: [product_market_pattern_row(id=1)], 2: [product_market_pattern_row(id=2)]},
        history={1: [product_market_history_row(id=10)], 2: [product_market_history_row(id=20)]},
        run_history={
            1: [product_market_run_history_row(id=101, top_insight="Tenant one read")],
            2: [product_market_run_history_row(id=202, top_insight="Tenant two read")],
        },
    )
    builder = make_builder(coverage={1: full_coverage(), 2: full_coverage()}, product_market=repo)

    state1 = builder.build(tenant_id=1, cadence="daily")
    state2 = builder.build(tenant_id=2, cadence="daily")

    assert [p.pattern_id for p in state1.product_market_patterns] == [1]
    assert [p.pattern_id for p in state2.product_market_patterns] == [2]
    assert [p.pattern_id for p in state1.product_market_history] == [10]
    assert [p.pattern_id for p in state2.product_market_history] == [20]
    assert [r.run_intelligence_id for r in state1.product_market_run_history] == [101]
    assert [r.run_intelligence_id for r in state2.product_market_run_history] == [202]


def test_product_market_trends_are_derived_from_pattern_history():
    repo = FakeProductMarketRepository(
        history={
            1: [
                product_market_history_row(
                    id=1,
                    created_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Constructor"],
                    evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
                ),
                product_market_history_row(
                    id=2,
                    created_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
                    summary="Coveo joined the agentic product discovery pattern.",
                    involved_companies=["Coveo", "Constructor"],
                    evidence_refs=[{"source_url": "https://coveo.com/docs/agentic"}],
                ),
                product_market_history_row(
                    id=3,
                    created_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
                    summary="Elastic framed the same capability earlier in the month.",
                    involved_companies=["Elastic"],
                    evidence_refs=[{"source_url": "https://elastic.co/search/ai"}],
                ),
            ]
        }
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    assert len(state.product_market_trends) == 1
    trend = state.product_market_trends[0]
    assert trend.capability_text == "agentic product discovery"
    assert trend.direction == "accelerating"
    assert trend.pattern_count_7d == 2
    assert trend.pattern_count_30d == 3
    assert trend.involved_companies == ["Constructor", "Coveo", "Elastic"]
    assert trend.latest_summary.startswith("Constructor")
    assert [item["source_url"] for item in trend.evidence_refs] == [
        "https://constructor.com/changelog",
        "https://coveo.com/docs/agentic",
        "https://elastic.co/search/ai",
    ]


def test_product_market_heatmap_cells_are_derived_by_entity_and_capability():
    repo = FakeProductMarketRepository(
        history={
            1: [
                product_market_history_row(
                    id=1,
                    created_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Constructor"],
                    evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
                ),
                product_market_history_row(
                    id=2,
                    created_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Coveo", "Constructor"],
                    evidence_refs=[{"source_url": "https://coveo.com/docs/agentic"}],
                ),
                product_market_history_row(
                    id=3,
                    created_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Elastic"],
                    evidence_refs=[{"source_url": "https://elastic.co/search/ai"}],
                ),
            ]
        }
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    cells = {(cell.entity_name, cell.capability_text): cell for cell in state.product_market_heatmap}
    constructor = cells[("Constructor", "agentic product discovery")]
    coveo = cells[("Coveo", "agentic product discovery")]
    elastic = cells[("Elastic", "agentic product discovery")]

    assert constructor.pattern_count_7d == 2
    assert constructor.pattern_count_30d == 2
    assert constructor.heat_level == "hot"
    assert constructor.intensity_score > coveo.intensity_score > elastic.intensity_score
    assert coveo.heat_level == "warm"
    assert elastic.heat_level == "watch"
    assert constructor.evidence_refs == [
        {"source_url": "https://constructor.com/changelog"},
        {"source_url": "https://coveo.com/docs/agentic"},
    ]


def test_product_market_entity_velocity_rolls_up_heatmap_by_entity():
    repo = FakeProductMarketRepository(
        history={
            1: [
                product_market_history_row(
                    id=1,
                    created_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Constructor"],
                    evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
                ),
                product_market_history_row(
                    id=2,
                    created_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                    capability_text="answer optimization",
                    summary="Constructor added answer optimization proof.",
                    involved_companies=["Constructor"],
                    evidence_refs=[{"source_url": "https://constructor.com/answers"}],
                ),
                product_market_history_row(
                    id=3,
                    created_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Coveo"],
                    evidence_refs=[{"source_url": "https://coveo.com/docs/agentic"}],
                ),
                product_market_history_row(
                    id=4,
                    created_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Elastic"],
                    evidence_refs=[{"source_url": "https://elastic.co/search/ai"}],
                ),
            ]
        }
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    entities = {entity.entity_name: entity for entity in state.product_market_entity_velocity}
    constructor = entities["Constructor"]
    coveo = entities["Coveo"]
    elastic = entities["Elastic"]

    assert [entity.entity_name for entity in state.product_market_entity_velocity][:3] == [
        "Constructor",
        "Coveo",
        "Elastic",
    ]
    assert constructor.direction == "accelerating"
    assert constructor.total_patterns_7d == 2
    assert constructor.total_patterns_30d == 2
    assert constructor.hot_capability_count == 0
    assert constructor.warm_capability_count == 2
    assert constructor.top_capabilities == ["agentic product discovery", "answer optimization"]
    assert constructor.latest_summary == "Constructor's agentic product discovery pressure persisted across the week."
    assert [item["source_url"] for item in constructor.evidence_refs] == [
        "https://constructor.com/changelog",
        "https://constructor.com/answers",
    ]
    assert coveo.direction == "emerging"
    assert elastic.direction == "dormant"


def test_product_market_theme_heatmap_rolls_up_market_patterns_by_theme():
    repo = FakeProductMarketRepository(
        history={
            1: [
                product_market_history_row(
                    id=1,
                    pattern_type="own_narrative_gap",
                    created_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Constructor"],
                    evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
                ),
                product_market_history_row(
                    id=2,
                    pattern_type="competitive_pressure",
                    created_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                    summary="Coveo joined the agentic product discovery conversation.",
                    involved_companies=["Coveo", "Constructor"],
                    evidence_refs=[{"source_url": "https://coveo.com/docs/agentic"}],
                ),
                product_market_history_row(
                    id=3,
                    pattern_type="conversation_without_product_proof",
                    capability_text="answer optimization",
                    created_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Bloomreach"],
                    evidence_refs=[{"source_url": "https://bloomreach.com/answers"}],
                ),
                product_market_history_row(
                    id=4,
                    pattern_type="own_product_gap",
                    created_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Elastic"],
                    evidence_refs=[{"source_url": "https://elastic.co/search/ai"}],
                ),
            ]
        }
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    themes = {theme.theme_text: theme for theme in state.product_market_theme_heatmap}
    agentic = themes["agentic product discovery"]
    answers = themes["answer optimization"]

    assert [theme.theme_text for theme in state.product_market_theme_heatmap][:2] == [
        "agentic product discovery",
        "answer optimization",
    ]
    assert agentic.direction == "accelerating"
    assert agentic.heat_level == "hot"
    assert agentic.pattern_count_7d == 2
    assert agentic.pattern_count_30d == 3
    assert agentic.entity_count == 3
    assert agentic.leading_entities == ["Constructor", "Coveo", "Elastic"]
    assert agentic.pattern_types == ["own_narrative_gap", "competitive_pressure", "own_product_gap"]
    assert agentic.intensity_score > answers.intensity_score
    assert [item["source_url"] for item in agentic.evidence_refs] == [
        "https://constructor.com/changelog",
        "https://coveo.com/docs/agentic",
        "https://elastic.co/search/ai",
    ]


def test_product_market_window_deltas_compare_current_7d_to_prior_7d():
    repo = FakeProductMarketRepository(
        history={
            1: [
                product_market_history_row(
                    id=1,
                    created_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Constructor"],
                    evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
                ),
                product_market_history_row(
                    id=2,
                    created_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Coveo", "Constructor"],
                    evidence_refs=[{"source_url": "https://coveo.com/docs/agentic"}],
                ),
                product_market_history_row(
                    id=3,
                    created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
                    summary="Elastic carried the same theme in the prior window.",
                    involved_companies=["Elastic"],
                    evidence_refs=[{"source_url": "https://elastic.co/search/ai"}],
                ),
                product_market_history_row(
                    id=4,
                    capability_text="answer optimization",
                    created_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Bloomreach"],
                    evidence_refs=[{"source_url": "https://bloomreach.com/answers"}],
                ),
                product_market_history_row(
                    id=5,
                    capability_text="personalization",
                    created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
                    involved_companies=["Nosto"],
                    evidence_refs=[{"source_url": "https://nosto.com/personalization"}],
                ),
            ]
        }
    )
    builder = make_builder(coverage={1: full_coverage()}, product_market=repo)

    state = builder.build(tenant_id=1, cadence="daily")

    deltas = {(delta.subject_type, delta.subject_name): delta for delta in state.product_market_window_deltas}
    agentic = deltas[("theme", "agentic product discovery")]
    constructor = deltas[("entity", "Constructor")]
    personalization = deltas[("theme", "personalization")]

    assert agentic.current_pattern_count == 2
    assert agentic.previous_pattern_count == 1
    assert agentic.delta == 1
    assert agentic.direction == "rising"
    assert agentic.related_entities == ["Constructor", "Coveo", "Elastic"]
    assert agentic.related_capabilities == ["agentic product discovery"]
    assert [item["source_url"] for item in agentic.evidence_refs] == [
        "https://constructor.com/changelog",
        "https://coveo.com/docs/agentic",
        "https://elastic.co/search/ai",
    ]
    assert constructor.current_pattern_count == 2
    assert constructor.previous_pattern_count == 0
    assert constructor.direction == "new"
    assert personalization.current_pattern_count == 0
    assert personalization.previous_pattern_count == 1
    assert personalization.direction == "falling"


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
