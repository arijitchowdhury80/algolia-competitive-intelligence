from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from cios.db.repos.product_market import PgProductMarketRepository
from cios.intelligence.runner import ProductMarketIntelligenceBrief, ProductMarketRunSummary
from cios.intelligence.types import (
    ConversationTheme,
    DemandSignal,
    EvidenceRef,
    FeaturePosition,
    PatternObservation,
    ProductChangeEvent,
    Recommendation,
    RecommendationScorecard,
    RubricDimensionScore,
    SourceMethod,
)


NOW = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, row: dict | None = None, rows: list[dict] | None = None) -> None:
        self.row = row or {"id": 123}
        self.rows = rows or []
        self.sql = ""
        self.params = None
        self.executed: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params) -> None:
        self.sql = sql
        self.params = params
        self.executed.append((sql, params))

    def fetchone(self) -> dict:
        return self.row

    def fetchall(self) -> list[dict]:
        return self.rows


class _FakeConnection:
    def __init__(self, *, row: dict | None = None, rows: list[dict] | None = None) -> None:
        self.cursor_obj = _FakeCursor(row=row, rows=rows)
        self.executed: list[tuple] = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, *args, **kwargs) -> None:
        self.executed.append((args, kwargs))
        return None

    def cursor(self, **_kwargs) -> _FakeCursor:
        return self.cursor_obj


def evidence(url: str, method: SourceMethod = SourceMethod.SCOUT_CHANGELOG) -> EvidenceRef:
    return EvidenceRef(source_url=url, captured_at=NOW, method=method, excerpt="proof")


def scorecard() -> RecommendationScorecard:
    return RecommendationScorecard(
        total_score=78,
        verdict="actionable",
        summary="Competitor product proof, public narrative, and demand all align.",
        dimension_scores=[
            RubricDimensionScore(
                dimension="product_reality",
                score=20,
                max_score=25,
                rationale="Constructor has release evidence.",
                evidence_urls=["https://constructor.com/changelog"],
            ),
            RubricDimensionScore(
                dimension="market_conversation",
                score=18,
                max_score=20,
                rationale="Constructor is publicly positioning the theme.",
                evidence_urls=["https://constructor.com/blog"],
            ),
            RubricDimensionScore(
                dimension="audience_demand",
                score=20,
                max_score=20,
                rationale="Algolia audience demand is rising.",
                evidence_urls=["looker://algolia/ga4/topics"],
            ),
            RubricDimensionScore(
                dimension="own_response_gap",
                score=10,
                max_score=15,
                rationale="Algolia has product proof but no matching narrative.",
                evidence_urls=["https://www.algolia.com/changelog/agentic-discovery"],
            ),
            RubricDimensionScore(
                dimension="evidence_breadth",
                score=10,
                max_score=20,
                rationale="Four distinct evidence refs support the recommendation.",
                evidence_urls=[
                    "https://constructor.com/changelog",
                    "https://constructor.com/blog",
                    "looker://algolia/ga4/topics",
                    "https://www.algolia.com/changelog/agentic-discovery",
                ],
            ),
        ],
    )


def test_save_product_change_event_targets_product_change_events() -> None:
    conn = _FakeConnection()
    event = ProductChangeEvent(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        capability="agentic product discovery",
        change_type="release",
        summary="Constructor shipped agentic product discovery",
        observed_at=NOW,
        evidence=[evidence("https://constructor.com/changelog")],
    )

    saved_id = PgProductMarketRepository(conn).save_product_change_event(event)

    assert saved_id == 123
    assert "INSERT INTO product_change_events" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["capability_text"] == "agentic product discovery"
    assert conn.cursor_obj.params["evidence_refs"].obj[0]["source_url"] == "https://constructor.com/changelog"


