"""Tests for the Hermes-callable product-market intelligence runner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cios.intelligence.runner import (
    ProductMarketRunPayload,
    load_product_market_payload,
    run_product_market_ledger_refresh,
    run_product_market_payload,
)
from tests.intelligence.test_product_market_workflow import FakeProductMarketLedger


NOW = datetime(2026, 7, 10, 19, 0, tzinfo=timezone.utc)


class HistoryProductMarketLedger(FakeProductMarketLedger):
    def get_pattern_history(self, tenant_id: int, days: int = 30, limit: int = 100) -> list[dict]:
        return [
            {
                "capability_text": "agentic product discovery",
                "summary": "Constructor moved on agentic product discovery earlier this week.",
                "involved_companies": ["Constructor", "Algolia"],
                "confidence": 0.72,
                "evidence_refs": [{"source_url": "https://constructor.com/changelog/agent"}],
                "created_at": "2026-07-08T19:00:00+00:00",
            }
        ][:limit]


class LedgerRefreshProductMarketLedger(HistoryProductMarketLedger):
    def get_recent_product_events(self, tenant_id: int, days: int = 30, limit: int = 500) -> list[dict]:
        return [
            {
                "id": 1,
                "tenant_id": tenant_id,
                "competitor_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability_text": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "observed_at": NOW,
                "evidence_refs": [
                    {
                        "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                        "captured_at": NOW.isoformat(),
                        "method": "scout_changelog",
                        "excerpt": "Constructor proof",
                    }
                ],
            },
            {
                "id": 2,
                "tenant_id": tenant_id,
                "competitor_id": None,
                "company_name": "Algolia",
                "company_role": "own",
                "capability_text": "agentic product discovery",
                "change_type": "release",
                "summary": "Algolia documented agentic product discovery.",
                "observed_at": NOW,
                "evidence_refs": [
                    {
                        "source_url": "https://www.algolia.com/changelog/agentic-discovery",
                        "captured_at": NOW.isoformat(),
                        "method": "scout_changelog",
                        "excerpt": "Algolia proof",
                    }
                ],
            },
        ]

    def get_recent_conversation_themes(self, tenant_id: int, days: int = 30, limit: int = 500) -> list[dict]:
        return [
            {
                "id": 10,
                "tenant_id": tenant_id,
                "competitor_id": 20,
                "company_name": "Constructor",
                "theme": "agentic product discovery",
                "summary": "Constructor is positioning around AI shopping agents.",
                "intensity": 0.82,
                "observed_at": NOW,
                "evidence_refs": [
                    {
                        "source_url": "https://constructor.com/blog/ai-shopping-agent",
                        "captured_at": NOW.isoformat(),
                        "method": "web_scan",
                        "excerpt": "Constructor narrative",
                    }
                ],
            }
        ]

    def get_recent_demand_signals(self, tenant_id: int, days: int = 30, limit: int = 500) -> list[dict]:
        return [
            {
                "id": 30,
                "tenant_id": tenant_id,
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 1234,
                "change_pct": 0.23,
                "period_start": NOW,
                "period_end": NOW,
                "source_label": "Looker Studio GA4 export",
                "evidence_refs": [
                    {
                        "source_url": "looker://algolia/ga4/topics",
                        "captured_at": NOW.isoformat(),
                        "method": "looker_export",
                        "excerpt": "GA4 demand proof",
                    }
                ],
                "metadata": {
                    "source_file": "ga-pages.csv",
                    "source_row_number": 1,
                    "source_fingerprint": "b" * 64,
                },
            }
        ]


class WindowedLedgerRefreshProductMarketLedger(LedgerRefreshProductMarketLedger):
    def get_recent_product_events(self, tenant_id: int, days: int = 30, limit: int = 500) -> list[dict]:
        older = {
            "id": 3,
            "tenant_id": tenant_id,
            "competitor_id": 40,
            "company_name": "Bloomreach",
            "company_role": "competitor",
            "capability_text": "vector merchandizing",
            "change_type": "release",
            "summary": "Bloomreach documented vector merchandizing improvements.",
            "observed_at": NOW - timedelta(days=20),
            "evidence_refs": [
                {
                    "source_url": "https://bloomreach.com/changelog/vector-merchandizing",
                    "captured_at": (NOW - timedelta(days=20)).isoformat(),
                    "method": "scout_changelog",
                    "excerpt": "Bloomreach older proof",
                }
            ],
        }
        return [*super().get_recent_product_events(tenant_id, days=days, limit=limit), older][:limit]

    def get_recent_conversation_themes(self, tenant_id: int, days: int = 30, limit: int = 500) -> list[dict]:
        older = {
            "id": 11,
            "tenant_id": tenant_id,
            "competitor_id": 40,
            "company_name": "Bloomreach",
            "theme": "vector merchandizing",
            "summary": "Bloomreach talked about vector merchandizing last month.",
            "intensity": 0.62,
            "observed_at": NOW - timedelta(days=20),
            "evidence_refs": [
                {
                    "source_url": "https://bloomreach.com/blog/vector-merchandizing",
                    "captured_at": (NOW - timedelta(days=20)).isoformat(),
                    "method": "web_scan",
                    "excerpt": "Bloomreach older narrative",
                }
            ],
        }
        return [*super().get_recent_conversation_themes(tenant_id, days=days, limit=limit), older][:limit]

    def get_recent_demand_signals(self, tenant_id: int, days: int = 30, limit: int = 500) -> list[dict]:
        older = {
            "id": 31,
            "tenant_id": tenant_id,
            "topic": "vector merchandizing",
            "metric": "engaged_sessions",
            "value": 320,
            "change_pct": 0.17,
            "period_start": NOW - timedelta(days=27),
            "period_end": NOW - timedelta(days=20),
            "source_label": "Looker Studio GA4 export",
            "evidence_refs": [
                {
                    "source_url": "looker://algolia/ga4/vector-merchandizing",
                    "captured_at": (NOW - timedelta(days=20)).isoformat(),
                    "method": "looker_export",
                    "excerpt": "Older GA4 demand proof",
                }
            ],
            "metadata": {
                "source_file": "ga-pages-last-month.csv",
                "source_row_number": 4,
                "source_fingerprint": "c" * 64,
            },
        }
        return [*super().get_recent_demand_signals(tenant_id, days=days, limit=limit), older][:limit]


def _payload() -> ProductMarketRunPayload:
    return ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            },
            {
                "company_id": 10,
                "company_name": "Algolia",
                "company_role": "own",
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Algolia documented agentic product discovery.",
                "source_url": "https://www.algolia.com/changelog/agentic-discovery",
                "captured_at": NOW.isoformat(),
            },
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "agentic product discovery",
                "summary": "Constructor is positioning around AI shopping agents.",
                "intensity": 0.82,
                "source_url": "https://constructor.com/blog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        looker_rows=[
            {
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 1234,
                "change_pct": 0.23,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "looker://algolia/ga4/topics",
            }
        ],
    )


def test_load_product_market_payload_from_json_file(tmp_path) -> None:
    path = tmp_path / "product-market.json"
    path.write_text(json.dumps(_payload().model_dump(mode="json")), encoding="utf-8")

    payload = load_product_market_payload(path)

    assert payload.tenant_id == 1
    assert payload.own_company_name == "Algolia"
    assert payload.scout_records[0]["company_name"] == "Constructor"


def test_payload_can_be_loaded_before_tenant_slug_resolution(tmp_path) -> None:
    path = tmp_path / "product-market.json"
    data = _payload().model_dump(mode="json")
    data.pop("tenant_id")
    path.write_text(json.dumps(data), encoding="utf-8")

    payload = load_product_market_payload(path)

    assert payload.tenant_id is None


def test_run_product_market_payload_requires_resolved_tenant_id() -> None:
    payload = _payload().model_copy(update={"tenant_id": None})

    with pytest.raises(ValueError, match="tenant_id"):
        run_product_market_payload(payload, repository=FakeProductMarketLedger())


def test_run_product_market_payload_executes_workflow_and_returns_counts() -> None:
    ledger = FakeProductMarketLedger()

    payload = _payload().model_copy(
        update={
            "learning_instructions": [
                {
                    "instruction": "Re-audit Coveo before ranking Constructor.",
                    "evidence_event_ids": [101],
                    "source_improvement_ids": [202],
                }
            ]
        }
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.tenant_id == 1
    assert summary.verdict == "actionable"
    assert summary.product_event_count == 2
    assert summary.conversation_theme_count == 1
    assert summary.demand_signal_count == 1
    assert summary.feature_position_count == 2
    assert summary.pattern_count == 1
    assert summary.recommendation_count == 1
    assert summary.learning_instruction_count == 1
    assert summary.learning_instruction_improvement_ids == [202]
    assert len(ledger.feature_positions) == 2
    assert len(ledger.run_intelligence_summaries) == 1
    assert ledger.run_intelligence_summaries[0].intelligence_brief.top_insight == summary.intelligence_brief.top_insight
    assert summary.intelligence_brief.verdict == "actionable"
    assert "Constructor" in summary.intelligence_brief.top_insight
    assert "Algolia" in summary.intelligence_brief.top_insight
    assert "agentic product discovery" in summary.intelligence_brief.primary_action
    assert set(summary.intelligence_brief.evidence_urls) >= {
        "https://constructor.com/changelog/ai-shopping-agent",
        "https://constructor.com/blog/ai-shopping-agent",
        "https://www.algolia.com/changelog/agentic-discovery",
        "looker://algolia/ga4/topics",
    }
    assert summary.intelligence_brief.next_questions


def test_run_product_market_payload_produces_canonical_argus_packet() -> None:
    ledger = FakeProductMarketLedger()

    summary = run_product_market_payload(_payload(), repository=ledger)

    assert summary.argus_packet is not None
    assert summary.argus_packet.schema_version == 1
    assert summary.argus_packet.tenant.tenant_id == 1
    assert summary.argus_packet.run.run_id.startswith("product-market-local-tenant-1-")
    assert summary.argus_packet.run.package_commit == "local"
    assert summary.argus_packet.status == "actionable"
    assert summary.argus_packet.executive_read.headline == summary.intelligence_brief.top_insight
    assert summary.argus_packet.recommendations[0].owner == "PMM"
    assert summary.argus_packet.recommendations[0].proof_ref_ids
    assert summary.argus_packet.consumer_state.dashboard is not None
    assert summary.argus_packet.consumer_state.dashboard.run_id == summary.argus_packet.run.run_id
    assert ledger.run_intelligence_summaries[0].argus_packet.packet_id == summary.argus_packet.packet_id


def test_run_product_market_payload_embeds_argus_decision_read_for_business_action() -> None:
    ledger = FakeProductMarketLedger()

    summary = run_product_market_payload(_payload(), repository=ledger)

    decision = summary.intelligence_brief.decision_read
    assert decision["status"] == "actionable"
    assert decision["market_direction"].startswith("agentic product discovery is heating up")
    assert "Constructor" in decision["priority_reason"]
    assert "tenant-side demand" in decision["priority_reason"]
    assert decision["strategic_insights"][0]["insight_type"] == "own_narrative_gap"
    assert "Algolia" in decision["strategic_insights"][0]["summary"]
    assert decision["tactical_actions"][0]["owner"] == "PMM"
    assert decision["tactical_actions"][0]["score"] == 78
    assert "agentic product discovery" in decision["tactical_actions"][0]["action"]
    assert [plane["plane"] for plane in decision["confidence_basis"][:3]] == [
        "product_reality",
        "market_conversation",
        "audience_demand",
    ]
    assert all(plane["status"] == "present" for plane in decision["confidence_basis"][:3])
    assert decision["blockers"] == []
    assert set(decision["evidence_urls"]) >= {
        "https://constructor.com/changelog/ai-shopping-agent",
        "https://constructor.com/blog/ai-shopping-agent",
        "https://www.algolia.com/changelog/agentic-discovery",
        "looker://algolia/ga4/topics",
    }


def test_run_product_market_payload_decision_read_blocks_action_without_demand_plane() -> None:
    ledger = FakeProductMarketLedger()
    payload = _payload().model_copy(update={"looker_rows": []})

    summary = run_product_market_payload(payload, repository=ledger)

    decision = summary.intelligence_brief.decision_read
    assert decision["status"] == "watch"
    assert "watch" in decision["priority_reason"].lower()
    assert decision["tactical_actions"] == []
    assert any("No tenant-side demand evidence" in blocker for blocker in decision["blockers"])
    demand_plane = next(plane for plane in decision["confidence_basis"] if plane["plane"] == "audience_demand")
    assert demand_plane["status"] == "missing"
    assert demand_plane["evidence_count"] == 0
    assert "owner action" in demand_plane["summary"]


def test_run_product_market_payload_brief_instructs_hermes_to_collect_missing_demand() -> None:
    ledger = FakeProductMarketLedger()
    payload = _payload().model_copy(update={"looker_rows": []})

    summary = run_product_market_payload(payload, repository=ledger)

    actions = summary.intelligence_brief.next_monitoring_actions
    demand_action = next(action for action in actions if action.plane == "audience_demand")
    assert demand_action.owner == "Hermes"
    assert demand_action.priority == "critical"
    assert "GA / Looker" in demand_action.instruction
    assert "agentic product discovery" in demand_action.instruction
    assert "recommendation" in demand_action.reason
    assert demand_action.source_families == ["ga4_api_export", "ga_looker_manual_export"]
    assert set(demand_action.evidence_urls) >= {
        "https://constructor.com/changelog/ai-shopping-agent",
        "https://constructor.com/blog/ai-shopping-agent",
    }
    assert ledger.run_intelligence_summaries[0].intelligence_brief.next_monitoring_actions == actions


def test_run_product_market_payload_brief_keeps_monitoring_agenda_after_actionable_read() -> None:
    ledger = FakeProductMarketLedger()

    summary = run_product_market_payload(_payload(), repository=ledger)

    actions = summary.intelligence_brief.next_monitoring_actions
    assert [action.plane for action in actions[:2]] == ["source_coverage", "learning"]
    assert actions[0].owner == "Hermes"
    assert actions[0].priority == "medium"
    assert "Constructor" in actions[0].instruction
    assert "Algolia" in actions[0].instruction
    assert "agentic product discovery" in actions[0].instruction
    assert actions[1].owner == "Argus"
    assert "scorecard" in actions[1].instruction
    assert "looker://algolia/ga4/topics" in actions[1].evidence_urls


def test_run_product_market_payload_embeds_product_feature_comparison_read() -> None:
    ledger = FakeProductMarketLedger()

    summary = run_product_market_payload(_payload(), repository=ledger)

    comparison = summary.intelligence_brief.product_feature_comparison
    assert comparison["summary"] == "1 capability compared; 0 product gaps, 1 narrative gap, 1 demand-backed row."
    assert comparison["product_gap_count"] == 0
    assert comparison["narrative_gap_count"] == 1
    assert comparison["demand_backed_count"] == 1
    row = comparison["rows"][0]
    assert row["capability"] == "agentic product discovery"
    assert row["capability_key"] == "shopping agent"
    assert row["assessment"] == "own_narrative_gap"
    assert row["own_status"] == "proven"
    assert row["competitors_with_product_proof"] == ["Constructor"]
    assert row["competitors_with_conversation"] == ["Constructor"]
    assert row["has_rising_demand"] is True
    assert row["recommended_action"] == (
        "Create an Algolia narrative for agentic product discovery using existing product proof."
    )
    assert set(row["evidence_urls"]) >= {
        "https://constructor.com/changelog/ai-shopping-agent",
        "https://constructor.com/blog/ai-shopping-agent",
        "https://www.algolia.com/changelog/agentic-discovery",
        "looker://algolia/ga4/topics",
    }
    assert ledger.run_intelligence_summaries[0].intelligence_brief.product_feature_comparison == comparison


def test_run_product_market_ledger_refresh_replays_existing_ledgers_without_resaving_inputs() -> None:
    ledger = LedgerRefreshProductMarketLedger()

    summary = run_product_market_ledger_refresh(
        tenant_id=1,
        own_company_name="Algolia",
        repository=ledger,
    )

    assert summary.verdict == "actionable"
    assert summary.product_event_count == 2
    assert summary.conversation_theme_count == 1
    assert summary.demand_signal_count == 1
    assert summary.pattern_count == 1
    assert summary.recommendation_count == 1
    assert ledger.product_events == []
    assert ledger.conversation_themes == []
    assert ledger.demand_signals == []
    assert ledger.patterns[0].pattern_type == "own_narrative_gap"
    assert ledger.recommendations[0][0].owner == "PMM"
    assert ledger.run_intelligence_summaries[0].intelligence_brief.top_insight == summary.intelligence_brief.top_insight
    assert "looker://algolia/ga4/topics" in summary.intelligence_brief.evidence_urls


def test_run_product_market_ledger_refresh_traces_demand_into_recommendation() -> None:
    ledger = LedgerRefreshProductMarketLedger()

    summary = run_product_market_ledger_refresh(
        tenant_id=1,
        own_company_name="Algolia",
        repository=ledger,
    )

    trace = summary.intelligence_brief.demand_recommendation_trace
    assert trace["status"] == "linked_to_recommendations"
    assert trace["demand_signal_count"] == 1
    assert trace["matched_demand_topic_count"] == 1
    assert trace["recommendation_count"] == 1
    assert trace["evidence_urls"] == [
        "looker://algolia/ga4/topics",
        "https://constructor.com/changelog/ai-shopping-agent",
        "https://constructor.com/blog/ai-shopping-agent",
        "https://www.algolia.com/changelog/agentic-discovery",
    ]

    topic = trace["demand_topics"][0]
    assert topic["topic"] == "agentic product discovery"
    assert topic["capability_key"] == "shopping agent"
    assert topic["metric"] == "engaged_sessions"
    assert topic["value"] == 1234
    assert topic["change_pct"] == 0.23
    assert topic["source_files"] == ["ga-pages.csv"]
    assert topic["source_row_numbers"] == [1]
    assert topic["pattern_summaries"] == [
        "Constructor is shipping and saying agentic product discovery, while Algolia has product proof but no matching narrative in this evidence set."
    ]
    assert topic["recommendation_actions"] == [
        "Create an evidence-backed agentic product discovery narrative that connects Algolia's shipped capability to rising audience demand."
    ]
    assert topic["scorecard_dimensions"] == ["audience_demand", "evidence_breadth"]
    assert topic["evidence_urls"] == ["looker://algolia/ga4/topics"]
    assert ledger.run_intelligence_summaries[0].intelligence_brief.demand_recommendation_trace == trace


def test_run_product_market_ledger_refresh_embeds_7_and_30_day_window_comparison() -> None:
    ledger = WindowedLedgerRefreshProductMarketLedger()

    summary = run_product_market_ledger_refresh(
        tenant_id=1,
        own_company_name="Algolia",
        repository=ledger,
        days=30,
    )

    comparison = summary.intelligence_brief.window_comparison
    assert comparison["summary"] == (
        "Last 7 days: 2 product events, 1 conversation theme, 1 demand signal. "
        "Last 30 days: 3 product events, 2 conversation themes, 2 demand signals."
    )
    seven = next(window for window in comparison["windows"] if window["days"] == 7)
    thirty = next(window for window in comparison["windows"] if window["days"] == 30)
    assert seven["product_event_count"] == 2
    assert seven["conversation_theme_count"] == 1
    assert seven["demand_signal_count"] == 1
    assert seven["leading_companies"] == ["Constructor", "Algolia"]
    assert "agentic product discovery" in seven["hot_capabilities"]
    assert "vector merchandizing" not in seven["hot_capabilities"]
    assert "https://bloomreach.com/changelog/vector-merchandizing" not in seven["evidence_urls"]
    assert thirty["product_event_count"] == 3
    assert thirty["conversation_theme_count"] == 2
    assert thirty["demand_signal_count"] == 2
    assert "Bloomreach" in thirty["leading_companies"]
    assert "vector merchandizing" in thirty["hot_capabilities"]
    assert "https://bloomreach.com/changelog/vector-merchandizing" in thirty["evidence_urls"]


def test_run_product_market_payload_embeds_market_movement_map_in_brief() -> None:
    ledger = HistoryProductMarketLedger()

    summary = run_product_market_payload(_payload(), repository=ledger)

    movement = summary.intelligence_brief.movement_map
    assert movement["direction_summary"].startswith("agentic product discovery is heating up")
    assert movement["hot_capabilities"] == ["agentic product discovery"]
    assert any(
        cell["company_name"] == "Constructor"
        and cell["capability"] == "agentic product discovery"
        and cell["heat_level"] == "hot"
        for cell in movement["heat_cells"]
    )
    assert "https://constructor.com/changelog/agent" in movement["evidence_urls"]
    assert ledger.run_intelligence_summaries[0].intelligence_brief.movement_map == movement


def test_run_product_market_payload_applies_coverage_recheck_learning_gate() -> None:
    ledger = FakeProductMarketLedger()
    payload = _payload().model_copy(
        update={
            "learning_instructions": [
                {
                    "kind": "coverage_recheck",
                    "instruction": "Re-audit source coverage before ranking Constructor again.",
                    "evidence_event_ids": [101],
                    "source_improvement_ids": [202],
                }
            ]
        }
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "watch"
    assert summary.pattern_count == 1
    assert summary.recommendation_count == 0
    assert summary.learning_instruction_count == 1
    assert summary.learning_instruction_improvement_ids == [202]
    assert ledger.patterns[0].pattern_type == "own_narrative_gap"
    assert ledger.recommendations == []


def test_run_product_market_payload_applies_scoring_review_learning_gate() -> None:
    ledger = FakeProductMarketLedger()
    payload = _payload().model_copy(
        update={
            "learning_instructions": [
                {
                    "kind": "scoring_review",
                    "instruction": "Require stronger scorecard evidence before promoting the next recommendation.",
                    "evidence_event_ids": [101],
                    "source_improvement_ids": [303],
                }
            ]
        }
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "watch"
    assert summary.pattern_count == 1
    assert summary.recommendation_count == 0
    assert summary.learning_instruction_count == 1
    assert summary.learning_instruction_improvement_ids == [303]
    assert ledger.patterns[0].pattern_type == "own_narrative_gap"
    assert ledger.recommendations == []
    assert summary.intelligence_brief.verdict == "watch"
    assert summary.intelligence_brief.primary_action is None
    assert any("withheld" in item for item in summary.intelligence_brief.confidence_limits)


def test_run_product_market_payload_brief_marks_quiet_as_unproven_not_silent() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[],
        conversation_records=[],
        looker_rows=[],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "quiet"
    assert summary.intelligence_brief.verdict == "quiet"
    assert "No cross-plane product-market pattern qualified" in summary.intelligence_brief.top_insight
    assert summary.intelligence_brief.primary_action is None
    assert summary.intelligence_brief.evidence_urls == []
    assert any("does not mean the market was silent" in item for item in summary.intelligence_brief.confidence_limits)


def test_run_product_market_payload_explains_product_artifacts_without_demand_or_patterns() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            },
            {
                "company_id": 30,
                "company_name": "Coveo",
                "company_role": "competitor",
                "capability": "agentic product discovery",
                "change_type": "docs_update",
                "summary": "Coveo documented commerce search assistants.",
                "source_url": "https://coveo.com/docs/commerce-assistants",
                "captured_at": NOW.isoformat(),
            },
        ],
        conversation_records=[],
        looker_rows=[],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "quiet"
    assert summary.product_event_count == 2
    assert summary.feature_position_count == 2
    assert summary.pattern_count == 0
    assert summary.conversion_diagnostics.scout_record_count == 2
    assert summary.conversion_diagnostics.product_event_count == 2
    assert summary.conversion_diagnostics.feature_position_count == 2
    assert summary.conversion_diagnostics.pattern_count == 0
    assert summary.conversion_diagnostics.summary == (
        "2 Scout/product records converted to 2 product events and 2 feature positions; "
        "0 product-market patterns qualified."
    )
    assert any(
        "product proof but no rising demand signal"
        in blocker
        for blocker in summary.conversion_diagnostics.blockers
    )
    assert summary.intelligence_brief.conversion_diagnostics["product_event_count"] == 2
    assert any(
        "2 product events and 2 feature positions"
        in item
        for item in summary.intelligence_brief.confidence_limits
    )


def test_run_product_market_payload_reports_matched_synonymous_capabilities() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "AI Shopping Agent",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "commerce AI agent",
                "summary": "Constructor is positioning commerce AI agents.",
                "intensity": 0.81,
                "source_url": "https://constructor.com/blog/commerce-ai-agent",
                "captured_at": NOW.isoformat(),
                "method": "web_scan",
            }
        ],
        looker_rows=[
            {
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 240,
                "change_pct": 0.22,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "looker://algolia/ga4/topics",
            }
        ],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "actionable"
    assert summary.pattern_count == 1
    assert summary.recommendation_count == 1
    assert summary.conversion_diagnostics.matched_capability_count == 1
    assert summary.conversion_diagnostics.product_capability_count == 1
    assert summary.conversion_diagnostics.conversation_capability_count == 1
    assert summary.conversion_diagnostics.demand_capability_count == 1
    assert not any("no rising demand signal" in item.lower() for item in summary.conversion_diagnostics.blockers)


def test_run_product_market_payload_does_not_promote_tiny_high_growth_demand() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "AI Shopping Agent",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "commerce AI agent",
                "summary": "Constructor is positioning commerce AI agents.",
                "intensity": 0.81,
                "source_url": "https://constructor.com/blog/commerce-ai-agent",
                "captured_at": NOW.isoformat(),
                "method": "web_scan",
            }
        ],
        looker_rows=[
            {
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 3,
                "change_pct": 0.90,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "https://lookerstudio.google.com/reporting/agentic",
                "source_file": "ga-pages.csv",
                "source_row_number": 1,
                "source_fingerprint": "c" * 64,
            }
        ],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "watch"
    assert summary.pattern_count == 1
    assert summary.recommendation_count == 0
    assert summary.conversion_diagnostics.demand_signal_count == 1
    assert summary.conversion_diagnostics.rising_demand_signal_count == 0
    assert summary.conversion_diagnostics.demand_capability_count == 0
    assert any("no rising demand signal" in item.lower() for item in summary.conversion_diagnostics.blockers)
    assert summary.intelligence_brief.demand_read["summary"] == (
        "1 demand signal captured, but none crossed the rising-demand threshold."
    )
    assert summary.intelligence_brief.demand_recommendation_trace["status"] == "no_rising_demand"


def test_run_product_market_payload_uses_payload_demand_quality_thresholds() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        demand_quality={"change_floor": 0.05, "value_floor": 2},
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "AI Shopping Agent",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "commerce AI agent",
                "summary": "Constructor is positioning commerce AI agents.",
                "intensity": 0.81,
                "source_url": "https://constructor.com/blog/commerce-ai-agent",
                "captured_at": NOW.isoformat(),
                "method": "web_scan",
            }
        ],
        looker_rows=[
            {
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 3,
                "change_pct": 0.90,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "https://lookerstudio.google.com/reporting/agentic",
                "source_file": "ga-pages.csv",
                "source_row_number": 1,
                "source_fingerprint": "e" * 64,
            }
        ],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    assert summary.verdict == "actionable"
    assert summary.recommendation_count == 1
    assert summary.conversion_diagnostics.rising_demand_signal_count == 1
    assert summary.intelligence_brief.demand_read["rising_topic_count"] == 1
    assert summary.intelligence_brief.demand_recommendation_trace["status"] == "linked_to_recommendations"


def test_run_product_market_payload_embeds_demand_read_with_matches_and_provenance() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "AI Shopping Agent",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "commerce AI agent",
                "summary": "Constructor is positioning commerce AI agents.",
                "intensity": 0.81,
                "source_url": "https://constructor.com/blog/commerce-ai-agent",
                "captured_at": NOW.isoformat(),
                "method": "web_scan",
            }
        ],
        looker_rows=[
            {
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 240,
                "change_pct": 0.22,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "https://lookerstudio.google.com/reporting/agentic",
                "source_file": "ga-pages.csv",
                "source_row_number": 1,
                "source_fingerprint": "a" * 64,
            },
            {
                "topic": "context engineering",
                "metric": "engaged_sessions",
                "value": 180,
                "change_pct": 0.41,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "https://lookerstudio.google.com/reporting/context",
                "source_file": "ga-pages.csv",
                "source_row_number": 2,
                "source_fingerprint": "b" * 64,
            },
        ],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    demand_read = summary.intelligence_brief.demand_read
    assert demand_read["summary"] == (
        "2 rising demand topics found; 1 matched product proof and 1 still needs product proof."
    )
    assert demand_read["rising_topic_count"] == 2
    assert demand_read["matched_product_topic_count"] == 1
    assert demand_read["unmatched_demand_topic_count"] == 1
    assert demand_read["source_files"] == ["ga-pages.csv"]
    assert demand_read["evidence_urls"] == [
        "https://lookerstudio.google.com/reporting/context",
        "https://lookerstudio.google.com/reporting/agentic",
    ]
    context = next(topic for topic in demand_read["top_topics"] if topic["topic"] == "context engineering")
    assert context["matched_product_proof"] is False
    assert context["matched_market_conversation"] is False
    assert context["missing_planes"] == ["product_proof", "market_conversation"]
    assert context["source_files"] == ["ga-pages.csv"]
    agentic = next(topic for topic in demand_read["top_topics"] if topic["topic"] == "agentic product discovery")
    assert agentic["matched_product_proof"] is True
    assert agentic["matched_market_conversation"] is True
    assert agentic["missing_planes"] == []


def test_demand_read_uses_argus_plan_capability_key_for_matching() -> None:
    ledger = FakeProductMarketLedger()
    payload = ProductMarketRunPayload(
        tenant_id=1,
        own_company_name="Algolia",
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "Assistant",
                "change_type": "release",
                "summary": "Constructor documents an Assistant capability.",
                "source_url": "https://constructor.com/changelog/assistant",
                "captured_at": NOW.isoformat(),
            }
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "Assistant",
                "summary": "Constructor is positioning around assistants.",
                "intensity": 0.81,
                "source_url": "https://constructor.com/blog/assistant",
                "captured_at": NOW.isoformat(),
                "method": "web_scan",
            }
        ],
        looker_rows=[
            {
                "topic": "Agent experience pages",
                "metric": "engaged_sessions",
                "value": 240,
                "change_pct": 0.22,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "https://lookerstudio.google.com/reporting/assistant",
                "source_file": "argus-demand-plan-template.csv",
                "source_row_number": 1,
                "source_fingerprint": "d" * 64,
                "argus_capability_key": "assistant",
                "argus_assessment": "competitive_pressure",
            }
        ],
    )

    summary = run_product_market_payload(payload, repository=ledger)

    demand_read = summary.intelligence_brief.demand_read
    topic = demand_read["top_topics"][0]
    assert summary.pattern_count >= 1
    assert summary.recommendation_count >= 1
    assert topic["topic"] == "Agent experience pages"
    assert topic["capability_key"] == "assistant"
    assert topic["matched_product_proof"] is True
    assert topic["matched_market_conversation"] is True
    assert topic["missing_planes"] == []
