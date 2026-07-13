from __future__ import annotations

from types import SimpleNamespace

import pytest

from cios.admin.repository import PgAdminRepository
from cios.admin.types import (
    CompetitorCreate,
    CompetitorUpdate,
    ImprovementStatusUpdate,
    SourceCreate,
    SourceUpdate,
)
from cios.db.session import tenant_context

pytestmark = pytest.mark.integration


def test_admin_repository_adds_pauses_and_retires_competitors_and_sources(app_conn):
    repo = PgAdminRepository(app_conn)

    competitor = repo.create_competitor(
        "algolia",
        CompetitorCreate(
            name="Admin Test Competitor",
            domain="admin-test.example",
            category="test",
            priority=2,
        ),
    )
    source = repo.create_source(
        "algolia",
        competitor.competitor_id,
        SourceCreate(source_family="blog", url="https://admin-test.example/blog"),
    )
    paused_competitor = repo.update_competitor(
        "algolia", competitor.competitor_id, CompetitorUpdate(status="paused")
    )
    blocked_source = repo.update_source("algolia", source.source_id, SourceUpdate(status="blocked"))

    registry = repo.registry("algolia")
    saved = next(c for c in registry.competitors if c.competitor_id == competitor.competitor_id)

    assert paused_competitor.status == "paused"
    assert blocked_source.status == "blocked"
    assert saved.competitor_name == "Admin Test Competitor"
    assert saved.sources[0].url == "https://admin-test.example/blog"


def test_admin_repository_lists_and_updates_argus_improvement_queue(app_conn):
    repo = PgAdminRepository(app_conn)
    with tenant_context(app_conn, 1):
        row = app_conn.execute(
            """
            INSERT INTO improvement_queue (tenant_id, source, problem, proposed_fix, priority, status)
            VALUES (1, 'argus_recommendation:7', 'challenge saved', 'recheck coverage', 'critical', 'open')
            RETURNING id
            """
        ).fetchone()
    improvement_id = int(row[0])

    items = repo.list_improvements("algolia")
    approved = repo.update_improvement_status(
        "algolia",
        improvement_id,
        ImprovementStatusUpdate(status="approved"),
    )
    registry = repo.registry("algolia")

    assert any(item.improvement_id == improvement_id for item in items)
    assert approved.status == "approved"
    assert all(item.improvement_id != improvement_id for item in registry.improvements)


def test_admin_repository_reads_product_muscle_feature_matrix(app_conn):
    repo = PgAdminRepository(app_conn)
    with tenant_context(app_conn, 1):
        capability = app_conn.execute(
            """
            INSERT INTO feature_capabilities (tenant_id, canonical_name, taxonomy_path)
            VALUES (1, 'agentic product discovery', 'commerce/search/agentic')
            ON CONFLICT (tenant_id, canonical_name) DO UPDATE SET taxonomy_path = EXCLUDED.taxonomy_path
            RETURNING id
            """
        ).fetchone()
        capability_id = int(capability[0])
        competitor = app_conn.execute(
            """
            INSERT INTO competitors (tenant_id, name, domain, category, priority, status)
            VALUES (1, 'Feature Matrix Test', 'feature-matrix.example', 'test', 9, 'active')
            ON CONFLICT (tenant_id, name) DO UPDATE SET status = 'active'
            RETURNING id
            """
        ).fetchone()
        competitor_id = int(competitor[0])
        app_conn.execute(
            """
            INSERT INTO company_feature_positions (
                tenant_id, feature_capability_id, competitor_id, company_name,
                company_role, position_status, summary, evidence_refs, confidence
            )
            VALUES (
                1, %s, %s, 'Feature Matrix Test', 'competitor', 'proven',
                'Feature Matrix Test has product proof for agentic discovery.',
                '[{"source_url":"https://feature-matrix.example/changelog"}]'::jsonb,
                0.72
            )
            ON CONFLICT (tenant_id, feature_capability_id, company_role, company_name)
            DO UPDATE SET summary = EXCLUDED.summary,
                          evidence_refs = EXCLUDED.evidence_refs,
                          confidence = EXCLUDED.confidence
            """,
            (capability_id, competitor_id),
        )

    rows = repo.feature_matrix("algolia")
    saved = next(row for row in rows if row.company_name == "Feature Matrix Test")

    assert saved.capability_text == "agentic product discovery"
    assert saved.position_status == "proven"
    assert saved.evidence_refs[0]["source_url"] == "https://feature-matrix.example/changelog"