def test_save_demand_signal_targets_demand_signals() -> None:
    conn = _FakeConnection()
    signal = DemandSignal(
        tenant_id=1,
        topic="agentic product discovery",
        metric="engaged_sessions",
        value=1234,
        change_pct=0.23,
        period_start=NOW,
        period_end=NOW,
        source_label="Looker Studio GA4 export",
        evidence=[evidence("looker://algolia/ga4/topics", SourceMethod.LOOKER_EXPORT)],
        metadata={
            "source_file": "ga-pages.csv",
            "source_row_number": 1,
            "source_fingerprint": "b" * 64,
        },
    )

    PgProductMarketRepository(conn).save_demand_signal(signal)

    assert "INSERT INTO demand_signals" in conn.cursor_obj.sql
    assert "metadata->>'source_fingerprint'" in conn.cursor_obj.sql
    assert "%(source_fingerprint)s::text IS NOT NULL" in conn.cursor_obj.sql
    assert "metadata->>'source_fingerprint' = %(source_fingerprint)s::text" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["topic"] == "agentic product discovery"
    assert conn.cursor_obj.params["evidence_refs"].obj[0]["method"] == "looker_export"
    assert conn.cursor_obj.params["metadata"].obj["source_fingerprint"] == "b" * 64


def test_save_conversation_theme_targets_conversation_themes() -> None:
    conn = _FakeConnection()
    theme = ConversationTheme(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        theme="agentic product discovery",
        summary="Constructor is positioning around AI shopping agents.",
        intensity=0.82,
        observed_at=NOW,
        evidence=[evidence("https://constructor.com/blog", SourceMethod.WEB_SCAN)],
    )

    saved_id = PgProductMarketRepository(conn).save_conversation_theme(theme)

    assert saved_id == 123
    assert "INSERT INTO conversation_themes" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["competitor_id"] == 20
    assert conn.cursor_obj.params["theme"] == "agentic product discovery"
    assert conn.cursor_obj.params["evidence_refs"].obj[0]["method"] == "web_scan"


def test_save_pattern_and_recommendation_target_decision_tables() -> None:
    conn = _FakeConnection()
    pattern = PatternObservation(
        tenant_id=1,
        pattern_type="own_narrative_gap",
        capability="agentic product discovery",
        summary="Constructor is louder around a shipped capability.",
        involved_companies=["Algolia", "Constructor"],
        confidence=0.78,
        evidence=[evidence("https://constructor.com/changelog")],
    )
    recommendation = Recommendation(
        tenant_id=1,
        owner="PMM",
        action="Write the agentic product discovery narrative.",
        why_now="Competitor product proof, conversation, and demand align.",
        urgency="this_week",
        confidence=0.78,
        scorecard=scorecard(),
        evidence=[evidence("https://constructor.com/changelog")],
    )

    pattern_id = PgProductMarketRepository(conn).save_pattern_observation(pattern)
    PgProductMarketRepository(conn).save_recommendation(
        recommendation,
        pattern_observation_id=pattern_id,
    )

    assert "INSERT INTO argus_recommendations" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["pattern_observation_id"] == 123
    assert conn.cursor_obj.params["owner"] == "PMM"
    assert conn.cursor_obj.params["scorecard"].obj["total_score"] == 78
    assert conn.cursor_obj.params["scorecard"].obj["dimension_scores"][0]["dimension"] == "product_reality"


def test_get_current_patterns_reads_pattern_observations() -> None:
    conn = _FakeConnection(rows=[{"id": 1, "pattern_type": "own_narrative_gap"}])

    rows = PgProductMarketRepository(conn).get_current_patterns(tenant_id=1)

    assert rows == [{"id": 1, "pattern_type": "own_narrative_gap"}]
    assert "FROM pattern_observations" in conn.cursor_obj.sql
    assert "tenant_id = %s" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1,)


def test_get_current_recommendations_reads_argus_recommendations() -> None:
    conn = _FakeConnection(rows=[{"id": 4, "owner": "PMM"}])

    rows = PgProductMarketRepository(conn).get_current_recommendations(tenant_id=1)

    assert rows == [{"id": 4, "owner": "PMM"}]
    assert "FROM argus_recommendations" in conn.cursor_obj.sql
    assert "scorecard" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1,)


def test_get_current_demand_signals_reads_demand_signals() -> None:
    conn = _FakeConnection(rows=[{"id": 7, "topic": "agentic product discovery"}])

    rows = PgProductMarketRepository(conn).get_current_demand_signals(tenant_id=1)

    assert rows == [{"id": 7, "topic": "agentic product discovery"}]
    assert "FROM demand_signals" in conn.cursor_obj.sql
    assert "metadata" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1,)


