from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cios.admin.demand_imports import DemandImportLedgerPersister, DemandImportStore
from cios.dashboard.state_builder import DashboardStateBuilder
from cios.db.repos.product_market import PgProductMarketRepository
from cios.db.session import tenant_context
from cios.intelligence.runner import run_product_market_ledger_refresh
from cios.intelligence.types import ConversationTheme, EvidenceRef, ProductChangeEvent, SourceMethod
from cios.intelligence.workflow import ProductMarketIntelligenceWorkflow

pytestmark = pytest.mark.integration


class EmptySignalsRepository:
    def get_material_deltas(self, tenant_id: int) -> list[dict]:
        return []


class EmptyThesesRepository:
    def get_active_theses(self, tenant_id: int) -> list[dict]:
        return []


class EmptyCoverageRepository:
    def get_latest_coverage(self, tenant_id: int) -> dict | None:
        return None


class EmptyRunsRepository:
    def get_latest_run(self, tenant_id: int, cadence: str) -> dict | None:
        return None


def _evidence(url: str, *, captured_at: datetime) -> EvidenceRef:
    return EvidenceRef(
        source_url=url,
        captured_at=captured_at,
        method=SourceMethod.SCOUT_CHANGELOG,
        excerpt="integration proof",
    )


def _seed_competitor(app_conn) -> int:
    with tenant_context(app_conn, 1):
        row = app_conn.execute(
            """
            INSERT INTO competitors (tenant_id, name, domain, category, priority, status)
            VALUES (1, 'Demand Flow Constructor', 'demand-flow-constructor.example', 'test', 1, 'active')
            RETURNING id
            """
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_demand_file_to_ledger_refresh_changes_dashboard_semantic_alignment(app_conn, tmp_path):
    repo = PgProductMarketRepository(app_conn)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    competitor_id = _seed_competitor(app_conn)

    ProductMarketIntelligenceWorkflow(repository=repo).run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            ProductChangeEvent(
                tenant_id=1,
                company_id=competitor_id,
                company_name="Demand Flow Constructor",
                company_role="competitor",
                capability="AI Shopping Agent",
                change_type="release",
                summary="Constructor shipped AI Shopping Agent proof.",
                observed_at=now,
                evidence=[
                    _evidence(
                        "https://demand-flow-constructor.example/changelog/ai-shopping-agent",
                        captured_at=now,
                    )
                ],
            )
        ],
        conversation_themes=[
            ConversationTheme(
                tenant_id=1,
                company_id=competitor_id,
                company_name="Demand Flow Constructor",
                theme="AI Shopping Agent",
                summary="Constructor is positioning AI shopping agents as commerce infrastructure.",
                intensity=0.82,
                observed_at=now,
                evidence=[
                    EvidenceRef(
                        source_url="https://demand-flow-constructor.example/blog/ai-shopping-agent",
                        captured_at=now,
                        method=SourceMethod.WEB_SCAN,
                        excerpt="integration proof",
                    )
                ],
            )
        ],
        demand_signals=[],
    )

    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop_folder = app_dir / "data" / "looker" / "algolia"
    drop_folder.mkdir(parents=True)
    period_start = (now - timedelta(days=7)).date().isoformat()
    period_end = now.date().isoformat()
    (drop_folder / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        f"AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,{period_start},{period_end},https://lookerstudio.google.com/reporting/demand-flow\n",
        encoding="utf-8",
    )

    prepared = DemandImportStore(app_dir=app_dir, work_root=work_root).prepare("algolia")
    persisted = DemandImportLedgerPersister(repository=repo).persist(tenant_id=1, prepared=prepared)
    summary = run_product_market_ledger_refresh(
        tenant_id=1,
        own_company_name="Algolia",
        repository=repo,
    )
    state = DashboardStateBuilder(
        signals=EmptySignalsRepository(),
        theses=EmptyThesesRepository(),
        coverage=EmptyCoverageRepository(),
        runs=EmptyRunsRepository(),
        product_market=repo,
    ).build(tenant_id=1, cadence="daily")

    assert prepared.ready_count == 1
    assert persisted.demand_signal_count == 1
    assert summary.demand_signal_count == 1
    assert summary.pattern_count >= 1
    assert summary.recommendation_count >= 1
    assert state.demand_signals[0].source_label == "Looker Studio GA4 export"
    assert state.demand_feature_alignment.status == "matched"
    alignment_row = state.demand_feature_alignment.rows[0]
    assert alignment_row.topic == "AI Shopping Agent"
    assert alignment_row.match_status == "matched"
    assert alignment_row.matched_capability == "AI Shopping Agent"
    assert alignment_row.demand_evidence_url == "https://lookerstudio.google.com/reporting/demand-flow"
    assert [company.company_name for company in alignment_row.related_companies] == [
        "Demand Flow Constructor"
    ]
    assert state.intelligence_spine.planes[2].plane == "audience_demand"
    assert state.intelligence_spine.planes[2].status == "present"
    assert state.argus_recommendations


