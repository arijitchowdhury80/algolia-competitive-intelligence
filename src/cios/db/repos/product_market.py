"""Postgres repository for Argus product-market intelligence rows."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.db.repos.collect import _postgres_safe
from cios.db.session import tenant_context
from cios.intelligence.types import (
    ConversationTheme,
    DemandSignal,
    EvidenceRef,
    FeaturePosition,
    PatternObservation,
    ProductChangeEvent,
    Recommendation,
)


def _evidence_refs_json(evidence: list[EvidenceRef]) -> Json:
    return Json(_postgres_safe([item.model_dump(mode="json") for item in evidence]))


def _stage_event_rows(stage_ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(stage_ledger, start=1):
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                "stage_order": index,
                "stage": _postgres_safe(str(raw.get("stage") or "")),
                "status": _postgres_safe(str(raw.get("status") or "")),
                "started_at": raw.get("started_at"),
                "ended_at": raw.get("ended_at"),
                "elapsed_s": raw.get("elapsed_s"),
                "error_type": _postgres_safe(raw.get("error_type")),
                "error": _postgres_safe(raw.get("error")),
                "metadata": _postgres_safe(
                    {
                        key: value
                        for key, value in raw.items()
                        if key
                        not in {
                            "stage",
                            "status",
                            "started_at",
                            "ended_at",
                            "elapsed_s",
                            "error_type",
                            "error",
                        }
                    }
                ),
            }
        )
    return rows


class PgProductMarketRepository:
    """Persistence boundary for product muscle, demand, patterns, and actions.

    The pure intelligence package has no DB dependency. This repo is the bridge
    that stores its value objects in tenant-scoped Postgres tables protected by
    schema.sql's RLS policy.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def save_product_change_event(self, event: ProductChangeEvent) -> int:
        with tenant_context(self._conn, event.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO product_change_events (
                        tenant_id, competitor_id, company_name, company_role,
                        capability_text, change_type, summary, observed_at,
                        evidence_refs, confidence
                    ) VALUES (
                        %(tenant_id)s, %(competitor_id)s, %(company_name)s, %(company_role)s,
                        %(capability_text)s, %(change_type)s, %(summary)s, %(observed_at)s,
                        %(evidence_refs)s, %(confidence)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": event.tenant_id,
                        "competitor_id": None if event.company_role == "own" else event.company_id,
                        "company_name": _postgres_safe(event.company_name),
                        "company_role": event.company_role,
                        "capability_text": _postgres_safe(event.capability),
                        "change_type": event.change_type,
                        "summary": _postgres_safe(event.summary),
                        "observed_at": event.observed_at,
                        "evidence_refs": _evidence_refs_json(event.evidence),
                        "confidence": None,
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def save_conversation_theme(self, theme: ConversationTheme) -> int:
        with tenant_context(self._conn, theme.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_themes (
                        tenant_id, competitor_id, company_name, theme, summary,
                        intensity, observed_at, evidence_refs
                    ) VALUES (
                        %(tenant_id)s, %(competitor_id)s, %(company_name)s, %(theme)s,
                        %(summary)s, %(intensity)s, %(observed_at)s, %(evidence_refs)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": theme.tenant_id,
                        "competitor_id": theme.company_id,
                        "company_name": _postgres_safe(theme.company_name),
                        "theme": _postgres_safe(theme.theme),
                        "summary": _postgres_safe(theme.summary),
                        "intensity": theme.intensity,
                        "observed_at": theme.observed_at,
                        "evidence_refs": _evidence_refs_json(theme.evidence),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def save_demand_signal(self, signal: DemandSignal) -> int:
        with tenant_context(self._conn, signal.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH existing_signal AS (
                        UPDATE demand_signals
                        SET
                            topic = %(topic)s,
                            metric = %(metric)s,
                            value = %(value)s,
                            change_pct = %(change_pct)s,
                            period_start = %(period_start)s,
                            period_end = %(period_end)s,
                            source_label = %(source_label)s,
                            evidence_refs = %(evidence_refs)s,
                            metadata = %(metadata)s
                        WHERE tenant_id = %(tenant_id)s
                          AND %(source_fingerprint)s::text IS NOT NULL
                          AND metadata->>'source_fingerprint' = %(source_fingerprint)s::text
                        RETURNING id
                    ),
                    inserted_signal AS (
                        INSERT INTO demand_signals (
                            tenant_id, topic, metric, value, change_pct, period_start,
                            period_end, source_label, evidence_refs, metadata
                        )
                        SELECT
                            %(tenant_id)s, %(topic)s, %(metric)s, %(value)s, %(change_pct)s,
                            %(period_start)s, %(period_end)s, %(source_label)s,
                            %(evidence_refs)s, %(metadata)s
                        WHERE NOT EXISTS (SELECT 1 FROM existing_signal)
                        RETURNING id
                    )
                    SELECT id FROM existing_signal
                    UNION ALL
                    SELECT id FROM inserted_signal
                    LIMIT 1
                    """,
                    {
                        "tenant_id": signal.tenant_id,
                        "topic": _postgres_safe(signal.topic),
                        "metric": _postgres_safe(signal.metric),
                        "value": signal.value,
                        "change_pct": signal.change_pct,
                        "period_start": signal.period_start,
                        "period_end": signal.period_end,
                        "source_label": _postgres_safe(signal.source_label),
                        "evidence_refs": _evidence_refs_json(signal.evidence),
                        "metadata": Json(_postgres_safe(signal.metadata)),
                        "source_fingerprint": signal.metadata.get("source_fingerprint"),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def save_feature_position(self, position: FeaturePosition) -> int:
        with tenant_context(self._conn, position.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH capability AS (
                        INSERT INTO feature_capabilities (
                            tenant_id, canonical_name, status, updated_at
                        ) VALUES (
                            %(tenant_id)s, %(canonical_name)s, 'active', now()
                        )
                        ON CONFLICT (tenant_id, canonical_name)
                        DO UPDATE SET updated_at = now()
                        RETURNING id
                    )
                    INSERT INTO company_feature_positions (
                        tenant_id, feature_capability_id, competitor_id,
                        company_name, company_role, position_status, summary,
                        last_seen_at, evidence_refs, confidence, updated_at
                    )
                    SELECT
                        %(tenant_id)s, capability.id, %(competitor_id)s,
                        %(company_name)s, %(company_role)s, %(position_status)s,
                        %(summary)s, %(last_seen_at)s, %(evidence_refs)s,
                        %(confidence)s, now()
                    FROM capability
                    ON CONFLICT (tenant_id, feature_capability_id, company_role, company_name)
                    DO UPDATE SET
                        competitor_id = EXCLUDED.competitor_id,
                        position_status = EXCLUDED.position_status,
                        summary = EXCLUDED.summary,
                        last_seen_at = EXCLUDED.last_seen_at,
                        evidence_refs = EXCLUDED.evidence_refs,
                        confidence = EXCLUDED.confidence,
                        updated_at = now()
                    RETURNING id
                    """,
                    {
                        "tenant_id": position.tenant_id,
                        "canonical_name": _postgres_safe(position.capability),
                        "competitor_id": None if position.company_role == "own" else position.company_id,
                        "company_name": _postgres_safe(position.company_name),
                        "company_role": position.company_role,
                        "position_status": position.position_status,
                        "summary": _postgres_safe(position.summary),
                        "last_seen_at": position.last_seen_at,
                        "evidence_refs": _evidence_refs_json(position.evidence),
                        "confidence": position.confidence,
                    },
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    WITH capability AS (
                        SELECT id
                        FROM feature_capabilities
                        WHERE tenant_id = %(tenant_id)s
                          AND canonical_name = %(canonical_name)s
                    )
                    INSERT INTO feature_evidence_links (
                        tenant_id, feature_capability_id, source_url, captured_at,
                        method, evidence_text
                    )
                    SELECT
                        %(tenant_id)s,
                        capability.id,
                        evidence.source_url,
                        evidence.captured_at,
                        evidence.method,
                        evidence.excerpt
                    FROM capability,
                    jsonb_to_recordset(%(evidence_refs)s::jsonb) AS evidence(
                        source_url text,
                        captured_at timestamptz,
                        method text,
                        excerpt text
                    )
                    """,
                    {
                        "tenant_id": position.tenant_id,
                        "canonical_name": _postgres_safe(position.capability),
                        "evidence_refs": _evidence_refs_json(position.evidence),
                    },
                )
        assert row is not None
        return int(row["id"])

    def save_pattern_observation(self, pattern: PatternObservation) -> int:
        with tenant_context(self._conn, pattern.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO pattern_observations (
                        tenant_id, pattern_type, capability_text, summary,
                        involved_companies, confidence, evidence_refs
                    ) VALUES (
                        %(tenant_id)s, %(pattern_type)s, %(capability_text)s, %(summary)s,
                        %(involved_companies)s, %(confidence)s, %(evidence_refs)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": pattern.tenant_id,
                        "pattern_type": pattern.pattern_type,
                        "capability_text": _postgres_safe(pattern.capability),
                        "summary": _postgres_safe(pattern.summary),
                        "involved_companies": Json(_postgres_safe(pattern.involved_companies)),
                        "confidence": pattern.confidence,
                        "evidence_refs": _evidence_refs_json(pattern.evidence),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def save_recommendation(
        self,
        recommendation: Recommendation,
        *,
        pattern_observation_id: int | None = None,
    ) -> int:
        with tenant_context(self._conn, recommendation.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO argus_recommendations (
                        tenant_id, pattern_observation_id, owner, action, why_now,
                        urgency, confidence, scorecard, evidence_refs
                    ) VALUES (
                        %(tenant_id)s, %(pattern_observation_id)s, %(owner)s, %(action)s,
                        %(why_now)s, %(urgency)s, %(confidence)s, %(scorecard)s,
                        %(evidence_refs)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": recommendation.tenant_id,
                        "pattern_observation_id": pattern_observation_id,
                        "owner": recommendation.owner,
                        "action": _postgres_safe(recommendation.action),
                        "why_now": _postgres_safe(recommendation.why_now),
                        "urgency": recommendation.urgency,
                        "confidence": recommendation.confidence,
                        "scorecard": Json(_postgres_safe(recommendation.scorecard.model_dump(mode="json"))),
                        "evidence_refs": _evidence_refs_json(recommendation.evidence),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def save_run_intelligence_summary(self, summary: Any) -> int:
        """Persist the run-level Argus read after workflow synthesis.

        The repository intentionally accepts the runner's pydantic object by
        duck type so the DB adapter remains a boundary, not an import cycle
        anchor. Stored JSON is sanitized at the persistence edge.
        """

        brief = summary.intelligence_brief.model_dump(mode="json")
        with tenant_context(self._conn, int(summary.tenant_id)):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO product_market_run_intelligence (
                        tenant_id, verdict, intelligence_brief,
                        product_event_count, conversation_theme_count,
                        demand_signal_count, feature_position_count,
                        pattern_count, recommendation_count,
                        learning_instruction_count, learning_instruction_improvement_ids
                    ) VALUES (
                        %(tenant_id)s, %(verdict)s, %(intelligence_brief)s,
                        %(product_event_count)s, %(conversation_theme_count)s,
                        %(demand_signal_count)s, %(feature_position_count)s,
                        %(pattern_count)s, %(recommendation_count)s,
                        %(learning_instruction_count)s, %(learning_instruction_improvement_ids)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": int(summary.tenant_id),
                        "verdict": _postgres_safe(summary.verdict),
                        "intelligence_brief": Json(_postgres_safe(brief)),
                        "product_event_count": int(summary.product_event_count),
                        "conversation_theme_count": int(summary.conversation_theme_count),
                        "demand_signal_count": int(summary.demand_signal_count),
                        "feature_position_count": int(summary.feature_position_count),
                        "pattern_count": int(summary.pattern_count),
                        "recommendation_count": int(summary.recommendation_count),
                        "learning_instruction_count": int(summary.learning_instruction_count),
                        "learning_instruction_improvement_ids": Json(
                            _postgres_safe(summary.learning_instruction_improvement_ids)
                        ),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def get_latest_run_intelligence(self, tenant_id: int, limit: int = 10) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, verdict, intelligence_brief,
                           product_event_count, conversation_theme_count,
                           demand_signal_count, feature_position_count,
                           pattern_count, recommendation_count,
                           learning_instruction_count,
                           learning_instruction_improvement_ids,
                           created_at
                    FROM product_market_run_intelligence
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant_id, limit),
                )
                rows = cur.fetchall()
        return list(rows)

    def save_run_stage_ledger(
        self,
        *,
        tenant_id: int,
        run_id: str,
        package_name: str,
        status: str,
        stage_ledger: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Persist ordered stage execution truth for one Hermes-invoked package run."""

        events = _stage_event_rows(stage_ledger)
        started_at = events[0].get("started_at") if events else None
        ended_at = events[-1].get("ended_at") if events else None
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO run_stage_ledgers (
                        tenant_id, run_id, package_name, status, started_at,
                        ended_at, metadata
                    ) VALUES (
                        %(tenant_id)s, %(run_id)s, %(package_name)s, %(status)s,
                        %(started_at)s, %(ended_at)s, %(metadata)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": tenant_id,
                        "run_id": _postgres_safe(run_id),
                        "package_name": _postgres_safe(package_name),
                        "status": _postgres_safe(status),
                        "started_at": started_at,
                        "ended_at": ended_at,
                        "metadata": Json(_postgres_safe(metadata or {})),
                    },
                )
                row = cur.fetchone()
                assert row is not None
                ledger_id = int(row["id"])
                if events:
                    cur.execute(
                        """
                        INSERT INTO run_stage_events (
                            tenant_id, ledger_id, stage_order, stage, status,
                            started_at, ended_at, elapsed_s, error_type, error,
                            metadata
                        )
                        SELECT
                            %(tenant_id)s,
                            %(ledger_id)s,
                            event.stage_order,
                            event.stage,
                            event.status,
                            NULLIF(event.started_at, '')::timestamptz,
                            NULLIF(event.ended_at, '')::timestamptz,
                            event.elapsed_s,
                            event.error_type,
                            event.error,
                            COALESCE(event.metadata, '{}'::jsonb)
                        FROM jsonb_to_recordset(%(events)s::jsonb) AS event(
                            stage_order integer,
                            stage text,
                            status text,
                            started_at text,
                            ended_at text,
                            elapsed_s numeric,
                            error_type text,
                            error text,
                            metadata jsonb
                        )
                        """,
                        {
                            "tenant_id": tenant_id,
                            "ledger_id": ledger_id,
                            "events": Json(_postgres_safe(events)),
                        },
                    )
        return ledger_id

    def get_latest_run_stage_ledger(
        self,
        *,
        tenant_id: int,
        package_name: str,
    ) -> dict[str, Any] | None:
        """Read the latest persisted stage ledger for one package."""

        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        l.id,
                        l.tenant_id,
                        l.run_id,
                        l.package_name,
                        l.status,
                        l.started_at,
                        l.ended_at,
                        l.metadata,
                        COALESCE(
                            jsonb_agg(
                                jsonb_build_object(
                                    'stage_order', e.stage_order,
                                    'stage', e.stage,
                                    'status', e.status,
                                    'started_at', e.started_at,
                                    'ended_at', e.ended_at,
                                    'elapsed_s', e.elapsed_s,
                                    'error_type', e.error_type,
                                    'error', e.error,
                                    'metadata', e.metadata
                                )
                                ORDER BY e.stage_order
                            ) FILTER (WHERE e.id IS NOT NULL),
                            '[]'::jsonb
                        ) AS stage_ledger
                    FROM run_stage_ledgers l
                    LEFT JOIN run_stage_events e
                      ON e.tenant_id = l.tenant_id
                     AND e.ledger_id = l.id
                    WHERE l.tenant_id = %s
                      AND l.package_name = %s
                    GROUP BY l.id, l.tenant_id, l.run_id, l.package_name,
                             l.status, l.started_at, l.ended_at, l.metadata
                    ORDER BY l.started_at DESC NULLS LAST, l.id DESC
                    LIMIT 1
                    """,
                    (tenant_id, package_name),
                )
                row = cur.fetchone()
        return dict(row) if row is not None else None

    def get_current_patterns(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, pattern_type, capability_text, summary, involved_companies,
                           confidence, evidence_refs, created_at
                    FROM pattern_observations
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 20
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_current_recommendations(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, pattern_observation_id, owner, action, why_now, urgency,
                           confidence, scorecard, evidence_refs, status, created_at
                    FROM argus_recommendations
                    WHERE tenant_id = %s
                    ORDER BY
                        CASE urgency
                            WHEN 'act_now' THEN 0
                            WHEN 'this_week' THEN 1
                            WHEN 'this_month' THEN 2
                            ELSE 3
                        END,
                        created_at DESC,
                        id DESC
                    LIMIT 20
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_current_demand_signals(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, topic, metric, value, change_pct, period_start,
                           period_end, source_label, evidence_refs, metadata,
                           created_at
                    FROM demand_signals
                    WHERE tenant_id = %s
                    ORDER BY period_end DESC, id DESC
                    LIMIT 20
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_recent_product_events(
        self,
        tenant_id: int,
        days: int = 30,
        limit: int = 500,
    ) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id, tenant_id, competitor_id, company_name, company_role,
                        capability_text, change_type, summary, observed_at,
                        evidence_refs, confidence, created_at
                    FROM product_change_events
                    WHERE tenant_id = %s
                      AND observed_at >= now() - (%s * interval '1 day')
                    ORDER BY observed_at DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant_id, days, limit),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_recent_conversation_themes(
        self,
        tenant_id: int,
        days: int = 30,
        limit: int = 500,
    ) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id, tenant_id, competitor_id, company_name, theme, summary,
                        intensity, observed_at, evidence_refs, created_at
                    FROM conversation_themes
                    WHERE tenant_id = %s
                      AND observed_at >= now() - (%s * interval '1 day')
                    ORDER BY observed_at DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant_id, days, limit),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_recent_demand_signals(
        self,
        tenant_id: int,
        days: int = 30,
        limit: int = 500,
    ) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id, tenant_id, topic, metric, value, change_pct, period_start,
                        period_end, source_label, evidence_refs, metadata, created_at
                    FROM demand_signals
                    WHERE tenant_id = %s
                      AND period_end >= now() - (%s * interval '1 day')
                    ORDER BY period_end DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant_id, days, limit),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_feature_matrix(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(fc.canonical_name, cfp.summary, cfp.company_name) AS capability_text,
                        cfp.company_name,
                        cfp.company_role,
                        cfp.position_status,
                        cfp.summary,
                        cfp.confidence,
                        cfp.evidence_refs,
                        cfp.updated_at
                    FROM company_feature_positions cfp
                    LEFT JOIN feature_capabilities fc
                        ON fc.id = cfp.feature_capability_id
                       AND fc.tenant_id = cfp.tenant_id
                    LEFT JOIN competitors c
                        ON c.tenant_id = cfp.tenant_id
                       AND c.id = cfp.competitor_id
                       AND c.status = 'active'
                    WHERE cfp.tenant_id = %s
                      AND (cfp.company_role = 'own' OR c.id IS NOT NULL)
                    ORDER BY capability_text, cfp.company_role, cfp.company_name
                    LIMIT 200
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return list(rows)

    def get_pattern_history(self, tenant_id: int, days: int = 30, limit: int = 100) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, pattern_type, capability_text, summary, involved_companies,
                           confidence, evidence_refs, created_at
                    FROM pattern_observations
                    WHERE tenant_id = %s
                      AND created_at >= now() - (%s * interval '1 day')
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant_id, days, limit),
                )
                rows = cur.fetchall()
        return list(rows)


__all__ = ["PgProductMarketRepository"]
