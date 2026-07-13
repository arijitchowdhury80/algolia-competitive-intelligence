"""Typed boundaries for the CI-OS local admin app."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl

from cios.learn.recommendation_challenge import RecommendationChallengeCategory


class SourceAdminRecord(BaseModel):
    source_id: int
    source_family: str
    url: str
    status: str
    latest_event_type: Optional[str] = None
    http_status: Optional[int] = None
    detail: Optional[str] = None
    checked_at: Optional[datetime] = None


class ProductSurfaceAdminRecord(BaseModel):
    surface_id: int
    company_name: str
    company_role: str = "competitor"
    surface_family: str
    url: str
    status: str
    last_checked_at: Optional[datetime] = None


class CompetitorAdminRecord(BaseModel):
    competitor_id: int
    competitor_name: str
    domain: Optional[str] = None
    category: Optional[str] = None
    priority: int = 3
    status: str = "active"
    sources: list[SourceAdminRecord] = Field(default_factory=list)
    product_surfaces: list[ProductSurfaceAdminRecord] = Field(default_factory=list)


class ImprovementAdminRecord(BaseModel):
    improvement_id: int
    source: Optional[str] = None
    problem: str
    proposed_fix: Optional[str] = None
    priority: Optional[str] = None
    status: str = "open"
    created_at: Optional[datetime] = None


class RegistryState(BaseModel):
    tenant_slug: str
    tenant_id: int
    competitors: list[CompetitorAdminRecord] = Field(default_factory=list)
    improvements: list[ImprovementAdminRecord] = Field(default_factory=list)


class ArgusRunIntelligenceRecord(BaseModel):
    run_intelligence_id: int
    verdict: str
    top_insight: str
    primary_action: Optional[str] = None
    confidence_limits: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    product_event_count: int = 0
    conversation_theme_count: int = 0
    demand_signal_count: int = 0
    feature_position_count: int = 0
    pattern_count: int = 0
    recommendation_count: int = 0
    learning_instruction_count: int = 0
    learning_instruction_improvement_ids: list[int] = Field(default_factory=list)


class ArgusRunStatus(BaseModel):
    tenant_slug: str
    tenant_id: int
    report_id: Optional[int] = None
    report_date: Optional[date] = None
    cadence: Optional[str] = None
    report_status: Optional[str] = None
    generated_at: Optional[datetime] = None
    product_market_status: str = "not_recorded"
    demand_plane_status: str = "not_recorded"
    looker_discovered_count: int = 0
    looker_ready_count: int = 0
    looker_error_count: int = 0
    looker_normalized_row_count: int = 0
    looker_skipped_row_count: int = 0
    looker_archived_count: int = 0
    looker_manifest_path: Optional[str] = None
    next_sweep_plan_path: Optional[str] = None
    learning_apply_plan_path: Optional[str] = None
    learning_apply_plan_summary: dict[str, Any] = Field(default_factory=dict)
    product_surface_plan_summary: dict[str, Any] = Field(default_factory=dict)
    product_surface_execution_summary: dict[str, Any] = Field(default_factory=dict)
    runner_summary: dict[str, Any] = Field(default_factory=dict)
    ledger_refresh_status: str = "not_recorded"
    ledger_refresh_summary: dict[str, Any] = Field(default_factory=dict)
    latest_intelligence_brief: dict[str, Any] = Field(default_factory=dict)
    run_intelligence_history: list[ArgusRunIntelligenceRecord] = Field(default_factory=list)
    scout_paths: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LearningApplyProposalAdminRecord(BaseModel):
    action_id: str
    status: str
    target: str
    package_path: str
    proposal_path: str
    summary: str
    approved_by: Optional[str] = None
    evidence_event_ids: list[int] = Field(default_factory=list)
    source_improvement_ids: list[int] = Field(default_factory=list)


class LearningApplyPolicyAdminRecord(BaseModel):
    action_id: str
    status: str
    target: str
    package_path: str
    summary: str
    approved_by: Optional[str] = None
    evidence_event_ids: list[int] = Field(default_factory=list)
    source_improvement_ids: list[int] = Field(default_factory=list)


class LearningPolicyAuditPolicyAdminRecord(BaseModel):
    package_path: str
    action_id: str
    expected_action_id: Optional[str] = None
    target: str = ""
    tenant_id: Optional[int] = None
    approved_by: Optional[str] = None
    status: str


class LearningPolicyAuditIssueAdminRecord(BaseModel):
    code: str
    package_path: str
    action_id: Optional[str] = None
    expected_action_id: Optional[str] = None
    target: Optional[str] = None
    message: str
    rollback_hint: str


class LearningPolicyAuditStatus(BaseModel):
    package_root: str = ""
    tenant_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    passed: bool = True
    policy_count: int = 0
    ok_count: int = 0
    drift_count: int = 0
    invalid_count: int = 0
    issue_count: int = 0
    policies: list[LearningPolicyAuditPolicyAdminRecord] = Field(default_factory=list)
    issues: list[LearningPolicyAuditIssueAdminRecord] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)


class LearningApplyStatus(BaseModel):
    tenant_slug: str
    tenant_id: int
    proposal_dir: str
    config_dir: str
    proposal_count: int = 0
    approved_policy_count: int = 0
    proposals: list[LearningApplyProposalAdminRecord] = Field(default_factory=list)
    approved_policies: list[LearningApplyPolicyAdminRecord] = Field(default_factory=list)
    policy_audit: LearningPolicyAuditStatus = Field(default_factory=LearningPolicyAuditStatus)


class LearningApplyExecuteRequest(BaseModel):
    approved_by: Optional[str] = Field(default=None, max_length=120)


class DemandImportFile(BaseModel):
    name: str
    path: str
    size_bytes: int = 0
    modified_at: Optional[datetime] = None


class DemandImportPreview(BaseModel):
    name: str
    path: str
    status: str
    raw_row_count: int = 0
    normalized_row_count: int = 0
    skipped_row_count: int = 0
    topics: list[str] = Field(default_factory=list)
    demand_plan_coverage: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class DemandImportStatus(BaseModel):
    tenant_slug: str
    drop_folder: str
    manifest_path: str
    manifest_exists: bool = False
    discovered_count: int = 0
    ready_count: int = 0
    error_count: int = 0
    normalized_row_count: int = 0
    skipped_row_count: int = 0
    manifest: dict[str, Any] = Field(default_factory=dict)
    inbox_files: list[DemandImportFile] = Field(default_factory=list)
    inbox_previews: list[DemandImportPreview] = Field(default_factory=list)
    archived_files: list[DemandImportFile] = Field(default_factory=list)
    rejected_files: list[DemandImportFile] = Field(default_factory=list)
    accepted_suffixes: list[str] = Field(default_factory=list)


class DemandImportCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)


class DemandImportUploadResult(BaseModel):
    name: str
    path: str
    size_bytes: int = 0
    status: str = "queued_for_next_sweep"
    preview_status: str = "not_evaluated"
    raw_row_count: int = 0
    normalized_row_count: int = 0
    skipped_row_count: int = 0
    topics: list[str] = Field(default_factory=list)
    demand_plan_coverage: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class DemandImportPrepareResult(BaseModel):
    tenant_slug: str
    manifest_path: str
    discovered_count: int = 0
    ready_count: int = 0
    error_count: int = 0
    normalized_row_count: int = 0
    skipped_row_count: int = 0
    raw_paths: list[str] = Field(default_factory=list)
    payload_paths: list[str] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)
    status: str = "prepared_for_next_sweep"


class DemandImportLedgerPersistResult(BaseModel):
    tenant_id: int
    status: str = "persisted"
    demand_signal_count: int = 0
    saved_ids: list[int] = Field(default_factory=list)
    payload_paths: list[str] = Field(default_factory=list)


class Ga4ExportStatus(BaseModel):
    tenant_slug: str
    enabled: bool = False
    ready: bool = False
    status: str = "disabled"
    missing_required: list[str] = Field(default_factory=list)
    setup_required: list[str] = Field(default_factory=list)
    property_configured: bool = False
    credentials_configured: bool = False
    credentials_path_exists: bool = False
    application_default_credentials_configured: bool = False
    script_path_exists: bool = False
    current_start: Optional[str] = None
    current_end: Optional[str] = None
    previous_start: Optional[str] = None
    previous_end: Optional[str] = None
    topic_dimension: str = "pageTitle"
    url_dimension: Optional[str] = "pagePath"
    metric: str = "engagedSessions"
    limit: int = 1000
    source_url_configured: bool = False
    output_path: str
    message: str


class Ga4ExportRunResult(BaseModel):
    tenant_slug: str
    status: str = "exported"
    output_path: str
    record_count: int = 0
    credentials_configured: bool = False
    demand_plan_path: Optional[str] = None
    demand_plan_status: Optional[str] = None
    demand_plan_topic_count: int = 0
    matched_plan_topic_count: int = 0
    off_plan_record_count: int = 0
    command_status: str = "ok"
    message: str = "GA4 export completed."


class FeatureMatrixAdminRecord(BaseModel):
    capability_text: str
    company_name: str
    company_role: str
    position_status: str
    summary: Optional[str] = None
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class FeatureComparisonCompany(BaseModel):
    company_name: str
    company_role: str = "competitor"
    status: str = "active"


class FeatureComparisonCell(BaseModel):
    company_name: str
    company_role: str = "competitor"
    position_status: str = "unknown"
    summary: str
    confidence: Optional[float] = None
    evidence_count: int = 0
    first_evidence_url: Optional[str] = None
    updated_at: Optional[datetime] = None


class FeatureComparisonRow(BaseModel):
    capability_text: str
    planned_by_argus: bool = False
    cells: list[FeatureComparisonCell] = Field(default_factory=list)
    proven_count: int = 0
    claimed_count: int = 0
    gap_count: int = 0
    disproven_count: int = 0
    unknown_count: int = 0
    evidence_count: int = 0


class FeatureComparisonState(BaseModel):
    tenant_slug: str
    tenant_id: int
    companies: list[FeatureComparisonCompany] = Field(default_factory=list)
    rows: list[FeatureComparisonRow] = Field(default_factory=list)


class RecommendationAdminRecord(BaseModel):
    recommendation_id: int
    pattern_observation_id: Optional[int] = None
    owner: str
    action: str
    why_now: str
    urgency: str
    confidence: Optional[float] = None
    scorecard: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "open"
    created_at: Optional[datetime] = None


class ProductEventAdminRecord(BaseModel):
    product_event_id: int
    company_name: str
    company_role: str
    capability_text: str
    change_type: str
    summary: str
    observed_at: Optional[datetime] = None
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ConversationThemeAdminRecord(BaseModel):
    conversation_theme_id: int
    company_name: Optional[str] = None
    theme: str
    summary: str
    intensity: Optional[float] = None
    observed_at: Optional[datetime] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class DemandSignalAdminRecord(BaseModel):
    demand_signal_id: int
    topic: str
    metric: str
    value: float
    change_pct: Optional[float] = None
    period_start: datetime
    period_end: datetime
    source_label: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatternObservationAdminRecord(BaseModel):
    pattern_observation_id: int
    pattern_type: str
    capability_text: str
    summary: str
    involved_companies: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class EvidenceLedgerState(BaseModel):
    tenant_slug: str
    tenant_id: int
    product_events: list[ProductEventAdminRecord] = Field(default_factory=list)
    conversation_themes: list[ConversationThemeAdminRecord] = Field(default_factory=list)
    demand_signals: list[DemandSignalAdminRecord] = Field(default_factory=list)
    patterns: list[PatternObservationAdminRecord] = Field(default_factory=list)


class ArgusEvidenceWorkItem(BaseModel):
    work_item_id: str
    evidence_plane: str
    status: str = "open"
    severity: str
    title: str
    why_needed: str
    blocks: list[str] = Field(default_factory=list)
    next_step: str
    operator_surface: str
    primary_action_label: str
    primary_action_href: str
    primary_action_method: str = "get"
    secondary_action_label: Optional[str] = None
    secondary_action_href: Optional[str] = None
    secondary_action_method: Optional[str] = None
    accepted_input_formats: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    observed_state: dict[str, Any] = Field(default_factory=dict)
    related_run_intelligence_id: Optional[int] = None
    observed_pattern_count: int = 0


class ProductMuscleWorkItem(BaseModel):
    work_item_id: str
    company_id: Optional[int] = None
    company_name: str
    company_role: str = "competitor"
    capability_text: Optional[str] = None
    status: str = "open"
    severity: str
    title: str
    why_needed: str
    blocks: list[str] = Field(default_factory=list)
    next_step: str
    operator_surface: str = "Product surfaces"
    primary_action_label: str
    primary_action_href: str
    primary_action_method: str = "get"
    secondary_action_label: Optional[str] = None
    secondary_action_href: Optional[str] = None
    secondary_action_method: Optional[str] = None
    observed_state: dict[str, Any] = Field(default_factory=dict)


class ProductSurfaceRepairRequest(BaseModel):
    company_name: Optional[str] = None
    company_id: Optional[int] = None
    surface_id: Optional[int] = None
    category: Optional[str] = None
    use_js: bool = True
    repair_timeout_seconds: float = 240
    command_timeout_seconds: float = 300
    limit: int = 1


class ProductSurfaceExtractionRequest(BaseModel):
    company_name: Optional[str] = None
    focus_capability: Optional[str] = None
    company_id: Optional[int] = None
    surface_id: Optional[int] = None
    use_js: bool = True
    timeout_seconds: float = 160
    command_timeout_seconds: float = 220
    max_workers: int = 1
    limit: int = 1


class ProductSurfaceCandidatePromotionRequest(BaseModel):
    company_name: Optional[str] = None
    company_id: Optional[int] = None
    surface_family: Optional[str] = None
    discovery_source: str = "product_muscle_gap_plan"
    promoted_by: str = "argus"
    limit: int = 1


class ArgusDataPlane(BaseModel):
    status: str
    summary: str
    blocks_action: bool = False
    storage: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    next_hermes_action: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class ArgusDataPlaneManifest(BaseModel):
    schema_version: int = 1
    tenant_slug: str
    generated_at: Optional[str] = None
    dashboard_generated_at: Optional[str] = None
    status: str
    argus_readiness: str
    next_hermes_action: str
    source_of_truth: dict[str, str] = Field(default_factory=dict)
    artifact_refs: dict[str, Optional[str]] = Field(default_factory=dict)
    planes: dict[str, ArgusDataPlane] = Field(default_factory=dict)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)
    artifact_path: Optional[str] = None
    artifact_found: bool = False


class ArgusOperatorCommand(BaseModel):
    label: str
    href: str
    method: str = "get"
    surface: Optional[str] = None


class ArgusOperatorHandoff(BaseModel):
    tenant_slug: str
    tenant_id: Optional[int] = None
    generated_at: Optional[str] = None
    status: str
    argus_readiness: str
    summary: str
    next_operator_action: str
    top_blocker: Optional[dict[str, Any]] = None
    primary_command: Optional[ArgusOperatorCommand] = None
    secondary_command: Optional[ArgusOperatorCommand] = None
    operator_brief: list[str] = Field(default_factory=list)
    demand_collection_plan: dict[str, Any] = Field(default_factory=dict)
    demand_plan_template: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: dict[str, Optional[str]] = Field(default_factory=dict)
    work_queue: dict[str, Any] = Field(default_factory=dict)
    artifact_path: Optional[str] = None
    artifact_found: bool = False


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    domain: Optional[str] = Field(default=None, max_length=240)
    category: Optional[str] = Field(default=None, max_length=160)
    priority: int = Field(default=3, ge=1, le=10)


class CompetitorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=180)
    domain: Optional[str] = Field(default=None, max_length=240)
    category: Optional[str] = Field(default=None, max_length=160)
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    status: Optional[str] = None


class CompetitorStatusUpdate(BaseModel):
    status: str


class SourceCreate(BaseModel):
    source_family: str = Field(min_length=1, max_length=80)
    url: HttpUrl
    title: Optional[str] = Field(default=None, max_length=240)
    status: str = "active"


class SourceUpdate(BaseModel):
    source_family: Optional[str] = Field(default=None, min_length=1, max_length=80)
    url: Optional[HttpUrl] = None
    title: Optional[str] = Field(default=None, max_length=240)
    status: Optional[str] = None


class SourceStatusUpdate(BaseModel):
    status: str


class ProductSurfaceCreate(BaseModel):
    surface_family: str = Field(min_length=1, max_length=80)
    url: HttpUrl
    status: str = "active"


class ProductSurfaceUpdate(BaseModel):
    surface_family: Optional[str] = Field(default=None, min_length=1, max_length=80)
    url: Optional[HttpUrl] = None
    status: Optional[str] = None


class ProductSurfaceStatusUpdate(BaseModel):
    status: str


class ImprovementStatusUpdate(BaseModel):
    status: str


class RecommendationStatusUpdate(BaseModel):
    status: str


class RecommendationChallengeCreate(BaseModel):
    challenge: str = Field(min_length=1, max_length=4000)
    category: RecommendationChallengeCategory
    run_id: Optional[str] = Field(default=None, max_length=180)
    scorecard_dimension: Optional[str] = Field(default=None, max_length=120)


class RecommendationChallengeResponse(BaseModel):
    learning_event_id: int
    improvement_id: Optional[int] = None
    next_sweep_instruction: Optional[str] = None
