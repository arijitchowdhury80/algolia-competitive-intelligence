"""Local-only FastAPI admin app for CI-OS registry management."""

from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import parse_qs

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from cios.admin.dashboard_refresh import AdminDashboardRefreshRunner
from cios.admin.data_plane_manifest import ArgusDataPlaneManifestStore
from cios.admin.demand_imports import (
    DEMAND_IMPORT_TEMPLATE_CSV,
    DEMAND_IMPORT_TEMPLATE_FIELDS,
    DemandImportLedgerPersister,
    DemandImportStore,
    Ga4DemandExportControl,
    demand_collection_plan_operator_guide,
    demand_collection_plan_template_csv,
)
from cios.admin.demand_intake import DemandIntakeControl, DemandIntakeHistoryStore
from cios.admin.demand_sources import build_demand_source_contract
from cios.admin.evidence_work_queue import build_argus_evidence_work_queue
from cios.admin.feature_comparison import build_feature_comparison_state
from cios.admin.learning_apply import LearningApplyArtifactStore
from cios.admin.operator_handoff import ArgusOperatorHandoffStore
from cios.admin.product_muscle_work_queue import (
    build_product_muscle_work_queue,
    product_muscle_observed_state_text,
)
from cios.admin.product_surface_extraction import ProductSurfaceExtractionControl
from cios.admin.product_surface_candidates import ProductSurfaceCandidatePromotionControl
from cios.admin.product_surface_repair import (
    ProductSurfaceRepairControl,
    ProductSurfaceRepairHistoryStore,
    write_product_surface_repair_admin_summary,
)
from cios.admin.product_surface_execution_trace import ProductSurfaceExecutionTraceStore
from cios.admin.repository import AdminRepository, PgAdminRepository
from cios.admin.types import (
    ArgusDataPlaneManifest,
    ArgusEvidenceWorkItem,
    ArgusOperatorCommand,
    ArgusOperatorHandoff,
    ArgusRunStatus,
    CompetitorCreate,
    CompetitorStatusUpdate,
    CompetitorUpdate,
    DemandImportCreate,
    DemandImportPrepareResult,
    DemandImportStatus,
    EvidenceLedgerState,
    FeatureComparisonState,
    FeatureMatrixAdminRecord,
    Ga4ExportRunResult,
    Ga4ExportStatus,
    ImprovementStatusUpdate,
    LearningApplyExecuteRequest,
    LearningApplyStatus,
    ProductSurfaceCreate,
    ProductSurfaceCandidatePromotionRequest,
    ProductSurfaceStatusUpdate,
    ProductSurfaceUpdate,
    ProductMuscleWorkItem,
    ProductSurfaceExtractionRequest,
    ProductSurfaceRepairRequest,
    RecommendationAdminRecord,
    RecommendationChallengeCreate,
    RecommendationChallengeResponse,
    RecommendationStatusUpdate,
    RegistryState,
    SourceCreate,
    SourceStatusUpdate,
    SourceUpdate,
)
from cios.db.repos.product_market import PgProductMarketRepository
from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.session import get_dsn
from cios.intelligence.demand_quality import DemandQualityConfig
from cios.intelligence.importers import build_payload_from_exports
from cios.intelligence.runner import run_product_market_ledger_refresh
from cios.intelligence.runner import run_product_market_payload
from cios.learn.recommendation_challenge import RecommendationChallengeRecorder

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _demand_quality_from_env(env: Mapping[str, str] | None = None) -> dict[str, float] | None:
    values = env or os.environ
    raw_change = (
        values.get("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR")
        or values.get("CIOS_DEMAND_CHANGE_FLOOR")
        or ""
    ).strip()
    raw_value = (
        values.get("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR")
        or values.get("CIOS_DEMAND_VALUE_FLOOR")
        or ""
    ).strip()
    if not raw_change and not raw_value:
        return None
    defaults = DemandQualityConfig()
    try:
        change_floor = float(raw_change) if raw_change else defaults.change_floor
        value_floor = float(raw_value) if raw_value else defaults.value_floor
    except ValueError as exc:
        raise ValueError("CI-OS demand quality thresholds must be numeric") from exc
    return DemandQualityConfig(change_floor=change_floor, value_floor=value_floor).model_dump()


def _with_demand_quality(kwargs: dict[str, Any]) -> dict[str, Any]:
    demand_quality = _demand_quality_from_env()
    if demand_quality is not None:
        kwargs["demand_quality"] = demand_quality
    return kwargs


async def _form_values(request: Request) -> dict[str, str]:
    body = await request.body()
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _header_param(header: str, name: str) -> str | None:
    pattern = rf'(?:^|;)\s*{re.escape(name)}=(?:"([^"]*)"|([^;]*))'
    match = re.search(pattern, header)
    if not match:
        return None
    return (match.group(1) if match.group(1) is not None else match.group(2) or "").strip()


def _decode_upload_text(value: bytes) -> str:
    try:
        return value.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("demand import file must be UTF-8 text") from exc


def _parse_multipart_form(body: bytes, content_type: str) -> dict[str, str]:
    boundary = _header_param(content_type, "boundary")
    if not boundary:
        raise ValueError("multipart form is missing a boundary")
    delimiter = b"--" + boundary.encode("utf-8")
    values: dict[str, str] = {}
    for raw_part in body.split(delimiter):
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")
        header_bytes, separator, value = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers: dict[str, str] = {}
        for line in header_bytes.decode("latin-1").splitlines():
            key, sep, text = line.partition(":")
            if sep:
                headers[key.strip().lower()] = text.strip()
        disposition = headers.get("content-disposition", "")
        field_name = _header_param(disposition, "name")
        if not field_name:
            continue
        filename = _header_param(disposition, "filename")
        if filename:
            values["filename"] = Path(filename).name
            values["content"] = _decode_upload_text(value)
            continue
        values[field_name] = _decode_upload_text(value)
    return values