def test_admin_repository_lists_and_updates_argus_recommendations(app_conn):
    repo = PgAdminRepository(app_conn)
    with tenant_context(app_conn, 1):
        pattern = app_conn.execute(
            """
            INSERT INTO pattern_observations (
                tenant_id, pattern_type, capability_text, summary,
                involved_companies, confidence, evidence_refs
            )
            VALUES (
                1, 'own_narrative_gap', 'agentic product discovery',
                'Constructor moved faster than Algolia narrative.',
                '["Algolia","Constructor"]'::jsonb, 0.78,
                '[{"source_url":"https://constructor.com/changelog"}]'::jsonb
            )
            RETURNING id
            """
        ).fetchone()
        pattern_id = int(pattern[0])
        recommendation = app_conn.execute(
            """
            INSERT INTO argus_recommendations (
                tenant_id, pattern_observation_id, owner, action, why_now,
                urgency, confidence, scorecard, evidence_refs, status
            )
            VALUES (
                1, %s, 'PMM',
                'Create an evidence-backed AI shopping agent narrative for Algolia.',
                'Constructor has product proof, public positioning, and rising audience demand.',
                'this_week', 0.78,
                '{"total_score":78,"verdict":"actionable","summary":"Product proof, conversation, and demand align.","dimension_scores":[{"dimension":"product_reality","score":20,"max_score":25,"rationale":"Constructor has release evidence.","evidence_urls":["https://constructor.com/changelog"]}]}'::jsonb,
                '[{"source_url":"https://constructor.com/changelog"}]'::jsonb,
                'open'
            )
            RETURNING id
            """,
            (pattern_id,),
        ).fetchone()
    recommendation_id = int(recommendation[0])

    listed = repo.list_recommendations("algolia")
    accepted = repo.update_recommendation_status(
        "algolia",
        recommendation_id,
        SimpleNamespace(status="accepted"),
    )

    saved = next(item for item in listed if item.recommendation_id == recommendation_id)
    assert saved.scorecard["total_score"] == 78
    assert saved.evidence_refs[0]["source_url"] == "https://constructor.com/changelog"
    assert accepted.status == "accepted"


def test_admin_repository_reads_argus_evidence_ledger(app_conn):
    repo = PgAdminRepository(app_conn)
    with tenant_context(app_conn, 1):
        product = app_conn.execute(
            """
            INSERT INTO product_change_events (
                tenant_id, company_name, company_role, capability_text,
                change_type, summary, observed_at, evidence_refs, confidence
            )
            VALUES (
                1, 'Constructor', 'competitor', 'AI shopping agents',
                'release', 'Constructor published product proof for AI shopping agents.',
                now(), '[{"source_url":"https://constructor.com/changelog"}]'::jsonb, 0.82
            )
            RETURNING id
            """
        ).fetchone()
        conversation = app_conn.execute(
            """
            INSERT INTO conversation_themes (
                tenant_id, company_name, theme, summary, intensity,
                observed_at, evidence_refs
            )
            VALUES (
                1, 'Constructor', 'AI shopping agents',
                'Constructor is positioning AI shopping agents as category infrastructure.',
                0.74, now(), '[{"source_url":"https://constructor.com/blog"}]'::jsonb
            )
            RETURNING id
            """
        ).fetchone()
        demand = app_conn.execute(
            """
            INSERT INTO demand_signals (
                tenant_id, topic, metric, value, change_pct,
                period_start, period_end, source_label, evidence_refs
            )
            VALUES (
                1, 'AI shopping agents', 'engaged_sessions', 240, 0.32,
                now() - interval '7 days', now(), 'Looker Studio GA4 export',
                '[{"source_url":"looker://algolia/ga4/ai-shopping-agents"}]'::jsonb
            )
            RETURNING id
            """
        ).fetchone()
        pattern = app_conn.execute(
            """
            INSERT INTO pattern_observations (
                tenant_id, pattern_type, capability_text, summary,
                involved_companies, confidence, evidence_refs
            )
            VALUES (
                1, 'own_narrative_gap', 'AI shopping agents',
                'Constructor is louder while Algolia has no matching narrative in this evidence set.',
                '["Algolia","Constructor"]'::jsonb, 0.78,
                '[{"source_url":"https://constructor.com/changelog"}]'::jsonb
            )
            RETURNING id
            """
        ).fetchone()

    ledger = repo.evidence_ledger("algolia")

    assert any(item.product_event_id == int(product[0]) for item in ledger.product_events)
    assert any(item.conversation_theme_id == int(conversation[0]) for item in ledger.conversation_themes)
    assert any(item.demand_signal_id == int(demand[0]) for item in ledger.demand_signals)
    assert any(item.pattern_observation_id == int(pattern[0]) for item in ledger.patterns)