def test_get_recent_product_events_reads_replayable_product_ledger_rows() -> None:
    conn = _FakeConnection(rows=[{"id": 1, "company_name": "Constructor"}])

    rows = PgProductMarketRepository(conn).get_recent_product_events(tenant_id=1, days=14, limit=50)

    assert rows == [{"id": 1, "company_name": "Constructor"}]
    assert "FROM product_change_events" in conn.cursor_obj.sql
    assert "observed_at >= now() - (%s * interval '1 day')" in conn.cursor_obj.sql
    assert "LIMIT %s" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, 14, 50)


def test_get_recent_conversation_themes_reads_replayable_conversation_ledger_rows() -> None:
    conn = _FakeConnection(rows=[{"id": 2, "theme": "agentic product discovery"}])

    rows = PgProductMarketRepository(conn).get_recent_conversation_themes(tenant_id=1, days=14, limit=50)

    assert rows == [{"id": 2, "theme": "agentic product discovery"}]
    assert "FROM conversation_themes" in conn.cursor_obj.sql
    assert "observed_at >= now() - (%s * interval '1 day')" in conn.cursor_obj.sql
    assert "LIMIT %s" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, 14, 50)


def test_get_recent_demand_signals_reads_replayable_demand_ledger_rows() -> None:
    conn = _FakeConnection(rows=[{"id": 3, "topic": "agentic product discovery"}])

    rows = PgProductMarketRepository(conn).get_recent_demand_signals(tenant_id=1, days=14, limit=50)

    assert rows == [{"id": 3, "topic": "agentic product discovery"}]
    assert "FROM demand_signals" in conn.cursor_obj.sql
    assert "period_end >= now() - (%s * interval '1 day')" in conn.cursor_obj.sql
    assert "LIMIT %s" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, 14, 50)


def test_get_feature_matrix_reads_company_feature_positions_joined_to_capabilities() -> None:
    conn = _FakeConnection(rows=[{"company_name": "Constructor", "capability_text": "agentic product discovery"}])

    rows = PgProductMarketRepository(conn).get_feature_matrix(tenant_id=1)

    assert rows == [{"company_name": "Constructor", "capability_text": "agentic product discovery"}]
    assert "FROM company_feature_positions" in conn.cursor_obj.sql
    assert "feature_capabilities" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1,)


def test_get_feature_matrix_filters_to_own_company_or_active_competitors() -> None:
    conn = _FakeConnection(rows=[])

    PgProductMarketRepository(conn).get_feature_matrix(tenant_id=1)

    sql = conn.cursor_obj.sql
    assert "LEFT JOIN competitors c" in sql
    assert "c.status = 'active'" in sql
    assert "cfp.company_role = 'own' OR c.id IS NOT NULL" in sql


def test_get_pattern_history_reads_recent_pattern_observations_for_tenant_window() -> None:
    conn = _FakeConnection(rows=[{"id": 11, "capability_text": "agentic product discovery"}])

    rows = PgProductMarketRepository(conn).get_pattern_history(tenant_id=1, days=30, limit=100)

    assert rows == [{"id": 11, "capability_text": "agentic product discovery"}]
    assert "FROM pattern_observations" in conn.cursor_obj.sql
    assert "created_at >= now() - (%s * interval '1 day')" in conn.cursor_obj.sql
    assert "LIMIT %s" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, 30, 100)


def test_save_run_intelligence_summary_targets_product_market_run_intelligence() -> None:
    conn = _FakeConnection(row={"id": 456})
    summary = ProductMarketRunSummary(
        tenant_id=1,
        verdict="watch",
        product_event_count=4,
        conversation_theme_count=3,
        demand_signal_count=2,
        feature_position_count=5,
        pattern_count=1,
        recommendation_count=0,
        learning_instruction_count=2,
        learning_instruction_improvement_ids=[202, 303],
        intelligence_brief=ProductMarketIntelligenceBrief(
            verdict="watch",
            top_insight="Constructor moved, but coverage recheck held the action.",
            primary_action=None,
            watchlist=["Recheck Coveo coverage"],
            evidence_urls=["https://constructor.com/changelog"],
            confidence_limits=["Coverage learning gate was active."],
            next_questions=["Did Coveo publish a matching release?"],
        ),
    )

    saved_id = PgProductMarketRepository(conn).save_run_intelligence_summary(summary)

    assert saved_id == 456
    assert "INSERT INTO product_market_run_intelligence" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["verdict"] == "watch"
    assert conn.cursor_obj.params["product_event_count"] == 4
    assert conn.cursor_obj.params["intelligence_brief"].obj["top_insight"].startswith("Constructor moved")
    assert conn.cursor_obj.params["learning_instruction_improvement_ids"].obj == [202, 303]