async def _demand_upload_form_values(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if content_type.lower().startswith("multipart/form-data"):
        return _parse_multipart_form(await request.body(), content_type)
    return await _form_values(request)


def create_app(
    *,
    repository: Optional[AdminRepository] = None,
    dsn: Optional[str] = None,
    admin_token: Optional[str] = None,
    allowed_hosts: Optional[set[str]] = None,
    recommendation_challenge_recorder=None,
    demand_import_store: DemandImportStore | None = None,
    demand_import_ledger_persister=None,
    demand_intake_control: DemandIntakeControl | None = None,
    demand_intake_history_store: DemandIntakeHistoryStore | None = None,
    ga4_export_control: Ga4DemandExportControl | None = None,
    ledger_refresh_runner=None,
    dashboard_refresh_runner=None,
    learning_apply_store: LearningApplyArtifactStore | None = None,
    operator_handoff_store: ArgusOperatorHandoffStore | None = None,
    data_plane_manifest_store: ArgusDataPlaneManifestStore | None = None,
    product_surface_trace_store: ProductSurfaceExecutionTraceStore | None = None,
    product_surface_extraction_control: ProductSurfaceExtractionControl | None = None,
    product_surface_candidate_promotion_control: ProductSurfaceCandidatePromotionControl | None = None,
    product_surface_repair_control: ProductSurfaceRepairControl | None = None,
    product_surface_repair_refresh_runner=None,
    product_surface_repair_history_store: ProductSurfaceRepairHistoryStore | None = None,
) -> FastAPI:
    app = FastAPI(title="CI-OS Local Admin", docs_url=None, redoc_url=None)
    allowed = allowed_hosts or _LOOPBACK_HOSTS
    configured_token = admin_token if admin_token is not None else os.environ.get("CIOS_ADMIN_TOKEN")
    app.state.repository = repository
    app.state.dsn = dsn
    app.state.allowed_hosts = allowed
    app.state.admin_token = configured_token
    app.state.recommendation_challenge_recorder = recommendation_challenge_recorder
    app.state.demand_import_store = demand_import_store
    app.state.demand_import_ledger_persister = demand_import_ledger_persister
    app.state.demand_intake_control = demand_intake_control
    app.state.demand_intake_history_store = demand_intake_history_store
    app.state.ga4_export_control = ga4_export_control
    app.state.ledger_refresh_runner = ledger_refresh_runner
    app.state.dashboard_refresh_runner = dashboard_refresh_runner
    app.state.learning_apply_store = learning_apply_store
    app.state.operator_handoff_store = operator_handoff_store
    app.state.data_plane_manifest_store = data_plane_manifest_store
    app.state.product_surface_trace_store = product_surface_trace_store
    app.state.product_surface_extraction_control = product_surface_extraction_control
    app.state.product_surface_candidate_promotion_control = product_surface_candidate_promotion_control
    app.state.product_surface_repair_control = product_surface_repair_control
    app.state.product_surface_repair_refresh_runner = product_surface_repair_refresh_runner
    app.state.product_surface_repair_history_store = product_surface_repair_history_store

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.client.host if request.client else ""
        if host not in request.app.state.allowed_hosts:
            return HTMLResponse("CI-OS admin is local-only.", status_code=403)
        return await call_next(request)

    def repo_dep(request: Request) -> AdminRepository:
        if request.app.state.repository is not None:
            return request.app.state.repository
        resolved_dsn = request.app.state.dsn or get_dsn()
        conn = psycopg.connect(resolved_dsn)
        return PgAdminRepository(conn)

    def registry_state(repo: AdminRepository, tenant_slug: str) -> RegistryState:
        return RegistryState.model_validate(repo.registry(tenant_slug))

    def latest_run_status_state(repo: AdminRepository, tenant_slug: str) -> ArgusRunStatus:
        return ArgusRunStatus.model_validate(repo.latest_run_status(tenant_slug))

    def demand_import_store_dep(request: Request) -> DemandImportStore:
        if request.app.state.demand_import_store is not None:
            return request.app.state.demand_import_store
        return DemandImportStore()

    def demand_import_status_state(
        store: DemandImportStore,
        tenant_slug: str,
        *,
        demand_plan: dict[str, Any] | None = None,
    ) -> DemandImportStatus:
        return DemandImportStatus.model_validate(store.status(tenant_slug, demand_plan=demand_plan))

    def demand_intake_history_state(
        store: DemandIntakeHistoryStore,
        tenant_slug: str,
    ) -> dict[str, Any]:
        return store.status(tenant_slug)

    def demand_import_ledger_persister_dep(request: Request):
        if request.app.state.demand_import_ledger_persister is not None:
            return request.app.state.demand_import_ledger_persister

        def _persist(*, tenant_id: int, prepared: DemandImportPrepareResult):
            resolved_dsn = request.app.state.dsn or get_dsn()
            with psycopg.connect(resolved_dsn, autocommit=True) as conn:
                return DemandImportLedgerPersister(
                    repository=PgProductMarketRepository(conn),
                ).persist(tenant_id=tenant_id, prepared=prepared)

        return _persist

    def demand_intake_control_dep(request: Request) -> DemandIntakeControl:
        if request.app.state.demand_intake_control is not None:
            return request.app.state.demand_intake_control
        return DemandIntakeControl()

    def demand_intake_history_store_dep(request: Request) -> DemandIntakeHistoryStore:
        if request.app.state.demand_intake_history_store is not None:
            return request.app.state.demand_intake_history_store
        return DemandIntakeHistoryStore()

    def ga4_export_control_dep(request: Request) -> Ga4DemandExportControl:
        if request.app.state.ga4_export_control is not None:
            return request.app.state.ga4_export_control
        return Ga4DemandExportControl()

    def ga4_export_status_state(control: Ga4DemandExportControl, tenant_slug: str) -> Ga4ExportStatus:
        return Ga4ExportStatus.model_validate(control.status(tenant_slug))

    def recommendation_challenge_recorder_dep(request: Request):
        if request.app.state.recommendation_challenge_recorder is not None:
            return request.app.state.recommendation_challenge_recorder
        resolved_dsn = request.app.state.dsn or get_dsn()
        conn = psycopg.connect(resolved_dsn)
        return RecommendationChallengeRecorder(
            PgLearningEventRepository(conn),
            PgImprovementQueueRepository(conn),
        )

    def ledger_refresh_runner_dep(request: Request):
        if request.app.state.ledger_refresh_runner is not None:
            return request.app.state.ledger_refresh_runner

        def _runner(
            *,
            tenant_slug: str,
            tenant_id: int,
            own_company_name: str,
            days: int,
            limit: int,
            demand_quality: dict[str, float] | None = None,
        ):
            resolved_dsn = request.app.state.dsn or get_dsn()
            with psycopg.connect(resolved_dsn, autocommit=True) as conn:
                kwargs: dict[str, Any] = {
                    "tenant_id": tenant_id,
                    "own_company_name": own_company_name,
                    "repository": PgProductMarketRepository(conn),
                    "days": days,
                    "limit": limit,
                }
                resolved_demand_quality = demand_quality or _demand_quality_from_env()
                if resolved_demand_quality is not None:
                    kwargs["demand_quality"] = resolved_demand_quality
                summary = run_product_market_ledger_refresh(
                    **kwargs,
                )
            return summary.model_dump(mode="json")

        return _runner

    def dashboard_refresh_runner_dep(request: Request):
        if request.app.state.dashboard_refresh_runner is not None:
            return request.app.state.dashboard_refresh_runner
        return AdminDashboardRefreshRunner()

    def learning_apply_store_dep(request: Request) -> LearningApplyArtifactStore:
        if request.app.state.learning_apply_store is not None:
            return request.app.state.learning_apply_store
        return LearningApplyArtifactStore()

    def operator_handoff_store_dep(request: Request) -> ArgusOperatorHandoffStore:
        if request.app.state.operator_handoff_store is not None:
            return request.app.state.operator_handoff_store
        return ArgusOperatorHandoffStore()

    def data_plane_manifest_store_dep(request: Request) -> ArgusDataPlaneManifestStore:
        if request.app.state.data_plane_manifest_store is not None:
            return request.app.state.data_plane_manifest_store
        return ArgusDataPlaneManifestStore()

    def product_surface_trace_store_dep(request: Request) -> ProductSurfaceExecutionTraceStore:
        if request.app.state.product_surface_trace_store is not None:
            return request.app.state.product_surface_trace_store
        return ProductSurfaceExecutionTraceStore()

    def product_surface_repair_control_dep(request: Request) -> ProductSurfaceRepairControl:
        if request.app.state.product_surface_repair_control is not None:
            return request.app.state.product_surface_repair_control
        return ProductSurfaceRepairControl()

    def product_surface_extraction_control_dep(request: Request) -> ProductSurfaceExtractionControl:
        if request.app.state.product_surface_extraction_control is not None:
            return request.app.state.product_surface_extraction_control
        return ProductSurfaceExtractionControl()

    def product_surface_candidate_promotion_control_dep(request: Request) -> ProductSurfaceCandidatePromotionControl:
        if request.app.state.product_surface_candidate_promotion_control is not None:
            return request.app.state.product_surface_candidate_promotion_control
        return ProductSurfaceCandidatePromotionControl()

    def product_surface_repair_refresh_runner_dep(request: Request):
        if request.app.state.product_surface_repair_refresh_runner is not None:
            return request.app.state.product_surface_repair_refresh_runner

        def _runner(
            *,
            tenant_slug: str,
            tenant_id: int,
            own_company_name: str,
            scout_paths: list[str],
            demand_quality: dict[str, float] | None = None,
        ):
            payload = build_payload_from_exports(
                own_company_name=own_company_name,
                tenant_id=tenant_id,
                scout_paths=[Path(path) for path in scout_paths],
            )
            resolved_demand_quality = demand_quality or _demand_quality_from_env()
            if resolved_demand_quality is not None:
                payload = payload.model_copy(
                    update={"demand_quality": DemandQualityConfig.model_validate(resolved_demand_quality)}
                )
            resolved_dsn = request.app.state.dsn or get_dsn()
            with psycopg.connect(resolved_dsn, autocommit=True) as conn:
                summary = run_product_market_payload(
                    payload,
                    repository=PgProductMarketRepository(conn),
                )
            return summary.model_dump(mode="json")

        return _runner

    def product_surface_repair_history_store_dep(request: Request) -> ProductSurfaceRepairHistoryStore:
        if request.app.state.product_surface_repair_history_store is not None:
            return request.app.state.product_surface_repair_history_store
        return ProductSurfaceRepairHistoryStore()

    async def require_write_token(request: Request) -> None:
        token = request.app.state.admin_token
        if not token:
            return
        supplied = request.headers.get("x-cios-admin-token")
        if supplied != token:
            raise HTTPException(status_code=403, detail="admin token required")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(
        tenant: str = "algolia",
        repo: AdminRepository = Depends(repo_dep),
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        demand_intake_history_store: DemandIntakeHistoryStore = Depends(demand_intake_history_store_dep),
        ga4_control: Ga4DemandExportControl = Depends(ga4_export_control_dep),
        learning_store: LearningApplyArtifactStore = Depends(learning_apply_store_dep),
        handoff_store: ArgusOperatorHandoffStore = Depends(operator_handoff_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
        surface_trace_store: ProductSurfaceExecutionTraceStore = Depends(product_surface_trace_store_dep),
        repair_history_store: ProductSurfaceRepairHistoryStore = Depends(product_surface_repair_history_store_dep),
    ) -> HTMLResponse:
        state = registry_state(repo, tenant)
        run_status = latest_run_status_state(repo, tenant)
        evidence_ledger = evidence_ledger_state(repo, tenant)
        demand_plan = demand_collection_plan_from_manifest(
            tenant_slug=tenant,
            manifest_store=manifest_store,
        )
        return HTMLResponse(
            render_admin_page(
                state,
                run_status,
                demand_import_status_state(demand_store, tenant, demand_plan=demand_plan),
                ga4_export_status_state(ga4_control, tenant),
                feature_matrix_state(repo, tenant),
                feature_comparison_state(repo, tenant, demand_plan=demand_plan),
                recommendation_state(repo, tenant),
                evidence_ledger,
                evidence_work_queue_state(tenant, run_status, evidence_ledger),
                product_muscle_work_queue_state(repo, tenant, evidence_ledger, surface_trace_store, demand_plan=demand_plan),
                product_surface_repair_history_state(repair_history_store, tenant),
                demand_intake_history_state(demand_intake_history_store, tenant),
                operator_handoff_status_state(handoff_store, tenant),
                data_plane_manifest_status_state(manifest_store, tenant),
                learning_apply_status_state(repo, learning_store, tenant),
            )
        )

    @app.get("/api/tenants/{tenant_slug}/registry")
    def registry(tenant_slug: str, repo: AdminRepository = Depends(repo_dep)) -> RegistryState:
        return registry_state(repo, tenant_slug)

    @app.post("/api/tenants/{tenant_slug}/competitors", dependencies=[Depends(require_write_token)])
    def create_competitor(
        tenant_slug: str, payload: CompetitorCreate, repo: AdminRepository = Depends(repo_dep)
    ):
        return repo.create_competitor(tenant_slug, payload)

    @app.patch("/api/tenants/{tenant_slug}/competitors/{competitor_id}", dependencies=[Depends(require_write_token)])
    def update_competitor(
        tenant_slug: str,
        competitor_id: int,
        payload: CompetitorUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_competitor(tenant_slug, competitor_id, payload)

    @app.post("/api/tenants/{tenant_slug}/competitors/{competitor_id}/status", dependencies=[Depends(require_write_token)])
    def set_competitor_status(
        tenant_slug: str,
        competitor_id: int,
        payload: CompetitorStatusUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_competitor(tenant_slug, competitor_id, CompetitorUpdate(status=payload.status))

    @app.post("/api/tenants/{tenant_slug}/competitors/{competitor_id}/sources", dependencies=[Depends(require_write_token)])
    def create_source(
        tenant_slug: str,
        competitor_id: int,
        payload: SourceCreate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.create_source(tenant_slug, competitor_id, payload)

    @app.post("/api/tenants/{tenant_slug}/competitors/{competitor_id}/product-surfaces", dependencies=[Depends(require_write_token)])
    def create_product_surface(
        tenant_slug: str,
        competitor_id: int,
        payload: ProductSurfaceCreate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.create_product_surface(tenant_slug, competitor_id, payload)

    @app.patch("/api/tenants/{tenant_slug}/sources/{source_id}", dependencies=[Depends(require_write_token)])
    def update_source(
        tenant_slug: str,
        source_id: int,
        payload: SourceUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_source(tenant_slug, source_id, payload)

    @app.post("/api/tenants/{tenant_slug}/sources/{source_id}/status", dependencies=[Depends(require_write_token)])
    def set_source_status(
        tenant_slug: str,
        source_id: int,
        payload: SourceStatusUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_source(tenant_slug, source_id, SourceUpdate(status=payload.status))

    @app.patch("/api/tenants/{tenant_slug}/product-surfaces/{surface_id}", dependencies=[Depends(require_write_token)])
    def update_product_surface(
        tenant_slug: str,
        surface_id: int,
        payload: ProductSurfaceUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_product_surface(tenant_slug, surface_id, payload)

    @app.post("/api/tenants/{tenant_slug}/product-surfaces/{surface_id}/status", dependencies=[Depends(require_write_token)])
    def set_product_surface_status(
        tenant_slug: str,
        surface_id: int,
        payload: ProductSurfaceStatusUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_product_surface(tenant_slug, surface_id, ProductSurfaceUpdate(status=payload.status))

    @app.post(
        "/api/tenants/{tenant_slug}/argus/recommendations/{recommendation_id}/challenge",
        dependencies=[Depends(require_write_token)],
    )
    def challenge_argus_recommendation(
        tenant_slug: str,
        recommendation_id: int,
        payload: RecommendationChallengeCreate,
        repo: AdminRepository = Depends(repo_dep),
        recorder=Depends(recommendation_challenge_recorder_dep),
    ) -> RecommendationChallengeResponse:
        state = registry_state(repo, tenant_slug)
        try:
            result = recorder.record_challenge(
                tenant_id=state.tenant_id,
                recommendation_id=recommendation_id,
                run_id=payload.run_id,
                challenge=payload.challenge,
                category=payload.category.value,
                scorecard_dimension=payload.scorecard_dimension,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RecommendationChallengeResponse(
            learning_event_id=int(result.event.id or 0),
            improvement_id=int(result.improvement.id) if result.improvement and result.improvement.id else None,
            next_sweep_instruction=result.next_sweep_instruction,
        )

    @app.get("/api/tenants/{tenant_slug}/argus/improvements")
    def list_argus_improvements(
        tenant_slug: str,
        status: str = "open",
        repo: AdminRepository = Depends(repo_dep),
    ):
        resolved_status = None if status == "all" else status
        return repo.list_improvements(tenant_slug, resolved_status)

    @app.get("/api/tenants/{tenant_slug}/argus/next-sweep-plan")
    def argus_next_sweep_plan(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.next_sweep_plan(tenant_slug)

    @app.get("/api/tenants/{tenant_slug}/argus/learning-apply")
    def argus_learning_apply_status(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        learning_store: LearningApplyArtifactStore = Depends(learning_apply_store_dep),
    ) -> LearningApplyStatus:
        return learning_apply_status_state(repo, learning_store, tenant_slug)

    @app.post("/api/tenants/{tenant_slug}/argus/learning-apply/execute", dependencies=[Depends(require_write_token)])
    def execute_argus_learning_apply(
        tenant_slug: str,
        payload: LearningApplyExecuteRequest | None = None,
        repo: AdminRepository = Depends(repo_dep),
        learning_store: LearningApplyArtifactStore = Depends(learning_apply_store_dep),
    ):
        return run_learning_apply_action(
            tenant_slug=tenant_slug,
            repo=repo,
            learning_store=learning_store,
            approved_by=payload.approved_by if payload else None,
        )

    @app.get("/api/tenants/{tenant_slug}/argus/run-status")
    def argus_run_status(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
    ) -> ArgusRunStatus:
        return latest_run_status_state(repo, tenant_slug)

    @app.post("/api/tenants/{tenant_slug}/argus/ledger-refresh", dependencies=[Depends(require_write_token)])
    def refresh_argus_from_ledger(
        tenant_slug: str,
        own_company_name: str | None = None,
        days: int = 30,
        limit: int = 500,
        repo: AdminRepository = Depends(repo_dep),
        runner=Depends(ledger_refresh_runner_dep),
    ):
        try:
            return run_ledger_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                runner=runner,
                own_company_name=own_company_name,
                days=days,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    def feature_matrix_state(repo: AdminRepository, tenant_slug: str) -> list[FeatureMatrixAdminRecord]:
        return [FeatureMatrixAdminRecord.model_validate(item) for item in repo.feature_matrix(tenant_slug)]

    def recommendation_state(
        repo: AdminRepository, tenant_slug: str, status: str | None = "open"
    ) -> list[RecommendationAdminRecord]:
        return [
            RecommendationAdminRecord.model_validate(item)
            for item in repo.list_recommendations(tenant_slug, status=status)
        ]

    def evidence_ledger_state(repo: AdminRepository, tenant_slug: str) -> EvidenceLedgerState:
        return EvidenceLedgerState.model_validate(repo.evidence_ledger(tenant_slug))

    def evidence_work_queue_state(
        tenant_slug: str,
        run_status: ArgusRunStatus,
        evidence_ledger: EvidenceLedgerState,
    ) -> list[ArgusEvidenceWorkItem]:
        return build_argus_evidence_work_queue(
            tenant_slug=tenant_slug,
            run_status=run_status,
            evidence_ledger=evidence_ledger,
        )

    def product_muscle_work_queue_state(
        repo: AdminRepository,
        tenant_slug: str,
        evidence_ledger: EvidenceLedgerState,
        surface_trace_store: ProductSurfaceExecutionTraceStore,
        demand_plan: dict[str, Any] | None = None,
    ) -> list[ProductMuscleWorkItem]:
        return build_product_muscle_work_queue(
            tenant_slug=tenant_slug,
            registry=registry_state(repo, tenant_slug),
            feature_comparison=feature_comparison_state(repo, tenant_slug, demand_plan=demand_plan),
            evidence_ledger=evidence_ledger,
            product_surface_execution_trace=surface_trace_store.status(tenant_slug),
        )

    def product_surface_repair_history_state(
        store: ProductSurfaceRepairHistoryStore,
        tenant_slug: str,
    ) -> dict[str, Any]:
        return store.status(tenant_slug)

    def operator_handoff_status_state(
        store: ArgusOperatorHandoffStore,
        tenant_slug: str,
    ) -> ArgusOperatorHandoff:
        return ArgusOperatorHandoff.model_validate(store.status(tenant_slug))

    def data_plane_manifest_status_state(
        store: ArgusDataPlaneManifestStore,
        tenant_slug: str,
    ) -> ArgusDataPlaneManifest:
        return ArgusDataPlaneManifest.model_validate(store.status(tenant_slug))

    def demand_collection_plan_from_manifest(
        *,
        tenant_slug: str,
        manifest_store: ArgusDataPlaneManifestStore,
    ) -> dict[str, Any] | None:
        manifest = data_plane_manifest_status_state(manifest_store, tenant_slug)
        demand_plane = manifest.planes.get("audience_demand")
        if demand_plane is None:
            return None
        plan = demand_plane.details.get("demand_collection_plan")
        return plan if isinstance(plan, dict) and plan else None

    def learning_apply_status_state(
        repo: AdminRepository,
        learning_store: LearningApplyArtifactStore,
        tenant_slug: str,
    ) -> LearningApplyStatus:
        state = registry_state(repo, tenant_slug)
        return learning_store.status(tenant_slug, tenant_id=state.tenant_id)

    def run_learning_apply_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        learning_store: LearningApplyArtifactStore,
        approved_by: str | None = None,
    ):
        run_status = latest_run_status_state(repo, tenant_slug)
        if not run_status.learning_apply_plan_path:
            raise HTTPException(status_code=400, detail="latest run did not record a learning apply plan")
        try:
            return learning_store.execute_plan(
                tenant_slug,
                tenant_id=run_status.tenant_id,
                plan_path=Path(run_status.learning_apply_plan_path),
                approved_by=_clean_optional_text(approved_by),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def feature_comparison_state(
        repo: AdminRepository,
        tenant_slug: str,
        demand_plan: dict[str, Any] | None = None,
    ) -> FeatureComparisonState:
        return build_feature_comparison_state(
            registry=registry_state(repo, tenant_slug),
            feature_matrix=feature_matrix_state(repo, tenant_slug),
            planned_capabilities=_planned_capabilities_from_demand_plan(demand_plan),
            own_company_name=_default_own_company_name(tenant_slug),
        )

    def run_ledger_refresh_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        runner,
        own_company_name: str | None = None,
        days: int = 30,
        limit: int = 500,
    ):
        state = registry_state(repo, tenant_slug)
        return runner(
            **_with_demand_quality(
                {
                    "tenant_slug": tenant_slug,
                    "tenant_id": state.tenant_id,
                    "own_company_name": own_company_name or _default_own_company_name(tenant_slug),
                    "days": days,
                    "limit": limit,
                }
            )
        )

    def run_product_surface_repair_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        repair_control: ProductSurfaceRepairControl,
        payload: ProductSurfaceRepairRequest,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        return repair_control.run(
            tenant_slug=tenant_slug,
            tenant_id=state.tenant_id,
            company_name=_clean_optional_text(payload.company_name),
            company_id=payload.company_id,
            surface_id=payload.surface_id,
            category=_clean_optional_text(payload.category),
            use_js=payload.use_js,
            repair_timeout_seconds=payload.repair_timeout_seconds,
            command_timeout_seconds=payload.command_timeout_seconds,
            limit=payload.limit,
        )

    def run_product_surface_repair_and_refresh_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        repair_control: ProductSurfaceRepairControl,
        repair_refresh_runner,
        payload: ProductSurfaceRepairRequest,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        repair = run_product_surface_repair_action(
            tenant_slug=tenant_slug,
            repo=repo,
            repair_control=repair_control,
            payload=payload,
        )
        scout_paths = [str(path) for path in repair.get("scout_paths", []) if str(path).strip()]
        if not scout_paths:
            result = {
                **repair,
                "argus_refresh": None,
                "argus_read": None,
            }
            write_product_surface_repair_admin_summary(result)
            return result
        refresh = repair_refresh_runner(
            **_with_demand_quality(
                {
                    "tenant_slug": tenant_slug,
                    "tenant_id": state.tenant_id,
                    "own_company_name": _default_own_company_name(tenant_slug),
                    "scout_paths": scout_paths,
                }
            )
        )
        result = {
            **repair,
            "argus_refresh": refresh,
            "argus_read": _argus_read_from_ledger_refresh(refresh),
        }
        write_product_surface_repair_admin_summary(result)
        return result

    def run_product_surface_extraction_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        extraction_control: ProductSurfaceExtractionControl,
        payload: ProductSurfaceExtractionRequest,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        return extraction_control.run(
            tenant_slug=tenant_slug,
            tenant_id=state.tenant_id,
            company_name=_clean_optional_text(payload.company_name),
            focus_capability=_clean_optional_text(payload.focus_capability),
            company_id=payload.company_id,
            surface_id=payload.surface_id,
            use_js=payload.use_js,
            timeout_seconds=payload.timeout_seconds,
            command_timeout_seconds=payload.command_timeout_seconds,
            max_workers=payload.max_workers,
            limit=payload.limit,
        )

    def run_product_surface_extraction_and_refresh_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        extraction_control: ProductSurfaceExtractionControl,
        refresh_runner,
        payload: ProductSurfaceExtractionRequest,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        extraction = run_product_surface_extraction_action(
            tenant_slug=tenant_slug,
            repo=repo,
            extraction_control=extraction_control,
            payload=payload,
        )
        scout_paths = [str(path) for path in extraction.get("scout_paths", []) if str(path).strip()]
        if not scout_paths:
            return {
                **extraction,
                "argus_refresh": None,
                "argus_read": None,
            }
        refresh = refresh_runner(
            **_with_demand_quality(
                {
                    "tenant_slug": tenant_slug,
                    "tenant_id": state.tenant_id,
                    "own_company_name": _default_own_company_name(tenant_slug),
                    "scout_paths": scout_paths,
                }
            )
        )
        return {
            **extraction,
            "argus_refresh": refresh,
            "argus_read": _argus_read_from_ledger_refresh(refresh),
        }

    def run_product_surface_candidate_promotion_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        promotion_control: ProductSurfaceCandidatePromotionControl,
        payload: ProductSurfaceCandidatePromotionRequest,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        return promotion_control.run(
            tenant_slug=tenant_slug,
            tenant_id=state.tenant_id,
            company_name=_clean_optional_text(payload.company_name),
            company_id=payload.company_id,
            surface_family=_clean_optional_text(payload.surface_family),
            discovery_source=_clean_optional_text(payload.discovery_source) or "product_muscle_gap_plan",
            promoted_by=_clean_optional_text(payload.promoted_by) or "argus",
            limit=payload.limit,
        )

    def run_demand_import_ledger_persist_action(
        *,
        tenant_id: int,
        prepared: DemandImportPrepareResult,
        persister,
    ):
        if hasattr(persister, "persist"):
            result = persister.persist(tenant_id=tenant_id, prepared=prepared)
        else:
            result = persister(tenant_id=tenant_id, prepared=prepared)
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        return result

    def run_demand_intake_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        control: DemandIntakeControl,
        days: int = 30,
        limit: int = 500,
        command_timeout_seconds: float = 300,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        return control.run(
            **_with_demand_quality(
                {
                    "tenant_slug": tenant_slug,
                    "tenant_id": state.tenant_id,
                    "own_company_name": _default_own_company_name(tenant_slug),
                    "days": days,
                    "limit": limit,
                    "command_timeout_seconds": command_timeout_seconds,
                }
            )
        )

    def run_dashboard_refresh_action(*, tenant_slug: str, runner):
        return runner(tenant_slug=tenant_slug)

    def run_ga4_export_and_refresh_action(
        *,
        tenant_slug: str,
        repo: AdminRepository,
        ga4_control: Ga4DemandExportControl,
        demand_store: DemandImportStore,
        demand_persister,
        runner,
        dashboard_runner,
        manifest_store: ArgusDataPlaneManifestStore,
    ) -> dict[str, Any]:
        state = registry_state(repo, tenant_slug)
        demand_plan = demand_collection_plan_from_manifest(
            tenant_slug=tenant_slug,
            manifest_store=manifest_store,
        )
        ga4_export = ga4_control.run(tenant_slug, demand_plan=demand_plan)
        prepared = demand_store.prepare(tenant_slug, demand_plan=demand_plan)
        demand_ledger = run_demand_import_ledger_persist_action(
            tenant_id=state.tenant_id,
            prepared=prepared,
            persister=demand_persister,
        )
        ledger_refresh = runner(
            **_with_demand_quality(
                {
                    "tenant_slug": tenant_slug,
                    "tenant_id": state.tenant_id,
                    "own_company_name": _default_own_company_name(tenant_slug),
                    "days": 30,
                    "limit": 500,
                }
            )
        )
        dashboard_refresh = run_dashboard_refresh_action(
            tenant_slug=tenant_slug,
            runner=dashboard_runner,
        )
        archive = demand_store.archive_prepared(tenant_slug, prepared)
        ga4_payload = ga4_export.model_dump(mode="json") if hasattr(ga4_export, "model_dump") else dict(ga4_export)
        return {
            "status": "ga4_exported_and_argus_refreshed",
            "ga4_export": ga4_payload,
            "demand_import": prepared.model_dump(mode="json"),
            "demand_ledger": demand_ledger,
            "ledger_refresh": ledger_refresh,
            "argus_read": _argus_read_from_ledger_refresh(ledger_refresh),
            "dashboard_refresh": dashboard_refresh,
            "archive": archive,
        }

    @app.get("/api/tenants/{tenant_slug}/argus/feature-matrix")
    def argus_feature_matrix(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
    ) -> list[FeatureMatrixAdminRecord]:
        return feature_matrix_state(repo, tenant_slug)

    @app.get("/api/tenants/{tenant_slug}/argus/feature-comparison")
    def argus_feature_comparison(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> FeatureComparisonState:
        return feature_comparison_state(
            repo,
            tenant_slug,
            demand_plan=demand_collection_plan_from_manifest(
                tenant_slug=tenant_slug,
                manifest_store=manifest_store,
            ),
        )

    @app.get("/api/tenants/{tenant_slug}/argus/demand-imports")
    def argus_demand_import_status(
        tenant_slug: str,
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> DemandImportStatus:
        return demand_import_status_state(
            demand_store,
            tenant_slug,
            demand_plan=demand_collection_plan_from_manifest(
                tenant_slug=tenant_slug,
                manifest_store=manifest_store,
            ),
        )

    @app.get("/api/tenants/{tenant_slug}/argus/demand-intake")
    def argus_demand_intake_history(
        tenant_slug: str,
        history_store: DemandIntakeHistoryStore = Depends(demand_intake_history_store_dep),
    ) -> dict[str, Any]:
        return demand_intake_history_state(history_store, tenant_slug)

    @app.post("/api/tenants/{tenant_slug}/argus/demand-intake", dependencies=[Depends(require_write_token)])
    def run_argus_demand_intake(
        tenant_slug: str,
        days: int = 30,
        limit: int = 500,
        command_timeout_seconds: float = 300,
        repo: AdminRepository = Depends(repo_dep),
        control: DemandIntakeControl = Depends(demand_intake_control_dep),
    ) -> dict[str, Any]:
        try:
            return run_demand_intake_action(
                tenant_slug=tenant_slug,
                repo=repo,
                control=control,
                days=days,
                limit=limit,
                command_timeout_seconds=command_timeout_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/tenants/{tenant_slug}/argus/demand-imports/template")
    def argus_demand_import_template(
        tenant_slug: str,
        planned: bool = False,
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> Response:
        if planned:
            manifest = data_plane_manifest_status_state(manifest_store, tenant_slug)
            demand_plane = manifest.planes.get("audience_demand")
            details = demand_plane.details if demand_plane is not None else {}
            plan = details.get("demand_collection_plan") if isinstance(details, dict) else {}
            return Response(
                content=demand_collection_plan_template_csv(plan if isinstance(plan, dict) else {}),
                media_type="text/csv",
                headers={"content-disposition": "attachment; filename=argus-demand-plan-template.csv"},
            )
        return Response(
            content=DEMAND_IMPORT_TEMPLATE_CSV,
            media_type="text/csv",
            headers={"content-disposition": "attachment; filename=argus-demand-template.csv"},
        )

    @app.get("/api/tenants/{tenant_slug}/argus/demand-imports/work-order")
    def argus_demand_import_work_order(
        tenant_slug: str,
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> dict[str, Any]:
        return demand_collection_plan_operator_guide(
            demand_collection_plan_from_manifest(
                tenant_slug=tenant_slug,
                manifest_store=manifest_store,
            ),
            tenant_slug=tenant_slug,
        )

    @app.get("/api/tenants/{tenant_slug}/argus/ga4-export")
    def argus_ga4_export_status(
        tenant_slug: str,
        ga4_control: Ga4DemandExportControl = Depends(ga4_export_control_dep),
    ) -> Ga4ExportStatus:
        return ga4_export_status_state(ga4_control, tenant_slug)

    @app.post("/api/tenants/{tenant_slug}/argus/ga4-export", dependencies=[Depends(require_write_token)])
    def run_argus_ga4_export(
        tenant_slug: str,
        ga4_control: Ga4DemandExportControl = Depends(ga4_export_control_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> Ga4ExportRunResult:
        try:
            return ga4_control.run(
                tenant_slug,
                demand_plan=demand_collection_plan_from_manifest(
                    tenant_slug=tenant_slug,
                    manifest_store=manifest_store,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/tenants/{tenant_slug}/argus/ga4-export/refresh", dependencies=[Depends(require_write_token)])
    def run_argus_ga4_export_and_refresh(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        ga4_control: Ga4DemandExportControl = Depends(ga4_export_control_dep),
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        demand_persister=Depends(demand_import_ledger_persister_dep),
        runner=Depends(ledger_refresh_runner_dep),
        dashboard_runner=Depends(dashboard_refresh_runner_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            return run_ga4_export_and_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                ga4_control=ga4_control,
                demand_store=demand_store,
                demand_persister=demand_persister,
                runner=runner,
                dashboard_runner=dashboard_runner,
                manifest_store=manifest_store,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/tenants/{tenant_slug}/argus/recommendations")
    def argus_recommendations(
        tenant_slug: str,
        status: str = "open",
        repo: AdminRepository = Depends(repo_dep),
    ) -> list[RecommendationAdminRecord]:
        resolved_status = None if status == "all" else status
        return recommendation_state(repo, tenant_slug, status=resolved_status)

    @app.get("/api/tenants/{tenant_slug}/argus/evidence-ledger")
    def argus_evidence_ledger(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
    ) -> EvidenceLedgerState:
        return evidence_ledger_state(repo, tenant_slug)

    @app.get("/api/tenants/{tenant_slug}/argus/evidence-work-queue")
    def argus_evidence_work_queue(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
    ) -> list[ArgusEvidenceWorkItem]:
        run_status = latest_run_status_state(repo, tenant_slug)
        evidence_ledger = evidence_ledger_state(repo, tenant_slug)
        return evidence_work_queue_state(tenant_slug, run_status, evidence_ledger)

    @app.get("/api/tenants/{tenant_slug}/argus/product-muscle-work-queue")
    def argus_product_muscle_work_queue(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        surface_trace_store: ProductSurfaceExecutionTraceStore = Depends(product_surface_trace_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> list[ProductMuscleWorkItem]:
        evidence_ledger = evidence_ledger_state(repo, tenant_slug)
        return product_muscle_work_queue_state(
            repo,
            tenant_slug,
            evidence_ledger,
            surface_trace_store,
            demand_plan=demand_collection_plan_from_manifest(
                tenant_slug=tenant_slug,
                manifest_store=manifest_store,
            ),
        )

    @app.get("/api/tenants/{tenant_slug}/argus/product-surface-repairs")
    def argus_product_surface_repair_history(
        tenant_slug: str,
        history_store: ProductSurfaceRepairHistoryStore = Depends(product_surface_repair_history_store_dep),
    ) -> dict[str, Any]:
        return product_surface_repair_history_state(history_store, tenant_slug)

    @app.post("/api/tenants/{tenant_slug}/argus/product-surface-repair", dependencies=[Depends(require_write_token)])
    def run_argus_product_surface_repair(
        tenant_slug: str,
        payload: ProductSurfaceRepairRequest,
        repo: AdminRepository = Depends(repo_dep),
        repair_control: ProductSurfaceRepairControl = Depends(product_surface_repair_control_dep),
        repair_refresh_runner=Depends(product_surface_repair_refresh_runner_dep),
    ):
        try:
            return run_product_surface_repair_and_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                repair_control=repair_control,
                repair_refresh_runner=repair_refresh_runner,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/tenants/{tenant_slug}/argus/product-surface-extraction", dependencies=[Depends(require_write_token)])
    def run_argus_product_surface_extraction(
        tenant_slug: str,
        payload: ProductSurfaceExtractionRequest,
        repo: AdminRepository = Depends(repo_dep),
        extraction_control: ProductSurfaceExtractionControl = Depends(product_surface_extraction_control_dep),
        refresh_runner=Depends(product_surface_repair_refresh_runner_dep),
    ):
        try:
            return run_product_surface_extraction_and_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                extraction_control=extraction_control,
                refresh_runner=refresh_runner,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post(
        "/api/tenants/{tenant_slug}/argus/product-surface-candidates/promote",
        dependencies=[Depends(require_write_token)],
    )
    def promote_argus_product_surface_candidates(
        tenant_slug: str,
        payload: ProductSurfaceCandidatePromotionRequest,
        repo: AdminRepository = Depends(repo_dep),
        promotion_control: ProductSurfaceCandidatePromotionControl = Depends(
            product_surface_candidate_promotion_control_dep
        ),
    ):
        try:
            return run_product_surface_candidate_promotion_action(
                tenant_slug=tenant_slug,
                repo=repo,
                promotion_control=promotion_control,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/tenants/{tenant_slug}/argus/operator-handoff")
    def argus_operator_handoff(
        tenant_slug: str,
        handoff_store: ArgusOperatorHandoffStore = Depends(operator_handoff_store_dep),
    ) -> ArgusOperatorHandoff:
        return operator_handoff_status_state(handoff_store, tenant_slug)

    @app.get("/api/tenants/{tenant_slug}/argus/data-plane-manifest")
    def argus_data_plane_manifest(
        tenant_slug: str,
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> ArgusDataPlaneManifest:
        return data_plane_manifest_status_state(manifest_store, tenant_slug)

    @app.post(
        "/api/tenants/{tenant_slug}/argus/recommendations/{recommendation_id}/status",
        dependencies=[Depends(require_write_token)],
    )
    def set_argus_recommendation_status(
        tenant_slug: str,
        recommendation_id: int,
        payload: RecommendationStatusUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ) -> RecommendationAdminRecord:
        return RecommendationAdminRecord.model_validate(
            repo.update_recommendation_status(tenant_slug, recommendation_id, payload)
        )

    @app.post("/api/tenants/{tenant_slug}/argus/demand-imports", dependencies=[Depends(require_write_token)])
    def upload_argus_demand_import(
        tenant_slug: str,
        payload: DemandImportCreate,
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            return demand_store.upload(
                tenant_slug,
                payload,
                demand_plan=demand_collection_plan_from_manifest(
                    tenant_slug=tenant_slug,
                    manifest_store=manifest_store,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/tenants/{tenant_slug}/argus/demand-imports/prepare",
        dependencies=[Depends(require_write_token)],
    )
    def prepare_argus_demand_imports(
        tenant_slug: str,
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ) -> DemandImportPrepareResult:
        return demand_store.prepare(
            tenant_slug,
            demand_plan=demand_collection_plan_from_manifest(
                tenant_slug=tenant_slug,
                manifest_store=manifest_store,
            ),
        )

    @app.post(
        "/api/tenants/{tenant_slug}/argus/demand-imports/refresh",
        dependencies=[Depends(require_write_token)],
    )
    def prepare_demand_imports_and_refresh_argus(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        demand_persister=Depends(demand_import_ledger_persister_dep),
        runner=Depends(ledger_refresh_runner_dep),
        dashboard_runner=Depends(dashboard_refresh_runner_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            state = registry_state(repo, tenant_slug)
            prepared = demand_store.prepare(
                tenant_slug,
                demand_plan=demand_collection_plan_from_manifest(
                    tenant_slug=tenant_slug,
                    manifest_store=manifest_store,
                ),
            )
            demand_ledger = run_demand_import_ledger_persist_action(
                tenant_id=state.tenant_id,
                prepared=prepared,
                persister=demand_persister,
            )
            ledger_refresh = run_ledger_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                runner=runner,
                days=30,
                limit=500,
            )
            dashboard_refresh = run_dashboard_refresh_action(
                tenant_slug=tenant_slug,
                runner=dashboard_runner,
            )
            archive = demand_store.archive_prepared(tenant_slug, prepared)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "status": "demand_prepared_and_argus_refreshed",
            "demand_import": prepared.model_dump(mode="json"),
            "demand_ledger": demand_ledger,
            "ledger_refresh": ledger_refresh,
            "argus_read": _argus_read_from_ledger_refresh(ledger_refresh),
            "dashboard_refresh": dashboard_refresh,
            "archive": archive,
        }

    @app.post(
        "/api/tenants/{tenant_slug}/argus/improvements/{improvement_id}/status",
        dependencies=[Depends(require_write_token)],
    )
    def set_argus_improvement_status(
        tenant_slug: str,
        improvement_id: int,
        payload: ImprovementStatusUpdate,
        repo: AdminRepository = Depends(repo_dep),
    ):
        return repo.update_improvement_status(tenant_slug, improvement_id, payload)

    @app.post("/admin/{tenant_slug}/competitors", dependencies=[Depends(require_write_token)])
    async def create_competitor_form(
        tenant_slug: str, request: Request, repo: AdminRepository = Depends(repo_dep)
    ):
        form = await _form_values(request)
        repo.create_competitor(
            tenant_slug,
            CompetitorCreate(
                name=str(form.get("name") or ""),
                domain=str(form.get("domain") or "") or None,
                category=str(form.get("category") or "") or None,
                priority=int(form.get("priority") or 3),
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/sources", dependencies=[Depends(require_write_token)])
    async def create_source_form(
        tenant_slug: str, request: Request, repo: AdminRepository = Depends(repo_dep)
    ):
        form = await _form_values(request)
        repo.create_source(
            tenant_slug,
            int(form.get("competitor_id") or 0),
            SourceCreate(
                source_family=str(form.get("source_family") or ""),
                url=str(form.get("url") or ""),
                title=str(form.get("title") or "") or None,
                status=str(form.get("status") or "active"),
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/product-surfaces", dependencies=[Depends(require_write_token)])
    async def create_product_surface_form(
        tenant_slug: str, request: Request, repo: AdminRepository = Depends(repo_dep)
    ):
        form = await _form_values(request)
        repo.create_product_surface(
            tenant_slug,
            int(form.get("competitor_id") or 0),
            ProductSurfaceCreate(
                surface_family=str(form.get("surface_family") or ""),
                url=str(form.get("url") or ""),
                status=str(form.get("status") or "active"),
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/competitors/{competitor_id}", dependencies=[Depends(require_write_token)])
    async def update_competitor_form(
        tenant_slug: str,
        competitor_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_competitor(
            tenant_slug,
            competitor_id,
            CompetitorUpdate(
                name=_form_text(form, "name"),
                domain=_form_text(form, "domain"),
                category=_form_text(form, "category"),
                priority=_form_int(form, "priority"),
                status=_form_text(form, "status"),
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/sources/{source_id}", dependencies=[Depends(require_write_token)])
    async def update_source_form(
        tenant_slug: str,
        source_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_source(
            tenant_slug,
            source_id,
            SourceUpdate(
                source_family=_form_text(form, "source_family"),
                url=_form_text(form, "url"),
                title=_form_text(form, "title"),
                status=_form_text(form, "status"),
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/product-surfaces/{surface_id}", dependencies=[Depends(require_write_token)])
    async def update_product_surface_form(
        tenant_slug: str,
        surface_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_product_surface(
            tenant_slug,
            surface_id,
            ProductSurfaceUpdate(
                surface_family=_form_text(form, "surface_family"),
                url=_form_text(form, "url"),
                status=_form_text(form, "status"),
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/competitors/{competitor_id}/status", dependencies=[Depends(require_write_token)])
    async def set_competitor_status_form(
        tenant_slug: str,
        competitor_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_competitor(
            tenant_slug,
            competitor_id,
            CompetitorUpdate(status=str(form.get("status") or "")),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/sources/{source_id}/status", dependencies=[Depends(require_write_token)])
    async def set_source_status_form(
        tenant_slug: str,
        source_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_source(
            tenant_slug,
            source_id,
            SourceUpdate(status=str(form.get("status") or "")),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/product-surfaces/{surface_id}/status", dependencies=[Depends(require_write_token)])
    async def set_product_surface_status_form(
        tenant_slug: str,
        surface_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_product_surface(
            tenant_slug,
            surface_id,
            ProductSurfaceUpdate(status=str(form.get("status") or "")),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/improvements/{improvement_id}/status", dependencies=[Depends(require_write_token)])
    async def set_improvement_status_form(
        tenant_slug: str,
        improvement_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_improvement_status(
            tenant_slug,
            improvement_id,
            ImprovementStatusUpdate(status=str(form.get("status") or "")),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/recommendations/{recommendation_id}/status", dependencies=[Depends(require_write_token)])
    async def set_recommendation_status_form(
        tenant_slug: str,
        recommendation_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
    ):
        form = await _form_values(request)
        repo.update_recommendation_status(
            tenant_slug,
            recommendation_id,
            RecommendationStatusUpdate(status=str(form.get("status") or "")),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/recommendations/{recommendation_id}/challenge", dependencies=[Depends(require_write_token)])
    async def challenge_recommendation_form(
        tenant_slug: str,
        recommendation_id: int,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
        recorder=Depends(recommendation_challenge_recorder_dep),
    ):
        form = await _form_values(request)
        state = registry_state(repo, tenant_slug)
        try:
            recorder.record_challenge(
                tenant_id=state.tenant_id,
                recommendation_id=recommendation_id,
                run_id=str(form.get("run_id") or "") or None,
                challenge=str(form.get("challenge") or ""),
                category=str(form.get("category") or "evidence"),
                scorecard_dimension=str(form.get("scorecard_dimension") or "") or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/demand-imports", dependencies=[Depends(require_write_token)])
    async def upload_demand_import_form(
        tenant_slug: str,
        request: Request,
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            form = await _demand_upload_form_values(request)
            demand_store.upload(
                tenant_slug,
                DemandImportCreate(
                    filename=str(form.get("filename") or ""),
                    content=str(form.get("content") or ""),
                ),
                demand_plan=demand_collection_plan_from_manifest(
                    tenant_slug=tenant_slug,
                    manifest_store=manifest_store,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/demand-imports/prepare", dependencies=[Depends(require_write_token)])
    async def prepare_demand_imports_form(
        tenant_slug: str,
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        demand_store.prepare(
            tenant_slug,
            demand_plan=demand_collection_plan_from_manifest(
                tenant_slug=tenant_slug,
                manifest_store=manifest_store,
            ),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/demand-imports/refresh", dependencies=[Depends(require_write_token)])
    async def prepare_demand_imports_and_refresh_argus_form(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        demand_persister=Depends(demand_import_ledger_persister_dep),
        runner=Depends(ledger_refresh_runner_dep),
        dashboard_runner=Depends(dashboard_refresh_runner_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            state = registry_state(repo, tenant_slug)
            prepared = demand_store.prepare(
                tenant_slug,
                demand_plan=demand_collection_plan_from_manifest(
                    tenant_slug=tenant_slug,
                    manifest_store=manifest_store,
                ),
            )
            run_demand_import_ledger_persist_action(
                tenant_id=state.tenant_id,
                prepared=prepared,
                persister=demand_persister,
            )
            run_ledger_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                runner=runner,
                days=30,
                limit=500,
            )
            run_dashboard_refresh_action(
                tenant_slug=tenant_slug,
                runner=dashboard_runner,
            )
            demand_store.archive_prepared(tenant_slug, prepared)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/demand-intake", dependencies=[Depends(require_write_token)])
    async def run_demand_intake_form(
        tenant_slug: str,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
        control: DemandIntakeControl = Depends(demand_intake_control_dep),
    ):
        form = await _form_values(request)
        try:
            run_demand_intake_action(
                tenant_slug=tenant_slug,
                repo=repo,
                control=control,
                days=int(form.get("days") or 30),
                limit=int(form.get("limit") or 500),
                command_timeout_seconds=float(form.get("command_timeout_seconds") or 300),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}#argus-demand-intake", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/ga4-export", dependencies=[Depends(require_write_token)])
    async def run_ga4_export_form(
        tenant_slug: str,
        ga4_control: Ga4DemandExportControl = Depends(ga4_export_control_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            ga4_control.run(
                tenant_slug,
                demand_plan=demand_collection_plan_from_manifest(
                    tenant_slug=tenant_slug,
                    manifest_store=manifest_store,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/ga4-export/refresh", dependencies=[Depends(require_write_token)])
    async def run_ga4_export_and_refresh_form(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        ga4_control: Ga4DemandExportControl = Depends(ga4_export_control_dep),
        demand_store: DemandImportStore = Depends(demand_import_store_dep),
        demand_persister=Depends(demand_import_ledger_persister_dep),
        runner=Depends(ledger_refresh_runner_dep),
        dashboard_runner=Depends(dashboard_refresh_runner_dep),
        manifest_store: ArgusDataPlaneManifestStore = Depends(data_plane_manifest_store_dep),
    ):
        try:
            run_ga4_export_and_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                ga4_control=ga4_control,
                demand_store=demand_store,
                demand_persister=demand_persister,
                runner=runner,
                dashboard_runner=dashboard_runner,
                manifest_store=manifest_store,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/ledger-refresh", dependencies=[Depends(require_write_token)])
    async def refresh_argus_from_ledger_form(
        tenant_slug: str,
        repo: AdminRepository = Depends(repo_dep),
        runner=Depends(ledger_refresh_runner_dep),
    ):
        try:
            run_ledger_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                runner=runner,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    @app.post("/admin/{tenant_slug}/argus/product-surface-repair", dependencies=[Depends(require_write_token)])
    async def run_product_surface_repair_form(
        tenant_slug: str,
        request: Request,
        company_name: str | None = None,
        company_id: int | None = None,
        surface_id: int | None = None,
        category: str | None = None,
        repo: AdminRepository = Depends(repo_dep),
        repair_control: ProductSurfaceRepairControl = Depends(product_surface_repair_control_dep),
        repair_refresh_runner=Depends(product_surface_repair_refresh_runner_dep),
    ):
        form = await _form_values(request)
        payload = ProductSurfaceRepairRequest(
            company_name=_form_text(form, "company_name") or company_name,
            company_id=_form_int(form, "company_id") or company_id,
            surface_id=_form_int(form, "surface_id") or surface_id,
            category=_form_text(form, "category") or category,
            use_js=(form.get("use_js") or "true").lower() not in {"0", "false", "no"},
            repair_timeout_seconds=float(form.get("repair_timeout_seconds") or 240),
            command_timeout_seconds=float(form.get("command_timeout_seconds") or 300),
            limit=int(form.get("limit") or 1),
        )
        try:
            run_product_surface_repair_and_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                repair_control=repair_control,
                repair_refresh_runner=repair_refresh_runner,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(
            f"/admin?tenant={tenant_slug}#argus-product-muscle-work-queue",
            status_code=303,
        )

    @app.post("/admin/{tenant_slug}/argus/product-surface-extraction", dependencies=[Depends(require_write_token)])
    async def run_product_surface_extraction_form(
        tenant_slug: str,
        request: Request,
        company_name: str | None = None,
        company_id: int | None = None,
        surface_id: int | None = None,
        repo: AdminRepository = Depends(repo_dep),
        extraction_control: ProductSurfaceExtractionControl = Depends(product_surface_extraction_control_dep),
        refresh_runner=Depends(product_surface_repair_refresh_runner_dep),
    ):
        form = await _form_values(request)
        payload = ProductSurfaceExtractionRequest(
            company_name=_form_text(form, "company_name") or company_name,
            focus_capability=_form_text(form, "focus_capability") or _clean_optional_text(request.query_params.get("focus_capability")),
            company_id=_form_int(form, "company_id") or company_id,
            surface_id=_form_int(form, "surface_id") or surface_id,
            use_js=(form.get("use_js") or "true").lower() not in {"0", "false", "no"},
            timeout_seconds=float(form.get("timeout_seconds") or 160),
            command_timeout_seconds=float(form.get("command_timeout_seconds") or 220),
            max_workers=int(form.get("max_workers") or 1),
            limit=int(form.get("limit") or 1),
        )
        try:
            run_product_surface_extraction_and_refresh_action(
                tenant_slug=tenant_slug,
                repo=repo,
                extraction_control=extraction_control,
                refresh_runner=refresh_runner,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(
            f"/admin?tenant={tenant_slug}#argus-product-muscle-work-queue",
            status_code=303,
        )

    @app.post(
        "/admin/{tenant_slug}/argus/product-surface-candidates/promote",
        dependencies=[Depends(require_write_token)],
    )
    async def promote_product_surface_candidates_form(
        tenant_slug: str,
        request: Request,
        company_name: str | None = None,
        company_id: int | None = None,
        surface_family: str | None = None,
        limit: int = 1,
        repo: AdminRepository = Depends(repo_dep),
        promotion_control: ProductSurfaceCandidatePromotionControl = Depends(
            product_surface_candidate_promotion_control_dep
        ),
    ):
        form = await _form_values(request)
        payload = ProductSurfaceCandidatePromotionRequest(
            company_name=_form_text(form, "company_name") or company_name,
            company_id=_form_int(form, "company_id") or company_id,
            surface_family=_form_text(form, "surface_family") or surface_family,
            discovery_source=_form_text(form, "discovery_source") or "product_muscle_gap_plan",
            promoted_by=_form_text(form, "promoted_by") or "argus",
            limit=int(form.get("limit") or limit or 1),
        )
        try:
            run_product_surface_candidate_promotion_action(
                tenant_slug=tenant_slug,
                repo=repo,
                promotion_control=promotion_control,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(
            f"/admin?tenant={tenant_slug}#argus-product-muscle-work-queue",
            status_code=303,
        )

    @app.post("/admin/{tenant_slug}/argus/learning-apply/execute", dependencies=[Depends(require_write_token)])
    async def execute_learning_apply_form(
        tenant_slug: str,
        request: Request,
        repo: AdminRepository = Depends(repo_dep),
        learning_store: LearningApplyArtifactStore = Depends(learning_apply_store_dep),
    ):
        form = await _form_values(request)
        run_learning_apply_action(
            tenant_slug=tenant_slug,
            repo=repo,
            learning_store=learning_store,
            approved_by=form.get("approved_by"),
        )
        return RedirectResponse(f"/admin?tenant={tenant_slug}", status_code=303)

    return app


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _form_text(form: dict[str, str], key: str) -> str | None:
    return _clean_optional_text(form.get(key))


def _form_int(form: dict[str, str], key: str) -> int | None:
    value = _clean_optional_text(form.get(key))
    return int(value) if value is not None else None


def _argus_read_from_ledger_refresh(ledger_refresh: Any) -> dict[str, Any] | None:
    if hasattr(ledger_refresh, "model_dump"):
        data = ledger_refresh.model_dump(mode="json")
    elif isinstance(ledger_refresh, dict):
        data = ledger_refresh
    else:
        return None
    brief = data.get("intelligence_brief") if isinstance(data.get("intelligence_brief"), dict) else {}
    demand_read = brief.get("demand_read") if isinstance(brief.get("demand_read"), dict) else {}
    conversion = brief.get("conversion_diagnostics")
    if not isinstance(conversion, dict):
        conversion = data.get("conversion_diagnostics") if isinstance(data.get("conversion_diagnostics"), dict) else {}
    return {
        "verdict": data.get("verdict"),
        "top_insight": brief.get("top_insight"),
        "primary_action": brief.get("primary_action"),
        "demand_summary": demand_read.get("summary"),
        "conversion_summary": conversion.get("summary"),
        "counts": {
            "product_events": int(data.get("product_event_count") or 0),
            "conversation_themes": int(data.get("conversation_theme_count") or 0),
            "demand_signals": int(data.get("demand_signal_count") or 0),
            "patterns": int(data.get("pattern_count") or 0),
            "recommendations": int(data.get("recommendation_count") or 0),
        },
    }


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _status_class(status: str | None) -> str:
    if status in {"active", "ok", "recovered", "accepted", "done"}:
        return "ok"
    if status in {
        "paused",
        "blocked",
        "blocked_on_evidence",
        "blocked_missing_demand_source",
        "limited_by_evidence",
        "missing",
        "needs_credentials",
        "not_recorded",
        "not_actionable",
        "artifact_error",
    }:
        return "warn"
    if status in {"retired", "fetch_error", "http_error", "timeout", "empty", "dismissed"}:
        return "bad"
    return "neutral"


def _default_own_company_name(tenant_slug: str) -> str:
    configured = os.environ.get("CIOS_OWN_COMPANY_NAME")
    if configured and configured.strip():
        return configured.strip()
    return tenant_slug.replace("-", " ").title()


def _planned_capabilities_from_demand_plan(demand_plan: dict[str, Any] | None) -> list[str]:
    if not isinstance(demand_plan, dict):
        return []
    topics = demand_plan.get("topics")
    if not isinstance(topics, list):
        return []
    capabilities: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        if not isinstance(topic, Mapping):
            continue
        label = _first_non_empty_text(
            topic.get("topic"),
            topic.get("capability_text"),
            topic.get("capability"),
            topic.get("capability_key"),
        )
        if not label:
            continue
        key = " ".join(label.lower().split())
        if key in seen:
            continue
        seen.add(key)
        capabilities.append(label)
    return capabilities


def _first_non_empty_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return " ".join(text.split())
    return None


def _select_options(options: list[str], selected: str | None) -> str:
    return "".join(
        f"<option value=\"{_esc(option)}\"{' selected' if option == selected else ''}>{_esc(option)}</option>"
        for option in options
    )


def _source_rows(state: RegistryState) -> str:
    rows: list[str] = []
    for competitor in state.competitors:
        for source in competitor.sources:
            event = source.latest_event_type or "not checked"
            rows.append(
                "<tr>"
                f"<td>{_esc(competitor.competitor_name)}</td>"
                f"<td>{_esc(source.source_family)}</td>"
                f"<td><a href=\"{_esc(source.url)}\">{_esc(source.url)}</a></td>"
                f"<td><span class=\"pill {_status_class(source.status)}\">{_esc(source.status)}</span></td>"
                f"<td><span class=\"pill {_status_class(source.latest_event_type)}\">{_esc(event)}</span></td>"
                f"<td>{_esc(source.http_status or '')}</td>"
                f"<td>{_esc(source.detail or '')}</td>"
                f"<td class=\"action-cell\">"
                f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/sources/{source.source_id}/status\">"
                f"<input type=\"hidden\" name=\"status\" value=\"blocked\" />"
                f"<button type=\"submit\">Pause</button>"
                f"</form>"
                f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/sources/{source.source_id}/status\">"
                f"<input type=\"hidden\" name=\"status\" value=\"retired\" />"
                f"<button type=\"submit\">Retire</button>"
                f"</form>"
                f"<details>"
                f"<summary>Edit</summary>"
                f"<form class=\"edit-form\" aria-label=\"Edit source {source.source_id}\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/sources/{source.source_id}\">"
                f"<label>Family<input name=\"source_family\" value=\"{_esc(source.source_family)}\" required /></label>"
                f"<label>URL<input name=\"url\" type=\"url\" value=\"{_esc(source.url)}\" required /></label>"
                f"<label>Title<input name=\"title\" value=\"\" /></label>"
                f"<label>Status<select name=\"status\">{_select_options(['active', 'candidate', 'blocked', 'needs_credentials', 'retired'], source.status)}</select></label>"
                f"<button type=\"submit\">Save source</button>"
                f"</form>"
                f"</details>"
                f"</td>"
                "</tr>"
            )
    if not rows:
        return '<tr><td colspan="8">No source URLs are configured for this tenant.</td></tr>'
    return "".join(rows)


def _product_surface_rows(state: RegistryState) -> str:
    rows: list[str] = []
    for competitor in state.competitors:
        for surface in competitor.product_surfaces:
            rows.append(
                "<tr>"
                f"<td>{_esc(competitor.competitor_name)}</td>"
                f"<td>{_esc(surface.surface_family)}</td>"
                f"<td><a href=\"{_esc(surface.url)}\">{_esc(surface.url)}</a></td>"
                f"<td><span class=\"pill {_status_class(surface.status)}\">{_esc(surface.status)}</span></td>"
                f"<td>{_esc(surface.last_checked_at or '')}</td>"
                f"<td class=\"action-cell\">"
                f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/product-surfaces/{surface.surface_id}/status\">"
                f"<input type=\"hidden\" name=\"status\" value=\"paused\" />"
                f"<button type=\"submit\">Pause</button>"
                f"</form>"
                f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/product-surfaces/{surface.surface_id}/status\">"
                f"<input type=\"hidden\" name=\"status\" value=\"retired\" />"
                f"<button type=\"submit\">Retire</button>"
                f"</form>"
                f"<details>"
                f"<summary>Edit</summary>"
                f"<form class=\"edit-form\" aria-label=\"Edit product surface {surface.surface_id}\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/product-surfaces/{surface.surface_id}\">"
                f"<label>Family<select name=\"surface_family\">{_select_options(['docs', 'changelog', 'release_notes', 'product_page', 'pricing', 'api_docs', 'integration', 'other'], surface.surface_family)}</select></label>"
                f"<label>URL<input name=\"url\" type=\"url\" value=\"{_esc(surface.url)}\" required /></label>"
                f"<label>Status<select name=\"status\">{_select_options(['active', 'candidate', 'paused', 'retired'], surface.status)}</select></label>"
                f"<button type=\"submit\">Save product surface</button>"
                f"</form>"
                f"</details>"
                f"</td>"
                "</tr>"
            )
    if not rows:
        return '<tr><td colspan="6">No product surfaces are configured for this tenant.</td></tr>'
    return "".join(rows)


def _competitor_rows(state: RegistryState) -> str:
    rows: list[str] = []
    for competitor in state.competitors:
        failed = sum(1 for s in competitor.sources if (s.latest_event_type or "") in {"fetch_error", "http_error", "timeout", "empty"})
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(competitor.competitor_name)}</strong><span>{_esc(competitor.domain or 'domain not set')}</span></td>"
            f"<td>{_esc(competitor.category or '')}</td>"
            f"<td>{_esc(competitor.priority)}</td>"
            f"<td><span class=\"pill {_status_class(competitor.status)}\">{_esc(competitor.status)}</span></td>"
            f"<td><meter min=\"0\" max=\"{max(len(competitor.sources), 1)}\" value=\"{len(competitor.sources) - failed}\"></meter>"
            f"<span>{len(competitor.sources)} sources / {failed} failed</span></td>"
            f"<td class=\"action-cell\">"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/competitors/{competitor.competitor_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"paused\" />"
            f"<button type=\"submit\">Pause</button>"
            f"</form>"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/competitors/{competitor.competitor_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"retired\" />"
            f"<button type=\"submit\">Retire</button>"
            f"</form>"
            f"<details>"
            f"<summary>Edit</summary>"
            f"<form class=\"edit-form\" aria-label=\"Edit competitor {_esc(competitor.competitor_name)}\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/competitors/{competitor.competitor_id}\">"
            f"<label>Name<input name=\"name\" value=\"{_esc(competitor.competitor_name)}\" required /></label>"
            f"<label>Domain<input name=\"domain\" value=\"{_esc(competitor.domain or '')}\" /></label>"
            f"<label>Category<input name=\"category\" value=\"{_esc(competitor.category or '')}\" /></label>"
            f"<label>Priority<input name=\"priority\" type=\"number\" min=\"1\" max=\"10\" value=\"{_esc(competitor.priority)}\" /></label>"
            f"<label>Status<select name=\"status\">{_select_options(['active', 'candidate', 'paused', 'retired'], competitor.status)}</select></label>"
            f"<button type=\"submit\">Save competitor</button>"
            f"</form>"
            f"</details>"
            f"</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6">No competitors configured yet.</td></tr>'
    return "".join(rows)


def _competitor_options(state: RegistryState) -> str:
    return "".join(
        f"<option value=\"{competitor.competitor_id}\">{_esc(competitor.competitor_name)}</option>"
        for competitor in state.competitors
    )


def _improvement_rows(state: RegistryState) -> str:
    rows: list[str] = []
    for item in state.improvements:
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(item.source or 'argus')}</strong><span>{_esc(item.created_at or '')}</span></td>"
            f"<td>{_esc(item.problem)}</td>"
            f"<td>{_esc(item.proposed_fix or '')}</td>"
            f"<td><span class=\"pill {_status_class(item.priority)}\">{_esc(item.priority or '')}</span></td>"
            f"<td><span class=\"pill {_status_class(item.status)}\">{_esc(item.status)}</span></td>"
            f"<td class=\"action-cell\">"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/argus/improvements/{item.improvement_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"approved\" />"
            f"<button type=\"submit\">Approve</button>"
            f"</form>"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/argus/improvements/{item.improvement_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"rejected\" />"
            f"<button type=\"submit\">Reject</button>"
            f"</form>"
            f"</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6">No open Argus improvement items.</td></tr>'
    return "".join(rows)


def _scorecard_total(scorecard: dict) -> str:
    total = scorecard.get("total_score") if isinstance(scorecard, dict) else None
    return "" if total is None else str(total)


def _scorecard_summary(scorecard: dict) -> str:
    if not isinstance(scorecard, dict):
        return ""
    return str(scorecard.get("summary") or scorecard.get("verdict") or "")


def _recommendation_rows(state: RegistryState, recommendations: list[RecommendationAdminRecord]) -> str:
    rows: list[str] = []
    for item in recommendations:
        urls = _evidence_urls(item.evidence_refs)
        proof = urls[0] if urls else ""
        proof_text = f'<a href="{_esc(proof)}">{_esc(proof)}</a>' if proof else "No proof link on file."
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(item.owner)} · {_esc(item.urgency)}</strong>"
            f"<span>{_esc(item.created_at or '')}</span></td>"
            f"<td><strong>{_esc(item.action)}</strong><span>{_esc(item.why_now)}</span></td>"
            f"<td>{_esc(_scorecard_total(item.scorecard))}<span>{_esc(_scorecard_summary(item.scorecard))}</span></td>"
            f"<td>{proof_text}<span>{_esc(len(urls))} proof links</span></td>"
            f"<td><span class=\"pill {_status_class(item.status)}\">{_esc(item.status)}</span></td>"
            f"<td class=\"action-cell\">"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/argus/recommendations/{item.recommendation_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"accepted\" />"
            f"<button type=\"submit\">Accept</button>"
            f"</form>"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/argus/recommendations/{item.recommendation_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"done\" />"
            f"<button type=\"submit\">Done</button>"
            f"</form>"
            f"<form class=\"inline\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/argus/recommendations/{item.recommendation_id}/status\">"
            f"<input type=\"hidden\" name=\"status\" value=\"dismissed\" />"
            f"<button type=\"submit\">Dismiss</button>"
            f"</form>"
            f"<form class=\"challenge-form\" method=\"post\" action=\"/admin/{_esc(state.tenant_slug)}/argus/recommendations/{item.recommendation_id}/challenge\">"
            f"<input type=\"hidden\" name=\"category\" value=\"evidence\" />"
            f"<input name=\"challenge\" aria-label=\"Challenge recommendation {_esc(item.recommendation_id)}\" placeholder=\"Challenge evidence or priority\" />"
            f"<button type=\"submit\">Challenge</button>"
            f"</form>"
            f"</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="6">No open Argus recommendations. Check run reads, feature matrix, and learning gates before treating this as a quiet day.</td></tr>'
    return "".join(rows)


def _recommendation_section(state: RegistryState, recommendations: list[RecommendationAdminRecord]) -> str:
    open_count = sum(1 for item in recommendations if item.status == "open")
    act_now = sum(1 for item in recommendations if item.urgency == "act_now")
    owners = len({item.owner for item in recommendations})
    best_score = max((int(float(_scorecard_total(item.scorecard) or 0)) for item in recommendations), default=0)
    return f"""
    <section>
      <h2>Argus action workbench</h2>
      <div class="muted">Current owner-specific recommendations promoted from the evidence ledger. Accept, dismiss, mark done, or challenge a read so Hermes can turn the feedback into next-sweep learning.</div>
      <div class="stats" aria-label="Argus action workbench summary">
        <div class="stat"><strong>{_esc(open_count)}</strong><span class="muted">open actions</span></div>
        <div class="stat"><strong>{_esc(act_now)}</strong><span class="muted">act now</span></div>
        <div class="stat"><strong>{_esc(owners)}</strong><span class="muted">owners</span></div>
        <div class="stat"><strong>{_esc(best_score)}</strong><span class="muted">top score</span></div>
      </div>
      <table aria-label="Argus action recommendations">
        <thead><tr><th>Owner</th><th>Recommended action</th><th>Score</th><th>Evidence</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{_recommendation_rows(state, recommendations)}</tbody>
      </table>
    </section>
"""


def _first_proof(evidence_refs: list[dict]) -> str:
    urls = _evidence_urls(evidence_refs)
    if not urls:
        return "No proof link on file."
    return f'<a href="{_esc(urls[0])}">{_esc(urls[0])}</a><span>{_esc(len(urls))} proof links</span>'


def _evidence_plane_rows(ledger: EvidenceLedgerState, plane: str) -> str:
    rows: list[str] = []
    if plane == "product":
        for item in ledger.product_events[:8]:
            rows.append(
                "<tr>"
                f"<td><strong>{_esc(item.company_name)}</strong><span>{_esc(item.company_role)} · {_esc(item.change_type)}</span></td>"
                f"<td><strong>{_esc(item.capability_text)}</strong><span>{_esc(item.summary)}</span></td>"
                f"<td>{_esc(item.confidence if item.confidence is not None else '')}</td>"
                f"<td>{_first_proof(item.evidence_refs)}</td>"
                f"<td>{_esc(item.observed_at or '')}</td>"
                "</tr>"
            )
    elif plane == "conversation":
        for item in ledger.conversation_themes[:8]:
            rows.append(
                "<tr>"
                f"<td><strong>{_esc(item.company_name or 'market')}</strong><span>conversation</span></td>"
                f"<td><strong>{_esc(item.theme)}</strong><span>{_esc(item.summary)}</span></td>"
                f"<td>{_esc(item.intensity if item.intensity is not None else '')}</td>"
                f"<td>{_first_proof(item.evidence_refs)}</td>"
                f"<td>{_esc(item.observed_at or '')}</td>"
                "</tr>"
            )
    elif plane == "demand":
        for item in ledger.demand_signals[:8]:
            rows.append(
                "<tr>"
                f"<td><strong>{_esc(item.source_label)}</strong><span>{_esc(item.metric)}</span></td>"
                f"<td><strong>{_esc(item.topic)}</strong><span>value {_esc(item.value)} · change {_esc(item.change_pct if item.change_pct is not None else '')}</span></td>"
                f"<td>{_esc(item.change_pct if item.change_pct is not None else '')}</td>"
                f"<td>{_first_proof(item.evidence_refs)}</td>"
                f"<td>{_esc(item.period_end)}</td>"
                "</tr>"
            )
    elif plane == "pattern":
        for item in ledger.patterns[:8]:
            companies = ", ".join(item.involved_companies)
            rows.append(
                "<tr>"
                f"<td><strong>{_esc(item.pattern_type)}</strong><span>{_esc(companies)}</span></td>"
                f"<td><strong>{_esc(item.capability_text)}</strong><span>{_esc(item.summary)}</span></td>"
                f"<td>{_esc(item.confidence if item.confidence is not None else '')}</td>"
                f"<td>{_first_proof(item.evidence_refs)}</td>"
                f"<td>{_esc(item.created_at or '')}</td>"
                "</tr>"
            )
    if not rows:
        labels = {
            "product": "No product proof captured. Scout/product-surface extraction has not produced rows for this plane.",
            "conversation": "No market conversation captured. Web/news/GTM scans have not produced rows for this plane.",
            "demand": "No audience demand captured. Queue GA / Looker exports or connect analytics before demand-backed action.",
            "pattern": "No Argus patterns captured. The brain has not found enough cross-plane evidence to synthesize a pattern.",
        }
        return f'<tr><td colspan="5">{_esc(labels.get(plane, "No evidence rows captured."))}</td></tr>'
    return "".join(rows)


def _evidence_plane_table(title: str, description: str, ledger: EvidenceLedgerState, plane: str) -> str:
    return f"""
      <div>
        <h3>{_esc(title)}</h3>
        <p class="muted">{_esc(description)}</p>
        <table aria-label="{_esc(title)} evidence plane">
          <thead><tr><th>Source</th><th>Signal</th><th>Weight</th><th>Evidence</th><th>Observed</th></tr></thead>
          <tbody>{_evidence_plane_rows(ledger, plane)}</tbody>
        </table>
      </div>
"""


def _evidence_ledger_section(ledger: EvidenceLedgerState) -> str:
    return f"""
    <section>
      <h2>Argus evidence ledger</h2>
      <div class="muted">The four planes Argus uses before it is allowed to recommend action: product proof, market conversation, audience demand, and synthesized pattern memory.</div>
      <div class="stats" aria-label="Argus evidence ledger summary">
        <div class="stat"><strong>{_esc(len(ledger.product_events))}</strong><span class="muted">product proof</span></div>
        <div class="stat"><strong>{_esc(len(ledger.conversation_themes))}</strong><span class="muted">conversation</span></div>
        <div class="stat"><strong>{_esc(len(ledger.demand_signals))}</strong><span class="muted">demand</span></div>
        <div class="stat"><strong>{_esc(len(ledger.patterns))}</strong><span class="muted">patterns</span></div>
      </div>
      <div class="ledger-grid">
        {_evidence_plane_table("Product proof", "What Scout/product surfaces say companies actually shipped or documented.", ledger, "product")}
        {_evidence_plane_table("Market conversation", "What competitors or the market are saying publicly.", ledger, "conversation")}
        {_evidence_plane_table("Audience demand", "What Algolia-side analytics say people are engaging with.", ledger, "demand")}
        {_evidence_plane_table("Pattern memory", "Argus's cross-plane synthesis before recommendations are promoted.", ledger, "pattern")}
      </div>
    </section>
"""


def _work_item_action(label: str | None, href: str | None, method: str | None) -> str:
    if not label or not href:
        return ""
    if (method or "get").lower() == "post":
        return (
            f"<form class=\"inline\" method=\"post\" action=\"{_esc(href)}\">"
            f"<button type=\"submit\">{_esc(label)}</button>"
            "</form>"
        )
    return f"<a href=\"{_esc(href)}\">{_esc(label)}</a>"


def _work_item_observed_state(item: ArgusEvidenceWorkItem) -> str:
    if not item.observed_state:
        return "No observed state recorded."
    parts = []
    for key, value in item.observed_state.items():
        if value is None or value == "":
            continue
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return " · ".join(parts) if parts else "No observed state recorded."


def _evidence_work_queue_rows(items: list[ArgusEvidenceWorkItem]) -> str:
    if not items:
        return (
            '<tr><td colspan="5">'
            "No open Argus evidence work items. If the read still feels weak, challenge the recommendation "
            "or refresh Argus from the evidence ledger."
            "</td></tr>"
        )
    rows: list[str] = []
    for item in items[:12]:
        schema_parts = []
        if item.accepted_input_formats:
            schema_parts.append("Formats: " + ", ".join(item.accepted_input_formats))
        if item.required_fields:
            schema_parts.append("Fields: " + ", ".join(item.required_fields[:7]))
        schema_line = " · ".join(schema_parts)
        actions = " ".join(
            part
            for part in [
                _work_item_action(
                    item.primary_action_label,
                    item.primary_action_href,
                    item.primary_action_method,
                ),
                _work_item_action(
                    item.secondary_action_label,
                    item.secondary_action_href,
                    item.secondary_action_method,
                ),
            ]
            if part
        )
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(item.title)}</strong><span>{_esc(item.evidence_plane)} · {_esc(item.severity)}</span></td>"
            f"<td>{_esc(item.why_needed)}<span>Blocks: {_esc(', '.join(item.blocks))}</span></td>"
            f"<td>{_esc(item.next_step)}<span>{_esc(schema_line)}</span></td>"
            f"<td>{_esc(_work_item_observed_state(item))}</td>"
            f"<td class=\"action-cell\">{actions}</td>"
            "</tr>"
        )
    return "".join(rows)


def _evidence_work_queue_section(items: list[ArgusEvidenceWorkItem]) -> str:
    blocking_count = sum(1 for item in items if item.severity == "blocks_action")
    limited_count = sum(1 for item in items if item.severity != "blocks_action")
    return f"""
    <section id="argus-evidence-work-queue">
      <h2>Argus evidence work queue</h2>
      <div class="muted">Open evidence gaps that stop Argus from turning a read into a trusted recommendation. This is the operator queue for repairing the brain and muscle, not another dashboard metric.</div>
      <div class="stats" aria-label="Argus evidence work queue summary">
        <div class="stat"><strong>{_esc(len(items))}</strong><span class="muted">open evidence tasks</span></div>
        <div class="stat"><strong>{_esc(blocking_count)}</strong><span class="muted">blocking action</span></div>
        <div class="stat"><strong>{_esc(limited_count)}</strong><span class="muted">limiting priority</span></div>
      </div>
      <table aria-label="Argus evidence work queue">
        <thead><tr><th>Evidence plane</th><th>Why Argus needs it</th><th>Next step</th><th>Observed state</th><th>Actions</th></tr></thead>
        <tbody>{_evidence_work_queue_rows(items)}</tbody>
      </table>
    </section>
"""


def _product_muscle_work_queue_rows(items: list[ProductMuscleWorkItem]) -> str:
    if not items:
        return (
            '<tr><td colspan="5">'
            "No open product-muscle coverage tasks. Active competitors have product surfaces and captured "
            "feature evidence for the current matrix."
            "</td></tr>"
        )
    rows: list[str] = []
    for item in items[:16]:
        actions = " ".join(
            part
            for part in [
                _work_item_action(
                    item.primary_action_label,
                    item.primary_action_href,
                    item.primary_action_method,
                ),
                _work_item_action(
                    item.secondary_action_label,
                    item.secondary_action_href,
                    item.secondary_action_method,
                ),
            ]
            if part
        )
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(item.company_name)}</strong><span>{_esc(item.company_role)} · {_esc(item.severity)}</span></td>"
            f"<td><strong>{_esc(item.title)}</strong><span>{_esc(item.why_needed)}</span></td>"
            f"<td>{_esc(item.next_step)}<span>Blocks: {_esc(', '.join(item.blocks))}</span></td>"
            f"<td>{_esc(product_muscle_observed_state_text(item))}</td>"
            f"<td class=\"action-cell\">{actions}</td>"
            "</tr>"
        )
    return "".join(rows)


def _product_muscle_work_queue_section(items: list[ProductMuscleWorkItem]) -> str:
    blocking_count = sum(1 for item in items if item.severity == "blocks_feature_matrix")
    limiting_count = sum(1 for item in items if item.severity != "blocks_feature_matrix")
    return f"""
    <section id="argus-product-muscle-work-queue">
      <h2>Argus product muscle work queue</h2>
      <div class="muted">Product-reality coverage gaps that make the feature matrix, product gap scoring, and product-backed recommendations untrustworthy. This is where Hermes knows what Scout/product-surface work must happen next.</div>
      <div class="stats" aria-label="Argus product muscle work queue summary">
        <div class="stat"><strong>{_esc(len(items))}</strong><span class="muted">open muscle tasks</span></div>
        <div class="stat"><strong>{_esc(blocking_count)}</strong><span class="muted">blocking matrix</span></div>
        <div class="stat"><strong>{_esc(limiting_count)}</strong><span class="muted">limiting confidence</span></div>
      </div>
      <table aria-label="Argus product muscle work queue">
        <thead><tr><th>Company</th><th>Why Argus needs it</th><th>Next step</th><th>Observed state</th><th>Actions</th></tr></thead>
        <tbody>{_product_muscle_work_queue_rows(items)}</tbody>
      </table>
    </section>
"""


def _repair_history_attempts(history: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = [item for item in history.get("attempts", []) if isinstance(item, dict)]
    latest = history.get("latest") if isinstance(history.get("latest"), dict) else None
    if latest and latest not in attempts:
        attempts = [latest, *attempts]
    return attempts[:5]


def _product_surface_repair_history_rows(history: dict[str, Any]) -> str:
    rows: list[str] = []
    for attempt in _repair_history_attempts(history):
        imported = int(attempt.get("imported_product_event_count") or 0)
        detail = attempt.get("argus_top_insight") or attempt.get("error") or "No repair detail recorded."
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(attempt.get('company_name') or 'Unknown company')}</strong>"
            f"<span>{_esc(attempt.get('category') or 'uncategorized')} · surface {_esc(attempt.get('surface_id') or '')}</span></td>"
            f"<td><span class=\"pill {_status_class(str(attempt.get('status') or 'unknown'))}\">{_esc(attempt.get('status') or 'unknown')}</span>"
            f"<span>{_esc(attempt.get('generated_at') or '')}</span></td>"
            f"<td>{_esc(attempt.get('row_count') or 0)} extracted rows"
            f"<span>{_esc(imported)} imported product events</span></td>"
            f"<td>{_esc(detail)}</td>"
            f"<td><span>{_esc(attempt.get('summary_path') or '')}</span></td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="5">No product-surface repair attempts have been recorded yet.</td></tr>'
    return "".join(rows)


def _product_surface_repair_history_section(history: dict[str, Any]) -> str:
    latest = history.get("latest") if isinstance(history.get("latest"), dict) else {}
    latest_status = latest.get("status") if latest else "none"
    imported = int(latest.get("imported_product_event_count") or 0) if latest else 0
    return f"""
    <section id="argus-product-surface-repair-history">
      <h2>Latest product-surface repair attempts</h2>
      <div class="muted">Recent bounded repair retries launched from the product muscle queue. This shows whether Scout/product-surface fixes actually produced product proof and whether Argus imported that proof into the intelligence ledger.</div>
      <div class="stats" aria-label="Product-surface repair history summary">
        <div class="stat"><strong>{_esc(history.get('attempt_count', 0))}</strong><span class="muted">recorded attempts</span></div>
        <div class="stat"><strong>{_esc(latest_status)}</strong><span class="muted">latest status</span></div>
        <div class="stat"><strong>{_esc(imported)}</strong><span class="muted">latest imported product events</span></div>
      </div>
      <table aria-label="Latest product-surface repair attempts">
        <thead><tr><th>Target</th><th>Status</th><th>Output</th><th>Result</th><th>Summary</th></tr></thead>
        <tbody>{_product_surface_repair_history_rows(history)}</tbody>
      </table>
    </section>
"""


def _operator_handoff_action(command: ArgusOperatorCommand | None) -> str:
    if command is None:
        return ""
    return _work_item_action(command.label, command.href, command.method)


def _operator_handoff_demand_work_order(handoff: ArgusOperatorHandoff) -> str:
    plan = handoff.demand_collection_plan or {}
    template = handoff.demand_plan_template or {}
    topics = [topic for topic in (plan.get("topics") or []) if isinstance(topic, dict)]
    try:
        topic_count = int(plan.get("topic_count") or len(topics))
    except (TypeError, ValueError):
        topic_count = len(topics)
    filename = str(template.get("filename") or "").strip()
    if not topics and topic_count <= 0 and not filename:
        return ""

    topic_rows: list[str] = []
    for topic in topics[:6]:
        name = str(topic.get("topic") or topic.get("capability_key") or "Untitled demand topic").strip()
        competitors = [
            str(item).strip()
            for item in (topic.get("related_competitors") or [])
            if str(item).strip()
        ]
        competitor_text = ", ".join(competitors[:4]) if competitors else "No competitor attached"
        try:
            evidence_count = int(topic.get("evidence_url_count") or len(topic.get("evidence_urls") or []))
        except (TypeError, ValueError):
            evidence_count = 0
        evidence_text = f"{evidence_count} evidence ref{'s' if evidence_count != 1 else ''}"
        topic_rows.append(
            "<li>"
            f"<strong>{_esc(name)}</strong>"
            f"<span>{_esc(competitor_text)} · {_esc(evidence_text)}</span>"
            "</li>"
        )
    topic_list = "".join(topic_rows) or "<li>No planned demand topics recorded.</li>"
    template_line = (
        f'<p><a href="/api/tenants/{_esc(handoff.tenant_slug)}/argus/demand-imports/template?planned=1">'
        f"Download Argus demand plan template</a>"
        f"{' · ' + _esc(filename) if filename else ''}</p>"
    )
    return f"""
          <div class="operator-demand-work-order">
            <h4>Argus demand work order</h4>
            <p><strong>{_esc(topic_count)} topics to collect</strong></p>
            {template_line}
            <ul class="run-targets">{topic_list}</ul>
          </div>
"""


def _operator_handoff_block(handoff: ArgusOperatorHandoff) -> str:
    top = handoff.top_blocker or {}
    blocker_line = "No top blocker recorded."
    if top:
        blocks = top.get("blocks") or []
        block_text = ", ".join(str(item) for item in blocks) if isinstance(blocks, list) else str(blocks)
        blocker_line = (
            f"{top.get('title') or 'Evidence blocker'} · "
            f"{top.get('evidence_plane') or 'unknown plane'} · "
            f"{top.get('severity') or 'unknown severity'}"
        )
        if block_text:
            blocker_line = f"{blocker_line} · blocks {block_text}"
    actions = " ".join(
        part
        for part in [
            _operator_handoff_action(handoff.primary_command),
            _operator_handoff_action(handoff.secondary_command),
        ]
        if part
    )
    brief = "".join(f"<li>{_esc(line)}</li>" for line in handoff.operator_brief[:4])
    if not brief:
        brief = "<li>No operator brief recorded.</li>"
    demand_work_order = _operator_handoff_demand_work_order(handoff)
    return f"""
        <div class="operator-handoff" id="argus-run-console">
          <h3>Argus operator handoff</h3>
          <div class="stats" aria-label="Argus operator handoff status">
            <div class="stat"><strong class="{_status_class(handoff.status)}">{_esc(handoff.status)}</strong><span class="muted">handoff status</span></div>
            <div class="stat"><strong class="{_status_class(handoff.argus_readiness)}">{_esc(handoff.argus_readiness)}</strong><span class="muted">Argus readiness</span></div>
            <div class="stat"><strong>{_esc((handoff.work_queue or {}).get('blocking_count', 0))}</strong><span class="muted">blocking evidence tasks</span></div>
          </div>
          <p><strong>{_esc(handoff.summary)}</strong></p>
          <p>Next action: {_esc(handoff.next_operator_action)}</p>
          <p>Top blocker: {_esc(blocker_line)}</p>
          <ul class="run-targets">{brief}</ul>
          {demand_work_order}
          <div class="action-cell">{actions}</div>
          <div class="muted">Artifact: {_esc(handoff.artifact_path or 'not recorded')} · found: {_esc(handoff.artifact_found)}</div>
        </div>
"""


def _run_console_targets(run_status: ArgusRunStatus) -> str:
    summary = run_status.product_surface_plan_summary or {}
    targets = summary.get("prioritized_targets") or []
    if not isinstance(targets, list) or not targets:
        return '<li>No learning-prioritized product surfaces recorded for the latest run.</li>'
    rows: list[str] = []
    for target in targets[:5]:
        if not isinstance(target, dict):
            continue
        reasons = target.get("learning_reasons") or []
        reason_text = "; ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else str(reasons)
        rows.append(
            "<li>"
            f"<strong>{_esc(target.get('company_name') or 'Unknown company')}</strong>"
            f"<span>{_esc(target.get('surface_family') or 'surface')} · "
            f"<a href=\"{_esc(target.get('url') or '')}\">{_esc(target.get('url') or '')}</a></span>"
            f"<span>priority {_esc(target.get('learning_priority') or 0)} · {_esc(reason_text)}</span>"
            "</li>"
        )
    return "".join(rows) or '<li>No learning-prioritized product surfaces recorded for the latest run.</li>'


def _run_console_read_rows(run_status: ArgusRunStatus) -> str:
    rows: list[str] = []
    for record in run_status.run_intelligence_history[:5]:
        action = record.primary_action or "No action promoted"
        counts = (
            f"{record.product_event_count} product · "
            f"{record.conversation_theme_count} conversation · "
            f"{record.demand_signal_count} demand"
        )
        learning = (
            f" · {record.learning_instruction_count} learning gates"
            if record.learning_instruction_count
            else ""
        )
        rows.append(
            "<li>"
            f"<strong>{_esc(record.verdict)} · {_esc(record.top_insight)}</strong>"
            f"<span>{_esc(action)}</span>"
            f"<span>{_esc(counts)}{_esc(learning)} · {_esc(len(record.evidence_urls))} proof links</span>"
            "</li>"
        )
    return "".join(rows) or '<li>No persisted Argus run reads recorded yet.</li>'


def _ledger_replay_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _run_console_latest_ledger_replay(run_status: ArgusRunStatus) -> str:
    ledger_refresh = _ledger_replay_dict(run_status.ledger_refresh_summary)
    brief = _ledger_replay_dict(ledger_refresh.get("intelligence_brief"))
    demand_read = _ledger_replay_dict(brief.get("demand_read"))
    conversion = _ledger_replay_dict(brief.get("conversion_diagnostics"))
    blockers = conversion.get("blockers") or []
    if not isinstance(blockers, list):
        blockers = [str(blockers)]
    blocker_rows = "".join(f"<li>{_esc(blocker)}</li>" for blocker in blockers[:4] if str(blocker).strip())
    if not blocker_rows:
        blocker_rows = "<li>No conversion blocker recorded.</li>"
    counts = (
        f"{int(ledger_refresh.get('product_event_count') or 0)} product · "
        f"{int(ledger_refresh.get('conversation_theme_count') or 0)} conversation · "
        f"{int(ledger_refresh.get('demand_signal_count') or 0)} demand · "
        f"{int(ledger_refresh.get('pattern_count') or 0)} pattern · "
        f"{int(ledger_refresh.get('recommendation_count') or 0)} recommendations"
    )
    if not ledger_refresh:
        return """
        <div>
          <h3>Latest ledger replay read</h3>
          <p>No ledger replay has been recorded for this tenant yet.</p>
        </div>
        """
    return f"""
        <div>
          <h3>Latest ledger replay read</h3>
          <p><strong>{_esc(ledger_refresh.get('verdict') or 'not recorded')}</strong> · {_esc(counts)}</p>
          <p><strong>Top insight:</strong> {_esc(brief.get('top_insight') or 'No replay insight recorded.')}</p>
          <p><strong>Primary action:</strong> {_esc(brief.get('primary_action') or 'No action promoted.')}</p>
          <p><strong>Demand read:</strong> {_esc(demand_read.get('summary') or 'No demand read recorded.')}</p>
          <p><strong>Conversion diagnostics:</strong> {_esc(conversion.get('summary') or 'No conversion diagnostic recorded.')}</p>
          <ul class="run-targets">{blocker_rows}</ul>
        </div>
    """


def _manifest_source_line(manifest: ArgusDataPlaneManifest) -> str:
    source = manifest.source_of_truth or {}
    parts = [
        source.get("runtime"),
        source.get("domain_package"),
        source.get("database"),
    ]
    return " · ".join(str(part) for part in parts if part) or "source of truth not recorded"


def _plane_counts_label(counts: dict[str, int]) -> str:
    parts = [f"{key.replace('_', ' ')} {value}" for key, value in list(counts.items())[:4]]
    return " · ".join(parts) if parts else "no counts recorded"


def _data_plane_rows(manifest: ArgusDataPlaneManifest) -> str:
    if not manifest.planes:
        return '<tr><td colspan="4">No data-plane manifest has been recorded yet.</td></tr>'
    order = [
        "registry_coverage",
        "product_reality",
        "market_conversation",
        "audience_demand",
        "operator_learning",
        "run_truth",
    ]
    ordered_keys = [key for key in order if key in manifest.planes]
    ordered_keys.extend(key for key in manifest.planes if key not in ordered_keys)
    rows: list[str] = []
    for key in ordered_keys:
        plane = manifest.planes[key]
        status = f"{plane.status}{' · blocks action' if plane.blocks_action else ''}"
        next_action = f"Next Hermes action: {plane.next_hermes_action}" if plane.next_hermes_action else ""
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(key.replace('_', ' '))}</strong><span>{_esc(plane.summary)}</span></td>"
            f"<td><span class=\"pill {_status_class(plane.status)}\">{_esc(status)}</span></td>"
            f"<td>{_esc(_plane_counts_label(plane.counts))}<span>{_esc(next_action)}</span></td>"
            f"<td>{_esc(', '.join(plane.storage[:4]) or 'not recorded')}</td>"
            "</tr>"
        )
    return "".join(rows)


def _data_plane_blockers(manifest: ArgusDataPlaneManifest) -> str:
    rows = []
    for blocker in manifest.blockers[:4]:
        rows.append(
            "<li>"
            f"<strong>{_esc(blocker.get('title') or 'Evidence blocker')}</strong>"
            f"<span>{_esc(blocker.get('plane') or 'unknown plane')} · {_esc(blocker.get('severity') or 'unknown severity')}</span>"
            f"<span>{_esc(blocker.get('next_step') or 'No next step recorded.')}</span>"
            "</li>"
        )
    return "".join(rows) or "<li>No blocking data-plane gaps recorded.</li>"


def _data_plane_manifest_block(manifest: ArgusDataPlaneManifest) -> str:
    return f"""
        <div>
          <h3>Argus operating planes</h3>
          <div class="muted">{_esc(_manifest_source_line(manifest))}</div>
          <div class="stats" aria-label="Argus operating plane manifest summary">
            <div class="stat"><strong class="{_status_class(manifest.status)}">{_esc(manifest.status)}</strong><span class="muted">manifest status</span></div>
            <div class="stat"><strong class="{_status_class(manifest.argus_readiness)}">{_esc(manifest.argus_readiness)}</strong><span class="muted">Argus readiness</span></div>
            <div class="stat"><strong>{_esc(len(manifest.planes))}</strong><span class="muted">operating planes</span></div>
            <div class="stat"><strong>{_esc(len(manifest.blockers))}</strong><span class="muted">blocking gaps</span></div>
          </div>
          <p>Next Hermes action: {_esc(manifest.next_hermes_action)}</p>
          <table aria-label="Argus operating planes">
            <thead><tr><th>Plane</th><th>Status</th><th>Counts</th><th>Storage</th></tr></thead>
            <tbody>{_data_plane_rows(manifest)}</tbody>
          </table>
          <ul class="run-targets">{_data_plane_blockers(manifest)}</ul>
          <div class="muted">Artifact: {_esc(manifest.artifact_path or 'not recorded')} · found: {_esc(manifest.artifact_found)}</div>
        </div>
"""


def _run_console_section(
    run_status: ArgusRunStatus,
    operator_handoff: ArgusOperatorHandoff,
    data_plane_manifest: ArgusDataPlaneManifest,
) -> str:
    summary = run_status.product_surface_plan_summary or {}
    runner = run_status.runner_summary or {}
    ledger_refresh = run_status.ledger_refresh_summary or {}
    target_count = summary.get("target_count", 0)
    prioritized_count = summary.get("learning_prioritized_count", 0)
    verdict = runner.get("verdict") or "not recorded"
    ledger_refresh_verdict = ledger_refresh.get("verdict") or "not recorded"
    ledger_refresh_brief = ledger_refresh.get("intelligence_brief")
    if not isinstance(ledger_refresh_brief, dict):
        ledger_refresh_brief = {}
    ledger_refresh_insight = ledger_refresh_brief.get("top_insight") or "No ledger replay insight recorded."
    learning_count = runner.get("learning_instruction_count", 0)
    ledger_learning_count = ledger_refresh.get("learning_instruction_count", 0)
    report_label = (
        f"Report {run_status.report_id} · {run_status.report_date} · {run_status.cadence}"
        if run_status.report_id
        else "No report metadata recorded yet"
    )
    scout_count = len(run_status.scout_paths)
    first_scout = run_status.scout_paths[0] if run_status.scout_paths else None
    errors = "; ".join(run_status.errors[:3]) if run_status.errors else "No run errors recorded."
    apply_summary = run_status.learning_apply_plan_summary
    apply_action_count = int(apply_summary.get("action_count") or 0)
    apply_targets = apply_summary.get("targets") or []
    if not isinstance(apply_targets, list):
        apply_targets = [str(apply_targets)]
    apply_paths = apply_summary.get("package_paths") or []
    if not isinstance(apply_paths, list):
        apply_paths = [str(apply_paths)]
    apply_target_label = ", ".join(str(item) for item in apply_targets[:3] if str(item).strip())
    apply_path_label = ", ".join(str(item) for item in apply_paths[:2] if str(item).strip())
    apply_line = (
        f"{apply_action_count} package action{'s' if apply_action_count != 1 else ''} proposed"
        if run_status.learning_apply_plan_path or apply_action_count
        else "not recorded"
    )
    if apply_target_label:
        apply_line = f"{apply_line}: {apply_target_label}"
    if apply_path_label:
        apply_line = f"{apply_line} · {apply_path_label}"
    demand_detail = (
        f"{run_status.looker_normalized_row_count} demand rows · "
        f"{run_status.looker_discovered_count} export file"
        f"{'' if run_status.looker_discovered_count == 1 else 's'} discovered"
    )
    if run_status.looker_error_count:
        demand_detail = (
            f"{demand_detail} · {run_status.looker_error_count} parse error"
            f"{'' if run_status.looker_error_count == 1 else 's'}"
        )
    return f"""
    <section>
      <h2>Argus run console</h2>
      <div class="muted">Latest Hermes-run CI-OS package evidence. This is read-only run state, not registry configuration.</div>
      <div class="stats" aria-label="Latest Argus run summary">
        <div class="stat"><strong class="{_status_class(run_status.product_market_status)}">{_esc(run_status.product_market_status)}</strong><span class="muted">Product-market chain</span></div>
        <div class="stat"><strong>{_esc(target_count)}</strong><span class="muted">surface targets</span></div>
        <div class="stat"><strong>{_esc(prioritized_count)}</strong><span class="muted">learning-prioritized</span></div>
        <div class="stat"><strong>{_esc(scout_count)}</strong><span class="muted">Scout artifacts</span></div>
        <div class="stat"><strong>{_esc(verdict)}</strong><span class="muted">runner verdict</span></div>
        <div class="stat"><strong class="{_status_class(run_status.ledger_refresh_status)}">{_esc(ledger_refresh_verdict)}</strong><span class="muted">Ledger replay</span></div>
        <div class="stat"><strong class="{_status_class(run_status.demand_plane_status)}">{_esc(run_status.demand_plane_status)}</strong><span class="muted">Inward demand</span></div>
      </div>
      <div class="muted">{_esc(demand_detail)}</div>
      <div class="run-console-grid">
        {_operator_handoff_block(operator_handoff)}
        {_data_plane_manifest_block(data_plane_manifest)}
        <div>
          <h3>What Argus prioritized</h3>
          <ul class="run-targets">{_run_console_targets(run_status)}</ul>
        </div>
        <div>
          <h3>Argus run reads</h3>
          <ul class="run-targets">{_run_console_read_rows(run_status)}</ul>
        </div>
        {_run_console_latest_ledger_replay(run_status)}
        <div>
          <h3>Run evidence</h3>
          <p><strong>{_esc(report_label)}</strong></p>
          <p>Learning instructions consumed: {_esc(learning_count)}</p>
          <p>Ledger replay: {_esc(run_status.ledger_refresh_status)} · {_esc(ledger_refresh_verdict)} · {_esc(ledger_learning_count)} learning gates</p>
          <p>Ledger replay insight: {_esc(ledger_refresh_insight)}</p>
          <p>Learning plan: {_esc(run_status.next_sweep_plan_path or 'not recorded')}</p>
          <p>Learning apply plan: {_esc(apply_line)}</p>
          <p>First Scout artifact: {_esc(first_scout or 'not recorded')}</p>
          <p>Errors: {_esc(errors)}</p>
        </div>
      </div>
    </section>
"""


def _learning_apply_rows(items: list, *, empty: str) -> str:
    rows: list[str] = []
    for item in items[:30]:
        trace = (
            f"evidence {', '.join(str(i) for i in item.evidence_event_ids) or 'none'} · "
            f"improvements {', '.join(str(i) for i in item.source_improvement_ids) or 'none'}"
        )
        approved = f"approved by {item.approved_by}" if item.approved_by else "approval pending"
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(item.target)}</strong><span>{_esc(item.summary)}</span></td>"
            f"<td>{_esc(item.status)}<span>{_esc(approved)}</span></td>"
            f"<td>{_esc(item.package_path)}</td>"
            f"<td>{_esc(trace)}</td>"
            "</tr>"
        )
    if not rows:
        return f'<tr><td colspan="4">{_esc(empty)}</td></tr>'
    return "".join(rows)


def _learning_policy_audit_rows(items: list, *, empty: str) -> str:
    rows: list[str] = []
    for item in items[:20]:
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(item.code)}</strong><span>{_esc(item.message)}</span></td>"
            f"<td>{_esc(item.package_path)}<span>{_esc(item.target or '')}</span></td>"
            f"<td>{_esc(item.action_id or '')}<span>expected {_esc(item.expected_action_id or '')}</span></td>"
            f"<td>{_esc(item.rollback_hint)}</td>"
            "</tr>"
        )
    if not rows:
        return f'<tr><td colspan="4">{_esc(empty)}</td></tr>'
    return "".join(rows)


def _learning_policy_audit_section(status: LearningApplyStatus) -> str:
    audit = status.policy_audit
    verdict = "Policy audit clean" if audit.passed else "Policy audit failed"
    return f"""
      <h3>Learning policy audit</h3>
      <div class="muted">Latest package-local drift check for approved CI-OS learning policies before Hermes production runs.</div>
      <div class="stats" aria-label="Learning policy audit summary">
        <div class="stat"><strong class="{_status_class('ok' if audit.passed else 'failed')}">{_esc(verdict)}</strong><span class="muted">audit verdict</span></div>
        <div class="stat"><strong>{_esc(audit.policy_count)}</strong><span class="muted">approved policies checked</span></div>
        <div class="stat"><strong>{_esc(audit.issue_count)}</strong><span class="muted">policy issues</span></div>
        <div class="stat"><strong>{_esc(audit.drift_count)}</strong><span class="muted">drifted policies</span></div>
        <div class="stat"><strong>{_esc(audit.invalid_count)}</strong><span class="muted">invalid policies</span></div>
      </div>
      <table aria-label="Learning policy audit issues">
        <thead><tr><th>Issue</th><th>Policy</th><th>Action id</th><th>Rollback</th></tr></thead>
        <tbody>{_learning_policy_audit_rows(audit.issues, empty="No learning policy audit issues.")}</tbody>
      </table>
"""


def _learning_apply_section(status: LearningApplyStatus) -> str:
    return f"""
    <section>
      <h2>Argus learning apply</h2>
      <div class="muted">Package-local learning artifacts. Pending proposals need human review; approved policies are loaded into future next-sweep plans without touching Hermes core.</div>
      <div class="stats" aria-label="Argus learning apply summary">
        <div class="stat"><strong>{_esc(status.proposal_count)}</strong><span class="muted">package proposals</span></div>
        <div class="stat"><strong>{_esc(status.approved_policy_count)}</strong><span class="muted">approved policies</span></div>
      </div>
      {_learning_policy_audit_section(status)}
      <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/learning-apply/execute">
        <button type="submit">Prepare apply proposals</button>
      </form>
      <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/learning-apply/execute">
        <label>Approved by<input name="approved_by" required placeholder="operator name" /></label>
        <button type="submit">Apply approved policies</button>
      </form>
      <h3>Pending package proposals</h3>
      <table aria-label="Argus learning apply proposals">
        <thead><tr><th>Target</th><th>Status</th><th>Package path</th><th>Trace</th></tr></thead>
        <tbody>{_learning_apply_rows(status.proposals, empty="No learning apply proposals recorded.")}</tbody>
      </table>
      <h3>Approved package policies</h3>
      <table aria-label="Argus approved learning policies">
        <thead><tr><th>Target</th><th>Status</th><th>Package path</th><th>Trace</th></tr></thead>
        <tbody>{_learning_apply_rows(status.approved_policies, empty="No approved learning policies recorded.")}</tbody>
      </table>
    </section>
"""


def _demand_file_rows(files: list, *, empty: str) -> str:
    rows: list[str] = []
    for item in files[:20]:
        rows.append(
            "<tr>"
            f"<td>{_esc(item.name)}</td>"
            f"<td>{_esc(item.size_bytes)}</td>"
            f"<td>{_esc(item.modified_at or '')}</td>"
            f"<td>{_esc(item.path)}</td>"
            "</tr>"
        )
    if not rows:
        return f'<tr><td colspan="4">{_esc(empty)}</td></tr>'
    return "".join(rows)


def _demand_preview_rows(status: DemandImportStatus) -> str:
    rows: list[str] = []
    for item in status.inbox_previews[:20]:
        detail = ", ".join(item.topics[:5]) if item.topics else (item.error or "")
        coverage = _demand_plan_coverage_cell(item.demand_plan_coverage)
        rows.append(
            "<tr>"
            f"<td>{_esc(item.name)}</td>"
            f"<td><span class=\"pill {_status_class(item.status)}\">{_esc(item.status)}</span></td>"
            f"<td>{_esc(item.raw_row_count)}</td>"
            f"<td>{_esc(item.normalized_row_count)}</td>"
            f"<td>{_esc(item.skipped_row_count)}</td>"
            f"<td>{coverage}</td>"
            f"<td>{_esc(detail)}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="7">No queued demand files to preview.</td></tr>'
    return "".join(rows)


def _demand_plan_coverage_cell(coverage: dict[str, Any]) -> str:
    if not coverage:
        return '<span class="muted">No Argus plan loaded.</span>'
    status = str(coverage.get("status") or "not_evaluated")
    try:
        matched = int(coverage.get("matched_plan_topic_count") or 0)
    except (TypeError, ValueError):
        matched = 0
    try:
        planned = int(coverage.get("planned_topic_count") or 0)
    except (TypeError, ValueError):
        planned = 0
    matched_topics = _coverage_topic_names(coverage.get("matched_topics"))
    missing_topics = _coverage_topic_names(coverage.get("missing_topics"))
    parts = [
        f'<span class="pill {_status_class(status)}">{_esc(status)}</span>',
        f"<span>{_esc(matched)}/{_esc(planned)} planned topics</span>",
    ]
    if matched_topics:
        parts.append(f"<span>matched: {_esc(', '.join(matched_topics[:4]))}</span>")
    if missing_topics:
        parts.append(f"<span>missing: {_esc(', '.join(missing_topics[:4]))}</span>")
    return "".join(parts)


def _coverage_topic_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("topic") or item.get("capability_key") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            names.append(name)
    return names


def _manifest_file_name(path: object) -> str:
    text = str(path or "").strip()
    if not text:
        return "unknown file"
    return text.rsplit("/", 1)[-1]


def _demand_manifest_diagnostic_rows(status: DemandImportStatus) -> str:
    files = status.manifest.get("files") if isinstance(status.manifest, dict) else None
    if not isinstance(files, list):
        return '<tr><td colspan="5">No demand import diagnostics recorded yet.</td></tr>'
    rows: list[str] = []
    for item in files[:12]:
        if not isinstance(item, dict):
            continue
        skipped_rows = item.get("skipped_rows")
        if isinstance(skipped_rows, list) and skipped_rows:
            for skipped in skipped_rows[:5]:
                if not isinstance(skipped, dict):
                    continue
                missing = skipped.get("missing_fields") or []
                columns = skipped.get("available_columns") or []
                missing_line = ", ".join(str(value) for value in missing) if isinstance(missing, list) else str(missing)
                columns_line = ", ".join(str(value) for value in columns) if isinstance(columns, list) else str(columns)
                rows.append(
                    "<tr>"
                    f"<td>{_esc(skipped.get('source_file') or _manifest_file_name(item.get('path')))}</td>"
                    f"<td>{_esc(skipped.get('row_number') or '')}</td>"
                    f"<td><span class=\"pill pending\">{_esc(skipped.get('reason') or 'skipped')}</span></td>"
                    f"<td>missing fields: {_esc(missing_line)}</td>"
                    f"<td>available columns: {_esc(columns_line)}</td>"
                    "</tr>"
                )
        elif item.get("status") == "error":
            rows.append(
                "<tr>"
                f"<td>{_esc(_manifest_file_name(item.get('path')))}</td>"
                "<td></td>"
                '<td><span class="pill failed">parse_error</span></td>'
                f"<td>{_esc(item.get('error') or 'File could not be parsed.')}</td>"
                f"<td>available columns: {_esc(', '.join(str(key) for key in item.keys()))}</td>"
                "</tr>"
            )
    if not rows:
        return '<tr><td colspan="5">No skipped demand rows or parse errors in the latest manifest.</td></tr>'
    return "".join(rows)


def _demand_intake_attempts(history: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = [item for item in history.get("attempts", []) if isinstance(item, dict)]
    latest = history.get("latest") if isinstance(history.get("latest"), dict) else None
    if latest and latest not in attempts:
        attempts = [latest, *attempts]
    return attempts[:5]


def _demand_intake_rows(history: dict[str, Any]) -> str:
    rows: list[str] = []
    for attempt in _demand_intake_attempts(history):
        detail = attempt.get("argus_top_insight") or attempt.get("error") or attempt.get("readiness_summary") or ""
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(attempt.get('status') or 'unknown')}</strong>"
            f"<span>{_esc(attempt.get('mode') or '')} · exit {_esc(attempt.get('exit_code'))}</span></td>"
            f"<td>{_esc(attempt.get('readiness_status') or '')}<span>{_esc(attempt.get('next_hermes_action') or '')}</span></td>"
            f"<td>{_esc(attempt.get('normalized_row_count') or 0)} normalized rows"
            f"<span>{_esc(attempt.get('demand_signal_count') or 0)} demand signals</span></td>"
            f"<td>{_esc(detail)}</td>"
            f"<td><span>{_esc(attempt.get('summary_path') or '')}</span></td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="5">No Argus demand intake attempts have been recorded yet.</td></tr>'
    return "".join(rows)


def _demand_intake_section(history: dict[str, Any], tenant_slug: str) -> str:
    latest = history.get("latest") if isinstance(history.get("latest"), dict) else {}
    latest_status = latest.get("status") if latest else "none"
    next_action = latest.get("next_hermes_action") if latest else "not recorded"
    return f"""
    <section id="argus-demand-intake">
      <h2>Argus demand intake</h2>
      <div class="muted">Hermes-facing operation for the inward demand plane: inspect readiness, run GA4 when configured, process queued GA / Looker exports, persist demand signals, refresh Argus, and record the result as operator-visible state.</div>
      <div class="stats" aria-label="Argus demand intake summary">
        <div class="stat"><strong>{_esc(history.get('attempt_count', 0))}</strong><span class="muted">recorded attempts</span></div>
        <div class="stat"><strong>{_esc(latest_status)}</strong><span class="muted">latest status</span></div>
        <div class="stat"><strong>{_esc(next_action)}</strong><span class="muted">next Hermes action</span></div>
      </div>
      <form method="post" action="/admin/{_esc(tenant_slug)}/argus/demand-intake">
        <label>Days<input name="days" type="number" min="1" value="30" /></label>
        <label>Limit<input name="limit" type="number" min="1" value="500" /></label>
        <label>Timeout seconds<input name="command_timeout_seconds" type="number" min="30" value="300" /></label>
        <button type="submit">Run demand intake</button>
      </form>
      <table aria-label="Argus demand intake attempts">
        <thead><tr><th>Status</th><th>Readiness</th><th>Demand output</th><th>Result</th><th>Summary</th></tr></thead>
        <tbody>{_demand_intake_rows(history)}</tbody>
      </table>
    </section>
"""


def _ga4_connector_section(status: Ga4ExportStatus) -> str:
    if status.missing_required:
        missing = ", ".join(status.missing_required)
    elif not status.enabled:
        missing = (
            "Set CIOS_GA4_EXPORT_ENABLED=1, CIOS_GA4_PROPERTY_ID, "
            "and CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS."
        )
    else:
        missing = "None"
    credential_label = "configured" if status.credentials_configured else "missing"
    setup_note = (
        ""
        if status.ready
        else (
            "<p><strong>Connector setup needed</strong>: "
            "Set CIOS_GA4_EXPORT_ENABLED=1, configure CIOS_GA4_PROPERTY_ID, "
            "and CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS. "
            "Date windows default to the last 7 complete UTC days; use "
            "CIOS_GA4_CURRENT_START/END and CIOS_GA4_PREVIOUS_START/END only "
            "for explicit backfills.</p>"
        )
    )
    button_attrs = "" if status.ready else ' disabled aria-disabled="true"'
    return f"""
        <div>
          <h3>GA4 connector</h3>
          <p><strong><span class="pill {_status_class(status.status)}">{_esc(status.status)}</span></strong></p>
          <p>{_esc(status.message)}</p>
          {setup_note}
          <p>Window: {_esc(status.current_start or 'not set')} to {_esc(status.current_end or 'not set')} · compare {_esc(status.previous_start or 'not set')} to {_esc(status.previous_end or 'not set')}</p>
          <p>Metric: {_esc(status.metric)} · topic {_esc(status.topic_dimension)} · URL {_esc(status.url_dimension or 'disabled')} · limit {_esc(status.limit)}</p>
          <p>Credentials: {_esc(credential_label)} · export script: {_esc('present' if status.script_path_exists else 'missing')}</p>
          <p>Missing: {_esc(missing)}</p>
          <p>Output: {_esc(status.output_path)}</p>
          <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/ga4-export">
            <button type="submit"{button_attrs}>Run GA4 export now</button>
          </form>
          <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/ga4-export/refresh">
            <button type="submit"{button_attrs}>Run GA4 export and refresh Argus</button>
          </form>
        </div>
"""


def _demand_source_contract_section(status: DemandImportStatus, ga4_status: Ga4ExportStatus) -> str:
    ready_preview_count = len([item for item in status.inbox_previews if item.status == "ready"])
    error_preview_count = len([item for item in status.inbox_previews if item.status == "error"])
    preview_row_count = sum(item.normalized_row_count for item in status.inbox_previews)
    try:
        work_root = Path(status.manifest_path).parent.parent
    except IndexError:
        work_root = Path(status.manifest_path).parent
    contract = build_demand_source_contract(
        tenant_slug=status.tenant_slug,
        work_root=work_root,
        demand_plane={},
        manual_import={
            "drop_folder": status.drop_folder,
            "manifest_path": status.manifest_path,
            "accepted_suffixes": status.accepted_suffixes,
            "template_fields": list(DEMAND_IMPORT_TEMPLATE_FIELDS),
            "inbox_file_count": len(status.inbox_files),
            "ready_preview_count": ready_preview_count,
            "error_preview_count": error_preview_count,
            "normalized_preview_row_count": preview_row_count,
        },
        ga4_connector={
            "enabled": ga4_status.enabled,
            "ready": ga4_status.ready,
            "status": ga4_status.status,
            "setup_required": ga4_status.setup_required,
            "missing_required": ga4_status.missing_required,
            "current_window": {"start": ga4_status.current_start, "end": ga4_status.current_end},
            "previous_window": {"start": ga4_status.previous_start, "end": ga4_status.previous_end},
            "metric": ga4_status.metric,
            "topic_dimension": ga4_status.topic_dimension,
            "url_dimension": ga4_status.url_dimension,
            "output_name": Path(ga4_status.output_path).name,
        },
    )
    rows = []
    for source in contract["sources"]:
        detail = source.get("landing_zone") or ", ".join(source.get("setup_required") or []) or source.get("output_name") or ""
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(source.get('label'))}</strong>"
            f"<span>{_esc(source.get('source_family'))} · {_esc(source.get('owner'))}</span></td>"
            f"<td><span class=\"pill {_status_class(source.get('status'))}\">{_esc(source.get('status'))}</span>"
            f"<span>{_esc(source.get('cadence'))}</span></td>"
            f"<td>{_esc('ready' if source.get('ready') else 'not ready')}</td>"
            f"<td><span>{_esc(detail)}</span></td>"
            "</tr>"
        )
    return f"""
          <h3>Demand source contract</h3>
          <p>Status: <strong>{_esc(contract['status'])}</strong> · Ready sources: {_esc(contract['ready_source_count'])}/{_esc(contract['source_count'])}</p>
          <p class="muted">{_esc(contract['summary'])}</p>
          <p class="muted">Contract: {_esc(contract['contract_path'])}</p>
          <table aria-label="Demand source contract">
            <thead><tr><th>Source</th><th>Status</th><th>Ready</th><th>Landing or setup</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
"""


def _demand_import_section(status: DemandImportStatus, ga4_status: Ga4ExportStatus) -> str:
    manifest_status = "present" if status.manifest_exists else "missing"
    ready_preview_count = len([item for item in status.inbox_previews if item.status == "ready"])
    preview_row_count = sum(item.normalized_row_count for item in status.inbox_previews)
    return f"""
    <section>
      <h2>Demand imports</h2>
      <div class="muted">GA / Looker exports queued here become Argus demand signals in the next Hermes sweep. This is the inward evidence plane, separate from competitor chatter and product-surface Scout exports.</div>
      <div class="stats" aria-label="Demand import summary">
        <div class="stat"><strong>{_esc(len(status.inbox_files))}</strong><span class="muted">queued files</span></div>
        <div class="stat"><strong>{_esc(status.ready_count)}</strong><span class="muted">ready last run</span></div>
        <div class="stat"><strong>{_esc(status.error_count)}</strong><span class="muted">errors last run</span></div>
        <div class="stat"><strong>{_esc(status.normalized_row_count)}</strong><span class="muted">accepted demand rows</span></div>
        <div class="stat"><strong>{_esc(preview_row_count)}</strong><span class="muted">queued valid rows</span></div>
        <div class="stat"><strong class="{_status_class('ok' if status.manifest_exists else 'missing')}">{_esc(manifest_status)}</strong><span class="muted">latest manifest</span></div>
      </div>
      <div class="run-console-grid">
        <div>
          <h3>Upload GA / Looker export</h3>
          <form class="demand-form" method="post" enctype="multipart/form-data" action="/admin/{_esc(status.tenant_slug)}/argus/demand-imports">
            <label>GA / Looker file<input type="file" name="file" accept=".csv,.json,.jsonl,text/csv,application/json,application/x-ndjson" required /></label>
            <button type="submit">Queue demand export</button>
          </form>
          <p><a href="/api/tenants/{_esc(status.tenant_slug)}/argus/demand-imports/template">Download demand template</a></p>
          <p><a href="/api/tenants/{_esc(status.tenant_slug)}/argus/demand-imports/template?planned=1">Download Argus demand plan template</a></p>
          <p><a href="/api/tenants/{_esc(status.tenant_slug)}/argus/demand-imports/work-order">View demand work-order guide</a></p>
          <p class="muted">Drop folder: {_esc(status.drop_folder)}</p>
          <p class="muted">Manifest: {_esc(status.manifest_path)}</p>
        </div>
        {_ga4_connector_section(ga4_status)}
        <div>
          <h3>Latest manifest</h3>
          <p>Discovered: {_esc(status.discovered_count)} · Ready: {_esc(status.ready_count)} · Skipped rows: {_esc(status.skipped_row_count)}</p>
          <p>Queued demand preview: {_esc(ready_preview_count)} ready file(s), {_esc(preview_row_count)} demand row(s) usable on the next sweep.</p>
          <p>Accepted suffixes: {_esc(', '.join(status.accepted_suffixes))}</p>
          <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/demand-imports/refresh">
            <button type="submit">Prepare demand and refresh Argus</button>
          </form>
          <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/demand-imports/prepare">
            <button type="submit">Prepare queued demand now</button>
          </form>
          <form method="post" action="/admin/{_esc(status.tenant_slug)}/argus/ledger-refresh">
            <button type="submit">Refresh Argus from evidence ledger</button>
          </form>
        </div>
      </div>
      {_demand_source_contract_section(status, ga4_status)}
      <h3>Queued demand preview</h3>
      <table aria-label="Queued demand preview">
        <thead><tr><th>Name</th><th>Status</th><th>Raw rows</th><th>Demand rows</th><th>Skipped</th><th>Plan coverage</th><th>Topics or error</th></tr></thead>
        <tbody>{_demand_preview_rows(status)}</tbody>
      </table>
      <h3>Demand import diagnostics</h3>
      <table aria-label="Demand import diagnostics">
        <thead><tr><th>File</th><th>Row</th><th>Reason</th><th>Missing fields</th><th>Available columns</th></tr></thead>
        <tbody>{_demand_manifest_diagnostic_rows(status)}</tbody>
      </table>
      <h3>Queued demand files</h3>
      <table aria-label="Queued demand files">
        <thead><tr><th>Name</th><th>Bytes</th><th>Modified</th><th>Path</th></tr></thead>
        <tbody>{_demand_file_rows(status.inbox_files, empty='No GA / Looker exports are waiting for the next sweep.')}</tbody>
      </table>
      <h3>Archived and rejected demand files</h3>
      <table aria-label="Processed demand files">
        <thead><tr><th>Name</th><th>Bytes</th><th>Modified</th><th>Path</th></tr></thead>
        <tbody>{_demand_file_rows(status.archived_files + status.rejected_files, empty='No processed demand exports recorded yet.')}</tbody>
      </table>
    </section>
"""


def _evidence_urls(evidence_refs: list[dict]) -> list[str]:
    urls: list[str] = []
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        url = str(ref.get("source_url") or "").strip()
        if url:
            urls.append(url)
    return urls


def _feature_matrix_rows(rows: list[FeatureMatrixAdminRecord]) -> str:
    html_rows: list[str] = []
    for row in rows[:80]:
        urls = _evidence_urls(row.evidence_refs)
        proof = urls[0] if urls else ""
        proof_text = f'<a href="{_esc(proof)}">{_esc(proof)}</a>' if proof else "No proof link on file."
        html_rows.append(
            "<tr>"
            f"<td><strong>{_esc(row.capability_text)}</strong><span>{_esc(row.summary or '')}</span></td>"
            f"<td>{_esc(row.company_name)}<span>{_esc(row.company_role)}</span></td>"
            f"<td><span class=\"pill {_status_class(row.position_status)}\">{_esc(row.position_status)}</span></td>"
            f"<td>{_esc(row.confidence if row.confidence is not None else '')}</td>"
            f"<td>{proof_text}<span>{_esc(len(urls))} proof links</span></td>"
            f"<td>{_esc(row.updated_at or '')}</td>"
            "</tr>"
        )
    if not html_rows:
        return '<tr><td colspan="6">No product muscle matrix rows have been captured yet.</td></tr>'
    return "".join(html_rows)


def _feature_matrix_section(rows: list[FeatureMatrixAdminRecord]) -> str:
    capability_count = len({row.capability_text for row in rows})
    company_count = len({row.company_name for row in rows})
    proven_count = sum(1 for row in rows if row.position_status == "proven")
    gap_count = sum(1 for row in rows if row.position_status == "gap")
    return f"""
    <section>
      <h2>Product muscle matrix</h2>
      <div class="muted">What Scout/product-surface evidence says companies actually have. This is product proof, not market conversation.</div>
      <div class="stats" aria-label="Product muscle matrix summary">
        <div class="stat"><strong>{_esc(capability_count)}</strong><span class="muted">capabilities</span></div>
        <div class="stat"><strong>{_esc(company_count)}</strong><span class="muted">companies</span></div>
        <div class="stat"><strong>{_esc(proven_count)}</strong><span class="muted">proven positions</span></div>
        <div class="stat"><strong>{_esc(gap_count)}</strong><span class="muted">captured gaps</span></div>
      </div>
      <table aria-label="Product muscle matrix">
        <thead><tr><th>Capability</th><th>Company</th><th>Status</th><th>Confidence</th><th>Evidence</th><th>Updated</th></tr></thead>
        <tbody>{_feature_matrix_rows(rows)}</tbody>
      </table>
    </section>
"""


def _feature_comparison_cell(cell) -> str:
    proof = (
        f'<a href="{_esc(cell.first_evidence_url)}">{_esc(cell.evidence_count)} proof link'
        f'{"s" if cell.evidence_count != 1 else ""}</a>'
        if cell.first_evidence_url
        else f"{_esc(cell.evidence_count)} proof links"
    )
    confidence = "" if cell.confidence is None else f" · confidence {_esc(cell.confidence)}"
    return (
        f"<td><strong><span class=\"pill {_status_class(cell.position_status)}\">"
        f"{_esc(cell.position_status)}</span></strong>"
        f"<span>{_esc(cell.summary)}</span>"
        f"<span>{proof}{confidence}</span></td>"
    )


def _feature_comparison_rows(comparison: FeatureComparisonState) -> str:
    if not comparison.rows:
        colspan = max(len(comparison.companies) + 1, 2)
        return f'<tr><td colspan="{colspan}">No feature comparison rows are available yet.</td></tr>'
    rows: list[str] = []
    for row in comparison.rows[:40]:
        cells = "".join(_feature_comparison_cell(cell) for cell in row.cells)
        counts = (
            f"{row.proven_count} proven · {row.gap_count} gaps · "
            f"{row.unknown_count} unknown · {row.evidence_count} proof links"
        )
        rows.append(
            "<tr>"
            f"<td><strong>{_esc(row.capability_text)}</strong><span>{_esc(counts)}</span></td>"
            f"{cells}"
            "</tr>"
        )
    return "".join(rows)


def _feature_comparison_section(comparison: FeatureComparisonState) -> str:
    company_headers = "".join(
        f"<th>{_esc(company.company_name)}<span>{_esc(company.company_role)}</span></th>"
        for company in comparison.companies
    )
    proven_total = sum(row.proven_count for row in comparison.rows)
    gap_total = sum(row.gap_count for row in comparison.rows)
    unknown_total = sum(row.unknown_count for row in comparison.rows)
    return f"""
    <section>
      <h2>Product feature comparison</h2>
      <div class="muted">A cross-company view of captured product proof. Unknown means Argus has not captured product evidence for that company and capability; it is not yet a claim that the product lacks it.</div>
      <div class="stats" aria-label="Product feature comparison summary">
        <div class="stat"><strong>{_esc(len(comparison.companies))}</strong><span class="muted">companies</span></div>
        <div class="stat"><strong>{_esc(len(comparison.rows))}</strong><span class="muted">capabilities</span></div>
        <div class="stat"><strong>{_esc(proven_total)}</strong><span class="muted">proven cells</span></div>
        <div class="stat"><strong>{_esc(gap_total)}</strong><span class="muted">captured gaps</span></div>
        <div class="stat"><strong>{_esc(unknown_total)}</strong><span class="muted">unknown cells</span></div>
      </div>
      <table aria-label="Product feature comparison">
        <thead><tr><th>Capability</th>{company_headers}</tr></thead>
        <tbody>{_feature_comparison_rows(comparison)}</tbody>
      </table>
    </section>
"""


def render_admin_page(
    state: RegistryState,
    run_status: ArgusRunStatus,
    demand_status: DemandImportStatus,
    ga4_status: Ga4ExportStatus,
    feature_matrix: list[FeatureMatrixAdminRecord],
    feature_comparison: FeatureComparisonState,
    recommendations: list[RecommendationAdminRecord],
    evidence_ledger: EvidenceLedgerState,
    evidence_work_queue: list[ArgusEvidenceWorkItem],
    product_muscle_work_queue: list[ProductMuscleWorkItem],
    product_surface_repair_history: dict[str, Any],
    demand_intake_history: dict[str, Any],
    operator_handoff: ArgusOperatorHandoff,
    data_plane_manifest: ArgusDataPlaneManifest,
    learning_apply_status: LearningApplyStatus,
) -> str:
    source_count = sum(len(c.sources) for c in state.competitors)
    surface_count = sum(len(c.product_surfaces) for c in state.competitors)
    improvement_count = len(state.improvements)
    recommendation_count = len(recommendations)
    failed_count = sum(
        1
        for c in state.competitors
        for s in c.sources
        if (s.latest_event_type or "") in {"fetch_error", "http_error", "timeout", "empty"}
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CI-OS Admin</title>
  <style>
    :root {{
      --ink: #10131a;
      --paper: #f7f8fa;
      --panel: #ffffff;
      --line: #d8dde8;
      --muted: #617084;
      --blue: #174cff;
      --green: #136f45;
      --amber: #9a6400;
      --red: #ad2e24;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: var(--ink); background: var(--paper); }}
    main {{ width: min(1440px, calc(100vw - 32px)); margin: 20px auto 40px; display: grid; gap: 18px; }}
    header {{ display: flex; justify-content: space-between; gap: 18px; align-items: end; border-bottom: 2px solid var(--ink); padding-bottom: 14px; }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 16px; }}
    .muted, td span {{ color: var(--muted); font-size: 12px; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .stat {{ border: 1px solid var(--line); background: var(--panel); padding: 10px 12px; min-width: 128px; }}
    .stat strong {{ display: block; font-size: 20px; }}
    section {{ border: 1px solid var(--line); background: var(--panel); padding: 14px; display: grid; gap: 12px; }}
    .run-console-grid {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, .8fr); gap: 16px; }}
    .ledger-grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
    .run-targets {{ margin: 0; padding-left: 18px; display: grid; gap: 8px; }}
    .run-targets li strong, .run-targets li span {{ display: block; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ text-align: left; border-top: 1px solid var(--line); padding: 10px 8px; vertical-align: top; font-size: 13px; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }}
    td strong, td span {{ display: block; }}
    form {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; align-items: end; }}
    form.inline {{ display: inline-grid; grid-template-columns: 1fr; gap: 0; margin-right: 4px; }}
    .source-form {{ grid-template-columns: 1.1fr .8fr 1.7fr 1fr .8fr 1fr; }}
    .action-cell {{ white-space: normal; }}
    .action-cell details {{ margin-top: 8px; min-width: 220px; }}
    .action-cell summary {{ color: var(--blue); cursor: pointer; font-size: 12px; font-weight: 700; }}
    .edit-form {{ display: grid; grid-template-columns: 1fr; gap: 6px; margin-top: 8px; }}
    .edit-form input, .edit-form select {{ min-height: 34px; }}
    label {{ display: grid; gap: 4px; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }}
    input, select {{ min-height: 42px; border: 1px solid var(--line); padding: 0 10px; font: inherit; background: #fff; }}
    textarea {{ min-height: 120px; border: 1px solid var(--line); padding: 10px; font: inherit; background: #fff; resize: vertical; }}
    form.inline input {{ display: none; }}
    button {{ min-height: 34px; border: 1px solid var(--ink); background: var(--ink); color: #fff; font: inherit; font-size: 12px; padding: 0 10px; cursor: pointer; }}
    td button {{ min-height: 30px; background: #fff; color: var(--ink); margin-right: 4px; }}
    .pill {{ display: inline-flex; min-height: 24px; align-items: center; border: 1px solid var(--line); padding: 0 8px; font-size: 11px; text-transform: uppercase; }}
    .pill.ok {{ color: var(--green); border-color: rgba(19,111,69,.35); }}
    .pill.warn {{ color: var(--amber); border-color: rgba(154,100,0,.35); }}
    .pill.bad {{ color: var(--red); border-color: rgba(173,46,36,.35); }}
    meter {{ width: 90px; height: 8px; display: block; margin-bottom: 6px; }}
    a {{ color: var(--blue); }}
    @media (max-width: 860px) {{
      header {{ display: grid; align-items: start; }}
      .run-console-grid {{ grid-template-columns: 1fr; }}
      form {{ grid-template-columns: 1fr; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      tr {{ border-top: 1px solid var(--line); padding: 8px 0; }}
      td {{ border-top: 0; padding: 6px 0; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>CI-OS Admin</h1>
        <div class="muted">Tenant: {_esc(state.tenant_slug)} · local-only registry control</div>
      </div>
      <div class="stats" aria-label="Registry summary">
        <div class="stat"><strong>{len(state.competitors)}</strong><span class="muted">competitors</span></div>
        <div class="stat"><strong>{source_count}</strong><span class="muted">sources</span></div>
        <div class="stat"><strong>{surface_count}</strong><span class="muted">product surfaces</span></div>
        <div class="stat"><strong>{improvement_count}</strong><span class="muted">open improvements</span></div>
        <div class="stat"><strong>{recommendation_count}</strong><span class="muted">open actions</span></div>
        <div class="stat"><strong>{failed_count}</strong><span class="muted">failed sources</span></div>
      </div>
    </header>

    {_run_console_section(run_status, operator_handoff, data_plane_manifest)}

    {_evidence_work_queue_section(evidence_work_queue)}

    {_product_muscle_work_queue_section(product_muscle_work_queue)}

    {_product_surface_repair_history_section(product_surface_repair_history)}

    {_learning_apply_section(learning_apply_status)}

    {_evidence_ledger_section(evidence_ledger)}

    {_recommendation_section(state, recommendations)}

    {_demand_intake_section(demand_intake_history, state.tenant_slug)}

    {_demand_import_section(demand_status, ga4_status)}

    {_feature_comparison_section(feature_comparison)}

    {_feature_matrix_section(feature_matrix)}

    <section>
      <h2>Add competitor</h2>
      <form method="post" action="/admin/{_esc(state.tenant_slug)}/competitors">
        <label>Name<input name="name" required /></label>
        <label>Domain<input name="domain" /></label>
        <label>Category<input name="category" /></label>
        <label>Priority<input name="priority" type="number" min="1" max="10" value="3" /></label>
        <button type="submit">Add competitor</button>
      </form>
    </section>

    <section>
      <h2>Competitors</h2>
      <table aria-label="Monitored competitors">
        <thead><tr><th>Name</th><th>Category</th><th>Priority</th><th>Status</th><th>Coverage</th><th>Actions</th></tr></thead>
        <tbody>{_competitor_rows(state)}</tbody>
      </table>
    </section>

    <section id="add-source">
      <h2>Sources</h2>
      <h3>Add source</h3>
      <form class="source-form" method="post" action="/admin/{_esc(state.tenant_slug)}/sources">
        <label>Competitor<select name="competitor_id" required>{_competitor_options(state)}</select></label>
        <label>Family<input name="source_family" required placeholder="blog" /></label>
        <label>URL<input name="url" type="url" required /></label>
        <label>Title<input name="title" /></label>
        <label>Status<select name="status"><option value="active">active</option><option value="candidate">candidate</option><option value="blocked">blocked</option><option value="needs_credentials">needs_credentials</option></select></label>
        <button type="submit">Add source</button>
      </form>
      <table aria-label="Source URLs">
        <thead><tr><th>Competitor</th><th>Family</th><th>URL</th><th>Status</th><th>Latest event</th><th>HTTP</th><th>Detail</th><th>Actions</th></tr></thead>
        <tbody>{_source_rows(state)}</tbody>
      </table>
    </section>

    <section id="add-product-surface">
      <h2>Product surfaces</h2>
      <h3>Add product surface</h3>
      <form class="source-form" method="post" action="/admin/{_esc(state.tenant_slug)}/product-surfaces">
        <label>Competitor<select name="competitor_id" required>{_competitor_options(state)}</select></label>
        <label>Family<select name="surface_family"><option value="docs">docs</option><option value="changelog">changelog</option><option value="release_notes">release_notes</option><option value="product_page">product_page</option><option value="pricing">pricing</option><option value="api_docs">api_docs</option><option value="integration">integration</option><option value="other">other</option></select></label>
        <label>URL<input name="url" type="url" required /></label>
        <label>Status<select name="status"><option value="active">active</option><option value="candidate">candidate</option><option value="paused">paused</option></select></label>
        <button type="submit">Add product surface</button>
      </form>
      <table aria-label="Product surfaces">
        <thead><tr><th>Competitor</th><th>Family</th><th>URL</th><th>Status</th><th>Last checked</th><th>Actions</th></tr></thead>
        <tbody>{_product_surface_rows(state)}</tbody>
      </table>
    </section>

    <section>
      <h2>Argus learning queue</h2>
      <div class="muted">Open improvements created from failed runs, quality reviews, false negatives, and recommendation challenges. Approving queues the work for a future gated apply path; it does not auto-change Hermes core.</div>
      <table aria-label="Argus learning queue">
        <thead><tr><th>Source</th><th>Problem</th><th>Proposed fix</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{_improvement_rows(state)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""
