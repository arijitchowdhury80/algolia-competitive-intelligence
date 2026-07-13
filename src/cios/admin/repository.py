"""Repository layer for the CI-OS local admin app."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.admin.types import (
    ArgusRunStatus,
    ArgusRunIntelligenceRecord,
    ConversationThemeAdminRecord,
    CompetitorAdminRecord,
    CompetitorCreate,
    CompetitorUpdate,
    DemandSignalAdminRecord,
    EvidenceLedgerState,
    FeatureMatrixAdminRecord,
    ImprovementAdminRecord,
    ImprovementStatusUpdate,
    PatternObservationAdminRecord,
    ProductEventAdminRecord,
    ProductSurfaceAdminRecord,
    ProductSurfaceCreate,
    ProductSurfaceUpdate,
    RecommendationAdminRecord,
    RecommendationStatusUpdate,
    RegistryState,
    SourceAdminRecord,
    SourceCreate,
    SourceUpdate,
)
from cios.db.session import tenant_context
from cios.hunter.validator import normalize_url
from cios.learn.feedback import NextSweepPlanner
from cios.learn.types import ImprovementItem, ImprovementPriority, ImprovementStatus

COMPETITOR_STATUSES = {"active", "paused", "retired"}
SOURCE_STATUSES = {"active", "candidate", "blocked", "missing", "retired", "needs_credentials", "not_applicable"}
PRODUCT_SURFACE_STATUSES = {"active", "candidate", "paused", "retired", "failed"}
IMPROVEMENT_STATUSES = {"open", "approved", "applied", "rejected"}
RECOMMENDATION_STATUSES = {"open", "accepted", "dismissed", "done"}


class AdminRepository(Protocol):
    def registry(self, tenant_slug: str) -> RegistryState: ...

    def latest_run_status(self, tenant_slug: str) -> ArgusRunStatus: ...

    def create_competitor(self, tenant_slug: str, payload: CompetitorCreate) -> CompetitorAdminRecord: ...

    def update_competitor(
        self, tenant_slug: str, competitor_id: int, payload: CompetitorUpdate
    ) -> CompetitorAdminRecord: ...

    def create_source(self, tenant_slug: str, competitor_id: int, payload: SourceCreate) -> SourceAdminRecord: ...

    def update_source(self, tenant_slug: str, source_id: int, payload: SourceUpdate) -> SourceAdminRecord: ...

    def create_product_surface(
        self, tenant_slug: str, competitor_id: int, payload: ProductSurfaceCreate
    ) -> ProductSurfaceAdminRecord: ...

    def update_product_surface(
        self, tenant_slug: str, surface_id: int, payload: ProductSurfaceUpdate
    ) -> ProductSurfaceAdminRecord: ...

    def list_improvements(self, tenant_slug: str, status: str | None = "open") -> list[ImprovementAdminRecord]: ...

    def update_improvement_status(
        self, tenant_slug: str, improvement_id: int, payload: ImprovementStatusUpdate
    ) -> ImprovementAdminRecord: ...

    def next_sweep_plan(self, tenant_slug: str) -> dict: ...

    def feature_matrix(self, tenant_slug: str) -> list[FeatureMatrixAdminRecord]: ...

    def evidence_ledger(self, tenant_slug: str) -> EvidenceLedgerState: ...

    def list_recommendations(
        self, tenant_slug: str, status: str | None = "open"
    ) -> list[RecommendationAdminRecord]: ...

    def update_recommendation_status(
        self, tenant_slug: str, recommendation_id: int, payload: RecommendationStatusUpdate
    ) -> RecommendationAdminRecord: ...


def _validate_status(status: str | None, allowed: set[str], *, field: str) -> str | None:
    if status is None:
        return None
    if status not in allowed:
        allowed_s = ", ".join(sorted(allowed))
        raise ValueError(f"{field} must be one of: {allowed_s}")
    return status


class PgAdminRepository:
    """Postgres-backed admin repository.

    The only cross-tenant lookup is resolving `tenants.slug` to id; all
    tenant-scoped reads/writes then run through `tenant_context`.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def _tenant_id(self, tenant_slug: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,))
            row = cur.fetchone()
        if row is None:
            raise LookupError(f"tenant not found: {tenant_slug}")
        return int(row[0])

    def registry(self, tenant_slug: str) -> RegistryState:
        tenant_id = self._tenant_id(tenant_slug)
        competitors = self._competitors(tenant_id)
        sources_by_competitor = self._sources_by_competitor(tenant_id)
        surfaces_by_competitor = self._product_surfaces_by_competitor(tenant_id)
        records = [
            CompetitorAdminRecord(
                **competitor,
                sources=sources_by_competitor.get(competitor["competitor_id"], []),
                product_surfaces=surfaces_by_competitor.get(competitor["competitor_id"], []),
            )
            for competitor in competitors
        ]
        return RegistryState(
            tenant_slug=tenant_slug,
            tenant_id=tenant_id,
            competitors=records,
            improvements=self._improvements(tenant_id, status="open"),
        )

    def latest_run_status(self, tenant_slug: str) -> ArgusRunStatus:
        tenant_id = self._tenant_id(tenant_slug)
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT tenant_id,
                           %s AS tenant_slug,
                           id AS report_id,
                           report_date,
                           cadence,
                           status AS report_status,
                           created_at AS generated_at,
                           metadata
                    FROM reports
                    WHERE tenant_id = %s
                    ORDER BY report_date DESC, id DESC
                    LIMIT 1
                    """,
                    (tenant_slug, tenant_id),
                )
                row = cur.fetchone()
        run_intelligence_history = self._latest_run_intelligence_history(tenant_id)
        latest_intelligence = run_intelligence_history[0] if run_intelligence_history else None
        if row is None:
            return ArgusRunStatus(
                tenant_slug=tenant_slug,
                tenant_id=tenant_id,
                latest_intelligence_brief=self._intelligence_brief_from_record(latest_intelligence),
                run_intelligence_history=run_intelligence_history,
            )
        status = self._run_status_from_report_row(dict(row))
        persisted_brief = self._intelligence_brief_from_record(latest_intelligence)
        if persisted_brief:
            status = status.model_copy(
                update={
                    "latest_intelligence_brief": persisted_brief,
                    "run_intelligence_history": run_intelligence_history,
                }
            )
        else:
            status = status.model_copy(update={"run_intelligence_history": run_intelligence_history})
        return status

    def create_competitor(self, tenant_slug: str, payload: CompetitorCreate) -> CompetitorAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO competitors (tenant_id, name, domain, category, priority, status)
                    VALUES (%s, %s, %s, %s, %s, 'active')
                    ON CONFLICT (tenant_id, name) DO UPDATE SET
                        domain = EXCLUDED.domain,
                        category = EXCLUDED.category,
                        priority = EXCLUDED.priority,
                        status = 'active',
                        updated_at = now()
                    RETURNING id AS competitor_id, name AS competitor_name,
                              domain, category, priority, status
                    """,
                    (tenant_id, payload.name, payload.domain, payload.category, payload.priority),
                )
                row = dict(cur.fetchone())
        return CompetitorAdminRecord(**row, sources=[])

    def update_competitor(
        self, tenant_slug: str, competitor_id: int, payload: CompetitorUpdate
    ) -> CompetitorAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, COMPETITOR_STATUSES, field="competitor status")
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE competitors SET
                        name = COALESCE(%s, name),
                        domain = COALESCE(%s, domain),
                        category = COALESCE(%s, category),
                        priority = COALESCE(%s, priority),
                        status = COALESCE(%s, status),
                        updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    RETURNING id AS competitor_id, name AS competitor_name,
                              domain, category, priority, status
                    """,
                    (
                        payload.name,
                        payload.domain,
                        payload.category,
                        payload.priority,
                        status,
                        tenant_id,
                        competitor_id,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise LookupError(f"competitor not found: {competitor_id}")
        return CompetitorAdminRecord(**dict(row), sources=[])

    def create_source(self, tenant_slug: str, competitor_id: int, payload: SourceCreate) -> SourceAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, SOURCE_STATUSES, field="source status")
        normalized_url = normalize_url(str(payload.url))
        now = datetime.now(timezone.utc)
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO sources (
                        tenant_id, competitor_id, source_family, url, normalized_url,
                        title, status, first_seen_at, last_seen_at, evidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
                    ON CONFLICT (tenant_id, normalized_url) DO UPDATE SET
                        competitor_id = EXCLUDED.competitor_id,
                        source_family = EXCLUDED.source_family,
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        status = EXCLUDED.status,
                        last_seen_at = EXCLUDED.last_seen_at,
                        evidence = sources.evidence || EXCLUDED.evidence
                    RETURNING id AS source_id, source_family, url, status,
                              NULL::text AS latest_event_type,
                              NULL::integer AS http_status,
                              NULL::text AS detail,
                              last_checked_at AS checked_at
                    """,
                    (
                        tenant_id,
                        competitor_id,
                        payload.source_family,
                        str(payload.url),
                        normalized_url,
                        payload.title,
                        status,
                        now,
                        now,
                    ),
                )
                row = dict(cur.fetchone())
        return SourceAdminRecord(**row)

    def update_source(self, tenant_slug: str, source_id: int, payload: SourceUpdate) -> SourceAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, SOURCE_STATUSES, field="source status")
        url = str(payload.url) if payload.url is not None else None
        normalized_url = normalize_url(url) if url else None
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE sources SET
                        source_family = COALESCE(%s, source_family),
                        url = COALESCE(%s, url),
                        normalized_url = COALESCE(%s, normalized_url),
                        title = COALESCE(%s, title),
                        status = COALESCE(%s, status),
                        retired_at = CASE WHEN %s = 'retired' THEN now() ELSE retired_at END
                    WHERE tenant_id = %s AND id = %s
                    RETURNING id AS source_id, source_family, url, status,
                              NULL::text AS latest_event_type,
                              NULL::integer AS http_status,
                              NULL::text AS detail,
                              last_checked_at AS checked_at
                    """,
                    (
                        payload.source_family,
                        url,
                        normalized_url,
                        payload.title,
                        status,
                        status,
                        tenant_id,
                        source_id,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise LookupError(f"source not found: {source_id}")
        return SourceAdminRecord(**dict(row))

    def create_product_surface(
        self, tenant_slug: str, competitor_id: int, payload: ProductSurfaceCreate
    ) -> ProductSurfaceAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, PRODUCT_SURFACE_STATUSES, field="product surface status")
        normalized_url = normalize_url(str(payload.url))
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT name FROM competitors WHERE tenant_id = %s AND id = %s",
                    (tenant_id, competitor_id),
                )
                competitor = cur.fetchone()
                if competitor is None:
                    raise LookupError(f"competitor not found: {competitor_id}")
                company_name = competitor["name"]
                cur.execute(
                    """
                    INSERT INTO product_surfaces (
                        tenant_id, competitor_id, company_name, company_role,
                        surface_family, url, normalized_url, status, updated_at
                    )
                    VALUES (%s, %s, %s, 'competitor', %s, %s, %s, %s, now())
                    ON CONFLICT (tenant_id, normalized_url) DO UPDATE SET
                        competitor_id = EXCLUDED.competitor_id,
                        company_name = EXCLUDED.company_name,
                        company_role = EXCLUDED.company_role,
                        surface_family = EXCLUDED.surface_family,
                        url = EXCLUDED.url,
                        status = EXCLUDED.status,
                        updated_at = now()
                    RETURNING id AS surface_id, company_name, company_role,
                              surface_family, url, status, last_checked_at
                    """,
                    (
                        tenant_id,
                        competitor_id,
                        company_name,
                        payload.surface_family,
                        str(payload.url),
                        normalized_url,
                        status,
                    ),
                )
                row = cur.fetchone()
        assert row is not None
        return ProductSurfaceAdminRecord(**dict(row))

    def update_product_surface(
        self, tenant_slug: str, surface_id: int, payload: ProductSurfaceUpdate
    ) -> ProductSurfaceAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, PRODUCT_SURFACE_STATUSES, field="product surface status")
        url = str(payload.url) if payload.url is not None else None
        normalized_url = normalize_url(url) if url else None
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE product_surfaces SET
                        surface_family = COALESCE(%s, surface_family),
                        url = COALESCE(%s, url),
                        normalized_url = COALESCE(%s, normalized_url),
                        status = COALESCE(%s, status),
                        updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    RETURNING id AS surface_id, company_name, company_role,
                              surface_family, url, status, last_checked_at
                    """,
                    (
                        payload.surface_family,
                        url,
                        normalized_url,
                        status,
                        tenant_id,
                        surface_id,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise LookupError(f"product surface not found: {surface_id}")
        return ProductSurfaceAdminRecord(**dict(row))

    def list_improvements(self, tenant_slug: str, status: str | None = "open") -> list[ImprovementAdminRecord]:
        tenant_id = self._tenant_id(tenant_slug)
        if status is not None:
            _validate_status(status, IMPROVEMENT_STATUSES, field="improvement status")
        return self._improvements(tenant_id, status=status)

    def update_improvement_status(
        self, tenant_slug: str, improvement_id: int, payload: ImprovementStatusUpdate
    ) -> ImprovementAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, IMPROVEMENT_STATUSES, field="improvement status")
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE improvement_queue
                    SET status = %s
                    WHERE tenant_id = %s AND id = %s
                    RETURNING id AS improvement_id, source, problem, proposed_fix,
                              priority, status, created_at
                    """,
                    (status, tenant_id, improvement_id),
                )
                row = cur.fetchone()
        if row is None:
            raise LookupError(f"improvement not found: {improvement_id}")
        return ImprovementAdminRecord(**dict(row))

    def next_sweep_plan(self, tenant_slug: str) -> dict:
        tenant_id = self._tenant_id(tenant_slug)
        improvements = self._improvements(tenant_id, status="approved")
        items = [self._improvement_item_from_admin_record(tenant_id, item) for item in improvements]
        evidence_by_item = self._learning_evidence_ids(tenant_id, items)
        plan = NextSweepPlanner().build(
            tenant_id=tenant_id,
            items=items,
            evidence_by_item=evidence_by_item,
        )
        return plan.model_dump(mode="json")

    def feature_matrix(self, tenant_slug: str) -> list[FeatureMatrixAdminRecord]:
        tenant_id = self._tenant_id(tenant_slug)
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
                    WHERE cfp.tenant_id = %s
                    ORDER BY capability_text, cfp.company_role, cfp.company_name
                    LIMIT 200
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return [FeatureMatrixAdminRecord(**row) for row in rows]

    def evidence_ledger(self, tenant_slug: str) -> EvidenceLedgerState:
        tenant_id = self._tenant_id(tenant_slug)
        return EvidenceLedgerState(
            tenant_slug=tenant_slug,
            tenant_id=tenant_id,
            product_events=self._product_events(tenant_id),
            conversation_themes=self._conversation_themes(tenant_id),
            demand_signals=self._demand_signals(tenant_id),
            patterns=self._pattern_observations(tenant_id),
        )

    def list_recommendations(
        self, tenant_slug: str, status: str | None = "open"
    ) -> list[RecommendationAdminRecord]:
        tenant_id = self._tenant_id(tenant_slug)
        if status is not None:
            _validate_status(status, RECOMMENDATION_STATUSES, field="recommendation status")
        return self._recommendations(tenant_id, status=status)

    def update_recommendation_status(
        self, tenant_slug: str, recommendation_id: int, payload: RecommendationStatusUpdate
    ) -> RecommendationAdminRecord:
        tenant_id = self._tenant_id(tenant_slug)
        status = _validate_status(payload.status, RECOMMENDATION_STATUSES, field="recommendation status")
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE argus_recommendations
                    SET status = %s, updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    RETURNING id AS recommendation_id,
                              pattern_observation_id,
                              owner,
                              action,
                              why_now,
                              urgency,
                              confidence,
                              scorecard,
                              evidence_refs,
                              status,
                              created_at
                    """,
                    (status, tenant_id, recommendation_id),
                )
                row = cur.fetchone()
        if row is None:
            raise LookupError(f"recommendation not found: {recommendation_id}")
        return RecommendationAdminRecord(**dict(row))

    @staticmethod
    def _run_status_from_report_row(row: dict) -> ArgusRunStatus:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        product_market_summary = metadata.get("product_market_summary")
        if not isinstance(product_market_summary, dict):
            product_market_summary = {}
        product_surface_plan_summary = product_market_summary.get("product_surface_plan_summary")
        if not isinstance(product_surface_plan_summary, dict):
            product_surface_plan_summary = {}
        product_surface_execution_summary = product_market_summary.get("product_surface_execution_summary")
        if not isinstance(product_surface_execution_summary, dict):
            product_surface_execution_summary = {}
        runner_summary = product_market_summary.get("runner_summary")
        if not isinstance(runner_summary, dict):
            runner_summary = {}
        ledger_refresh_summary = product_market_summary.get("ledger_refresh_summary")
        if not isinstance(ledger_refresh_summary, dict):
            ledger_refresh_summary = {}
        latest_intelligence_brief = runner_summary.get("intelligence_brief")
        if not isinstance(latest_intelligence_brief, dict):
            latest_intelligence_brief = {}
        scout_paths = product_market_summary.get("scout_paths") or []
        if not isinstance(scout_paths, list):
            scout_paths = []
        errors = metadata.get("run_errors") or product_market_summary.get("errors") or []
        if not isinstance(errors, list):
            errors = [str(errors)]
        looker_discovered_count = int(product_market_summary.get("looker_discovered_count") or 0)
        looker_ready_count = int(product_market_summary.get("looker_ready_count") or 0)
        looker_error_count = int(product_market_summary.get("looker_error_count") or 0)
        looker_normalized_row_count = int(product_market_summary.get("looker_normalized_row_count") or 0)
        demand_signal_count = int(runner_summary.get("demand_signal_count") or 0)
        return ArgusRunStatus(
            tenant_slug=str(row.get("tenant_slug") or ""),
            tenant_id=int(row["tenant_id"]),
            report_id=int(row["report_id"]) if row.get("report_id") is not None else None,
            report_date=row.get("report_date"),
            cadence=row.get("cadence"),
            report_status=row.get("report_status"),
            generated_at=row.get("generated_at"),
            product_market_status=str(product_market_summary.get("status") or "not_recorded"),
            demand_plane_status=PgAdminRepository._product_market_demand_plane_status(
                status=str(product_market_summary.get("status") or "not_recorded"),
                discovered_count=looker_discovered_count,
                ready_count=looker_ready_count,
                error_count=looker_error_count,
                normalized_row_count=looker_normalized_row_count,
                demand_signal_count=demand_signal_count,
            ),
            looker_discovered_count=looker_discovered_count,
            looker_ready_count=looker_ready_count,
            looker_error_count=looker_error_count,
            looker_normalized_row_count=looker_normalized_row_count,
            looker_skipped_row_count=int(product_market_summary.get("looker_skipped_row_count") or 0),
            looker_archived_count=int(product_market_summary.get("looker_archived_count") or 0),
            looker_manifest_path=product_market_summary.get("looker_manifest_path"),
            next_sweep_plan_path=product_market_summary.get("next_sweep_plan_path"),
            learning_apply_plan_path=product_market_summary.get("learning_apply_plan_path"),
            learning_apply_plan_summary=dict(product_market_summary.get("learning_apply_plan_summary") or {}),
            product_surface_plan_summary=product_surface_plan_summary,
            product_surface_execution_summary=product_surface_execution_summary,
            runner_summary=runner_summary,
            ledger_refresh_status=str(product_market_summary.get("ledger_refresh_status") or "not_recorded"),
            ledger_refresh_summary=ledger_refresh_summary,
            latest_intelligence_brief=latest_intelligence_brief,
            scout_paths=[str(path) for path in scout_paths],
            errors=[str(error) for error in errors],
        )

    @staticmethod
    def _product_market_demand_plane_status(
        *,
        status: str,
        discovered_count: int,
        ready_count: int,
        error_count: int,
        normalized_row_count: int,
        demand_signal_count: int,
    ) -> str:
        if status == "not_recorded":
            return "not_recorded"
        if demand_signal_count > 0 or normalized_row_count > 0 or ready_count > 0:
            return "processed" if error_count == 0 else "degraded"
        if error_count > 0:
            return "error"
        if discovered_count > 0:
            return "empty"
        return "missing"

    def _latest_run_intelligence_history(self, tenant_id: int) -> list[ArgusRunIntelligenceRecord]:
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
                    LIMIT 10
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return [self._run_intelligence_record_from_row(row) for row in rows]

    @staticmethod
    def _run_intelligence_record_from_row(row: dict[str, Any]) -> ArgusRunIntelligenceRecord:
        brief = row.get("intelligence_brief")
        if not isinstance(brief, dict):
            brief = {}
        learning_ids = row.get("learning_instruction_improvement_ids") or []
        if not isinstance(learning_ids, list):
            learning_ids = []
        return ArgusRunIntelligenceRecord(
            run_intelligence_id=int(row["id"]),
            verdict=str(row.get("verdict") or brief.get("verdict") or "quiet"),
            top_insight=str(brief.get("top_insight") or "No persisted Argus read was stored."),
            primary_action=brief.get("primary_action"),
            confidence_limits=[str(item) for item in (brief.get("confidence_limits") or [])],
            evidence_urls=[str(item) for item in (brief.get("evidence_urls") or [])],
            created_at=row.get("created_at"),
            product_event_count=int(row.get("product_event_count") or 0),
            conversation_theme_count=int(row.get("conversation_theme_count") or 0),
            demand_signal_count=int(row.get("demand_signal_count") or 0),
            feature_position_count=int(row.get("feature_position_count") or 0),
            pattern_count=int(row.get("pattern_count") or 0),
            recommendation_count=int(row.get("recommendation_count") or 0),
            learning_instruction_count=int(row.get("learning_instruction_count") or 0),
            learning_instruction_improvement_ids=[int(item) for item in learning_ids if str(item).isdigit()],
        )

    @staticmethod
    def _intelligence_brief_from_record(record: ArgusRunIntelligenceRecord | None) -> dict[str, Any]:
        if record is None:
            return {}
        return {
            "verdict": record.verdict,
            "top_insight": record.top_insight,
            "primary_action": record.primary_action,
            "confidence_limits": list(record.confidence_limits),
            "evidence_urls": list(record.evidence_urls),
            "run_intelligence_id": record.run_intelligence_id,
            "created_at": record.created_at,
        }

    def _competitors(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS competitor_id, name AS competitor_name,
                           domain, category, priority, status
                    FROM competitors
                    WHERE tenant_id = %s
                    ORDER BY status <> 'active', priority ASC, name ASC
                    """,
                    (tenant_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def _sources_by_competitor(self, tenant_id: int) -> dict[int, list[SourceAdminRecord]]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH latest_health AS (
                        SELECT DISTINCT ON (source_id)
                               source_id,
                               event_type AS latest_event_type,
                               http_status,
                               detail,
                               created_at AS checked_at
                        FROM source_health_events
                        WHERE tenant_id = %s
                        ORDER BY source_id, created_at DESC
                    )
                    SELECT s.competitor_id,
                           s.id AS source_id,
                           s.source_family,
                           s.url,
                           s.status,
                           h.latest_event_type,
                           h.http_status,
                           h.detail,
                           COALESCE(h.checked_at, s.last_checked_at) AS checked_at
                    FROM sources s
                    LEFT JOIN latest_health h ON h.source_id = s.id
                    WHERE s.tenant_id = %s
                    ORDER BY s.status <> 'active', s.source_family ASC, s.id ASC
                    """,
                    (tenant_id, tenant_id),
                )
                rows = [dict(row) for row in cur.fetchall()]
        grouped: dict[int, list[SourceAdminRecord]] = {}
        for row in rows:
            competitor_id = int(row.pop("competitor_id"))
            grouped.setdefault(competitor_id, []).append(SourceAdminRecord(**row))
        return grouped

    def _product_surfaces_by_competitor(self, tenant_id: int) -> dict[int, list[ProductSurfaceAdminRecord]]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT competitor_id,
                           id AS surface_id,
                           company_name,
                           company_role,
                           surface_family,
                           url,
                           status,
                           last_checked_at
                    FROM product_surfaces
                    WHERE tenant_id = %s
                      AND competitor_id IS NOT NULL
                    ORDER BY status <> 'active', company_name ASC, surface_family ASC, id ASC
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        grouped: dict[int, list[ProductSurfaceAdminRecord]] = {}
        for row in rows:
            competitor_id = int(row.pop("competitor_id"))
            grouped.setdefault(competitor_id, []).append(ProductSurfaceAdminRecord(**row))
        return grouped

    def _improvements(self, tenant_id: int, status: str | None = "open") -> list[ImprovementAdminRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                if status is None:
                    cur.execute(
                        """
                        SELECT id AS improvement_id, source, problem, proposed_fix,
                               priority, status, created_at
                        FROM improvement_queue
                        WHERE tenant_id = %s
                        ORDER BY
                            CASE priority
                                WHEN 'critical' THEN 0
                                WHEN 'high' THEN 1
                                WHEN 'medium' THEN 2
                                WHEN 'low' THEN 3
                                ELSE 4
                            END,
                            created_at DESC,
                            id DESC
                        LIMIT 100
                        """,
                        (tenant_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id AS improvement_id, source, problem, proposed_fix,
                               priority, status, created_at
                        FROM improvement_queue
                        WHERE tenant_id = %s AND status = %s
                        ORDER BY
                            CASE priority
                                WHEN 'critical' THEN 0
                                WHEN 'high' THEN 1
                                WHEN 'medium' THEN 2
                                WHEN 'low' THEN 3
                                ELSE 4
                            END,
                            created_at DESC,
                            id DESC
                        LIMIT 100
                        """,
                        (tenant_id, status),
                    )
                rows = [dict(row) for row in cur.fetchall()]
        return [ImprovementAdminRecord(**row) for row in rows]

    def _recommendations(
        self, tenant_id: int, status: str | None = "open"
    ) -> list[RecommendationAdminRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                if status is None:
                    cur.execute(
                        """
                        SELECT id AS recommendation_id,
                               pattern_observation_id,
                               owner,
                               action,
                               why_now,
                               urgency,
                               confidence,
                               scorecard,
                               evidence_refs,
                               status,
                               created_at
                        FROM argus_recommendations
                        WHERE tenant_id = %s
                        ORDER BY
                            CASE urgency
                                WHEN 'act_now' THEN 0
                                WHEN 'this_week' THEN 1
                                WHEN 'this_month' THEN 2
                                ELSE 3
                            END,
                            CASE status
                                WHEN 'open' THEN 0
                                WHEN 'accepted' THEN 1
                                WHEN 'done' THEN 2
                                WHEN 'dismissed' THEN 3
                                ELSE 4
                            END,
                            created_at DESC,
                            id DESC
                        LIMIT 100
                        """,
                        (tenant_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id AS recommendation_id,
                               pattern_observation_id,
                               owner,
                               action,
                               why_now,
                               urgency,
                               confidence,
                               scorecard,
                               evidence_refs,
                               status,
                               created_at
                        FROM argus_recommendations
                        WHERE tenant_id = %s AND status = %s
                        ORDER BY
                            CASE urgency
                                WHEN 'act_now' THEN 0
                                WHEN 'this_week' THEN 1
                                WHEN 'this_month' THEN 2
                                ELSE 3
                            END,
                            created_at DESC,
                            id DESC
                        LIMIT 100
                        """,
                        (tenant_id, status),
                    )
                rows = [dict(row) for row in cur.fetchall()]
        return [RecommendationAdminRecord(**row) for row in rows]

    def _product_events(self, tenant_id: int) -> list[ProductEventAdminRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS product_event_id,
                           company_name,
                           company_role,
                           capability_text,
                           change_type,
                           summary,
                           observed_at,
                           confidence,
                           evidence_refs
                    FROM product_change_events
                    WHERE tenant_id = %s
                    ORDER BY observed_at DESC, id DESC
                    LIMIT 80
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return [ProductEventAdminRecord(**row) for row in rows]

    def _conversation_themes(self, tenant_id: int) -> list[ConversationThemeAdminRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS conversation_theme_id,
                           company_name,
                           theme,
                           summary,
                           intensity,
                           observed_at,
                           evidence_refs
                    FROM conversation_themes
                    WHERE tenant_id = %s
                    ORDER BY observed_at DESC, id DESC
                    LIMIT 80
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return [ConversationThemeAdminRecord(**row) for row in rows]

    def _demand_signals(self, tenant_id: int) -> list[DemandSignalAdminRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS demand_signal_id,
                           topic,
                           metric,
                           value,
                           change_pct,
                           period_start,
                           period_end,
                           source_label,
                           evidence_refs,
                           metadata
                    FROM demand_signals
                    WHERE tenant_id = %s
                    ORDER BY period_end DESC, id DESC
                    LIMIT 80
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return [DemandSignalAdminRecord(**row) for row in rows]

    def _pattern_observations(self, tenant_id: int) -> list[PatternObservationAdminRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS pattern_observation_id,
                           pattern_type,
                           capability_text,
                           summary,
                           involved_companies,
                           confidence,
                           evidence_refs,
                           created_at
                    FROM pattern_observations
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 80
                    """,
                    (tenant_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return [PatternObservationAdminRecord(**row) for row in rows]

    @staticmethod
    def _improvement_item_from_admin_record(tenant_id: int, record: ImprovementAdminRecord) -> ImprovementItem:
        payload = {
            "id": record.improvement_id,
            "tenant_id": tenant_id,
            "source": record.source,
            "problem": record.problem,
            "proposed_fix": record.proposed_fix,
            "priority": ImprovementPriority(record.priority or ImprovementPriority.MEDIUM.value),
            "status": ImprovementStatus(record.status),
        }
        if record.created_at is not None:
            payload["created_at"] = record.created_at
        return ImprovementItem(**payload)

    def _learning_evidence_ids(
        self, tenant_id: int, items: list[ImprovementItem]
    ) -> dict[int, list[int]]:
        evidence_by_item: dict[int, list[int]] = {}
        for item in items:
            if item.id is None:
                continue
            with tenant_context(self._conn, tenant_id):
                with self._conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT id
                        FROM learning_events
                        WHERE tenant_id = %s
                          AND lesson = %s
                          AND proposed_change IS NOT DISTINCT FROM %s
                        ORDER BY id
                        """,
                        (tenant_id, item.problem, item.proposed_fix),
                    )
                    rows = cur.fetchall()
            evidence_by_item[item.id] = [int(row["id"]) for row in rows]
        return evidence_by_item