def test_get_latest_run_intelligence_reads_latest_brain_record() -> None:
    conn = _FakeConnection(rows=[{"id": 8, "verdict": "actionable", "intelligence_brief": {"top_insight": "Ship now"}}])

    rows = PgProductMarketRepository(conn).get_latest_run_intelligence(tenant_id=1, limit=1)

    assert rows == [{"id": 8, "verdict": "actionable", "intelligence_brief": {"top_insight": "Ship now"}}]
    assert "FROM product_market_run_intelligence" in conn.cursor_obj.sql
    assert "ORDER BY created_at DESC, id DESC" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, 1)


def test_save_run_stage_ledger_targets_parent_and_event_tables() -> None:
    conn = _FakeConnection(row={"id": 789})
    ledger_id = PgProductMarketRepository(conn).save_run_stage_ledger(
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        package_name="cios.product_market",
        status="completed",
        stage_ledger=[
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
                "status": "failed",
                "started_at": "2026-07-11T22:35:06Z",
                "ended_at": "2026-07-11T22:35:09Z",
                "elapsed_s": 3.2,
                "error_type": "RuntimeError",
                "error": "boom",
            },
        ],
        metadata={"source": "daily_production_run"},
    )

    sql_history = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert ledger_id == 789
    assert "INSERT INTO run_stage_ledgers" in sql_history
    assert "INSERT INTO run_stage_events" in sql_history
    parent_params = conn.cursor_obj.executed[0][1]
    event_params = conn.cursor_obj.executed[1][1]
    assert parent_params["tenant_id"] == 1
    assert parent_params["run_id"] == "daily-algolia-2026-07-11"
    assert parent_params["package_name"] == "cios.product_market"
    assert parent_params["status"] == "completed"
    assert parent_params["metadata"].obj == {"source": "daily_production_run"}
    assert event_params["events"].obj[0]["stage_order"] == 1
    assert event_params["events"].obj[0]["stage"] == "product_surface_export"
    assert event_params["events"].obj[1]["stage_order"] == 2
    assert event_params["events"].obj[1]["status"] == "failed"
    assert event_params["events"].obj[1]["error_type"] == "RuntimeError"


def test_get_latest_run_stage_ledger_rehydrates_parent_and_events() -> None:
    conn = _FakeConnection(
        row={
            "id": 789,
            "tenant_id": 1,
            "run_id": "daily-algolia-2026-07-11",
            "package_name": "cios.product_market",
            "status": "completed",
            "started_at": NOW,
            "ended_at": NOW,
            "metadata": {"source": "daily_production_run"},
            "stage_ledger": [
                {
                    "stage": "product_surface_export",
                    "status": "completed",
                    "elapsed_s": 5.1,
                }
            ],
        }
    )

    row = PgProductMarketRepository(conn).get_latest_run_stage_ledger(
        tenant_id=1,
        package_name="cios.product_market",
    )

    assert row["id"] == 789
    assert row["run_id"] == "daily-algolia-2026-07-11"
    assert row["stage_ledger"][0]["stage"] == "product_surface_export"
    assert "FROM run_stage_ledgers" in conn.cursor_obj.sql
    assert "run_stage_events" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, "cios.product_market")


def test_save_feature_position_upserts_capability_position_and_evidence_links() -> None:
    conn = _FakeConnection(row={"id": 321})
    position = FeaturePosition(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        capability="agentic product discovery",
        position_status="proven",
        summary="Constructor shipped agentic product discovery.",
        last_seen_at=NOW,
        confidence=0.72,
        evidence=[evidence("https://constructor.com/changelog")],
    )

    saved_id = PgProductMarketRepository(conn).save_feature_position(position)

    sql_history = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert saved_id == 321
    assert "INSERT INTO feature_capabilities" in sql_history
    assert "INSERT INTO company_feature_positions" in sql_history
    assert "INSERT INTO feature_evidence_links" in sql_history
    assert conn.cursor_obj.executed[0][1]["canonical_name"] == "agentic product discovery"
    assert conn.cursor_obj.executed[0][1]["position_status"] == "proven"
    assert conn.cursor_obj.executed[1][1]["evidence_refs"].obj[0]["source_url"] == "https://constructor.com/changelog"