def test_argus_plan_template_demand_file_uses_capability_key_for_dashboard_alignment(app_conn, tmp_path):
    repo = PgProductMarketRepository(app_conn)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    competitor_id = _seed_competitor(app_conn)

    ProductMarketIntelligenceWorkflow(repository=repo).run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            ProductChangeEvent(
                tenant_id=1,
                company_id=competitor_id,
                company_name="Demand Flow Constructor",
                company_role="competitor",
                capability="Assistant",
                change_type="release",
                summary="Constructor shipped Assistant proof.",
                observed_at=now,
                evidence=[
                    _evidence(
                        "https://demand-flow-constructor.example/changelog/assistant",
                        captured_at=now,
                    )
                ],
            )
        ],
        conversation_themes=[
            ConversationTheme(
                tenant_id=1,
                company_id=competitor_id,
                company_name="Demand Flow Constructor",
                theme="Assistant",
                summary="Constructor is positioning Assistant as commerce infrastructure.",
                intensity=0.82,
                observed_at=now,
                evidence=[
                    EvidenceRef(
                        source_url="https://demand-flow-constructor.example/blog/assistant",
                        captured_at=now,
                        method=SourceMethod.WEB_SCAN,
                        excerpt="integration proof",
                    )
                ],
            )
        ],
        demand_signals=[],
    )

    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop_folder = app_dir / "data" / "looker" / "algolia"
    drop_folder.mkdir(parents=True)
    period_start = (now - timedelta(days=7)).date().isoformat()
    period_end = now.date().isoformat()
    (drop_folder / "argus-demand-plan-template.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,"
        "Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,"
        "Why collect,Evidence URLs\n"
        f",,240,160,{period_start},{period_end},https://lookerstudio.google.com/reporting/assistant,"
        "Agent experience pages,Assistant,competitive_pressure,assistant | agent,"
        "Demand Flow Constructor,Validate demand behind the Assistant plan row.,"
        "https://demand-flow-constructor.example/changelog/assistant\n",
        encoding="utf-8",
    )

    prepared = DemandImportStore(app_dir=app_dir, work_root=work_root).prepare("algolia")
    persisted = DemandImportLedgerPersister(repository=repo).persist(tenant_id=1, prepared=prepared)
    summary = run_product_market_ledger_refresh(
        tenant_id=1,
        own_company_name="Algolia",
        repository=repo,
    )
    state = DashboardStateBuilder(
        signals=EmptySignalsRepository(),
        theses=EmptyThesesRepository(),
        coverage=EmptyCoverageRepository(),
        runs=EmptyRunsRepository(),
        product_market=repo,
    ).build(tenant_id=1, cadence="daily")

    assert prepared.ready_count == 1
    assert persisted.demand_signal_count == 1
    assert summary.demand_signal_count == 1
    assert summary.pattern_count >= 1
    assert summary.recommendation_count >= 1
    assert state.demand_signals[0].topic == "Agent experience pages"
    assert state.demand_signals[0].argus_plan_context["capability_key"] == "Assistant"
    alignment_row = state.demand_feature_alignment.rows[0]
    assert alignment_row.topic == "Agent experience pages"
    assert alignment_row.match_status == "matched"
    assert alignment_row.matched_capability == "Assistant"
    assert [company.company_name for company in alignment_row.related_companies] == [
        "Demand Flow Constructor"
    ]
