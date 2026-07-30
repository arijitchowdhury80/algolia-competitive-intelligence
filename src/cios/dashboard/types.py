"""Shared data types for the CI-OS dashboard data/state layer (Gate 5).

Mirrors dashboard_state + the tables the UX spec's "Dashboard Data Contract"
names as the render source (docs/planning/CI-OS-dashboard-app-UX-spec.md
"Dashboard Data Contract"): dashboard_state, semantic_deltas, raw_findings,
source_health_events, action_items, bot_deliveries, content_recommendations,
weekly_content_plan, quality_reviews, false_negative_audits.

Doctrine enforced by these types (CI-OS-Fable-build-goal-spec.md Gate 5
acceptance: "dashboard updates automatically from DB; no green quiet unless
all lanes ran"):
  - coverage-before-quiet: DashboardState.is_quiet is only ever True when
    CoverageBarometer.all_lanes_ran AND the false-negative audit is clean.
    A dashboard can look empty; it can never claim to be verified-quiet
    without earning it.
  - materiality-before-urgency: competitor_cards are always materiality-
    ranked (highest attention_score first); the builder is the only place
    that ranking happens, so every consumer (JSON publisher, tests) sees the
    same order.
  - decision-layer-not-feed: every CompetitorSignalCard carries an
    action_cue (per UX spec Attention Barometer rule: "watch" / "monitor"
    rows must say what to watch or monitor, not just show a bare score).

This module has no DB or network access. The caller's injected repositories
(state_builder.py) map Postgres rows onto these value objects.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

# Schema version for the published JSON contract (publisher.py). Bump this
# whenever the shape of dashboard-state.v{N}.json changes in a
# backward-incompatible way.
DASHBOARD_STATE_SCHEMA_VERSION = 26


class AttentionLevel(str, Enum):
    """Discrete, labeled Attention Barometer color states (UX spec: "Color
    states are discrete and labeled: green normal, blue monitor, amber watch,
    red act now")."""

    NORMAL = "normal"
    MONITOR = "monitor"
    WATCH = "watch"
    ACT_NOW = "act_now"


# Materiality-score thresholds mapping a competitor's top signal into an
# AttentionLevel. Ranges are inclusive of the lower bound. Kept as named
# constants (not a magic literal in the builder) so the UX spec's four
# discrete states stay reviewable independent of the code that applies them.
ATTENTION_THRESHOLD_ACT_NOW = 0.75
ATTENTION_THRESHOLD_WATCH = 0.5
ATTENTION_THRESHOLD_MONITOR = 0.25


def attention_level_for_score(score: float) -> AttentionLevel:
    if score >= ATTENTION_THRESHOLD_ACT_NOW:
        return AttentionLevel.ACT_NOW
    if score >= ATTENTION_THRESHOLD_WATCH:
        return AttentionLevel.WATCH
    if score >= ATTENTION_THRESHOLD_MONITOR:
        return AttentionLevel.MONITOR
    return AttentionLevel.NORMAL


class LaneStatus(BaseModel):
    """Did one required collection lane run cleanly this cycle? Mirrors
    cios.brain.types.LaneStatus -- redeclared here so this package has no
    import dependency on the brain package (dashboard is a pure read/render
    layer over already-synthesized state)."""

    lane: str
    ran: bool
    error: Optional[str] = None


class CoverageBarometer(BaseModel):
    """Coverage-before-quiet proof block. This is the ONLY place the
    no-green-quiet invariant is computed; DashboardState.is_quiet reads it,
    never recomputes it."""

    lanes: list[LaneStatus] = Field(default_factory=list)
    coverage_score: Optional[float] = None
    false_negative_audit_status: Optional[str] = None  # false_negative_audits.audit_status
    missing_source_families: list[str] = Field(default_factory=list)

    @property
    def all_lanes_ran(self) -> bool:
        return bool(self.lanes) and all(l.ran and l.error is None for l in self.lanes)

    @property
    def failed_lanes(self) -> list[str]:
        return [l.lane for l in self.lanes if not l.ran or l.error is not None]

    @property
    def is_quiet_eligible(self) -> bool:
        """Coverage alone earns the right to call a run quiet. Does NOT
        consider whether any signals exist -- that's DashboardState.is_quiet."""
        return self.all_lanes_ran and self.false_negative_audit_status == "clean"


class CompetitorSignalCard(BaseModel):
    """One Attention Barometer row (UX spec Screen 2). Cards are always
    emitted in materiality-ranked order by the state builder."""

    competitor_id: int
    competitor_name: str
    attention_score: float  # 0-100, "attention needed this week"
    attention_level: AttentionLevel
    action_cue: str  # what to watch/monitor/act on -- never a bare score
    top_signal_headline: Optional[str] = None
    what_changed: Optional[str] = None
    why_it_matters: Optional[str] = None
    recommended_action: Optional[str] = None
    materiality_score: Optional[float] = None
    confidence: Optional[float] = None
    evidence_ids: list[Any] = Field(default_factory=list)
    brief_href: Optional[str] = None
    delta_id: Optional[int] = None
    thesis_id: Optional[int] = None
    # How many near-duplicate deltas (same competitor, same underlying
    # story) were merged into this one card -- see cios.common.dedup. 1
    # means no merge happened. Rendered as a "seen in N sources" badge.
    duplicate_count: int = 1


class LivingThesis(BaseModel):
    """Mirrors competitor_theses. Non-destructive: status transitions, never
    deleted."""

    thesis_id: int
    competitor_id: int
    competitor_name: Optional[str] = None
    thesis: str
    status: str  # active | confirmed | weakened | retired
    confidence: Optional[float] = None
    supporting_delta_count: int = 0
    contradicting_delta_count: int = 0
    updated_at: Optional[datetime] = None


class ArgusRead(BaseModel):
    """The hero structure the UX spec mandates for "Argus current read"
    (Screen 2): useful truth first, what changed, why it matters, what not
    to over-believe, recommended move, confidence."""

    useful_truth: Optional[str] = None
    what_changed: Optional[str] = None
    why_it_matters: Optional[str] = None
    what_not_to_overbelieve: Optional[str] = None
    recommended_move: Optional[str] = None
    confidence: Optional[float] = None


class RunHealth(BaseModel):
    """Trust bar data (UX spec Screen 2: "data freshness, source coverage,
    delivery status, model tier")."""

    run_id: Optional[str] = None
    report_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    model_tier: Optional[str] = None
    source_family_count: Optional[int] = None
    current_material_delta_count: int = 0
    rolling_material_delta_count: int = 0
    material_delta_count: int = 0
    delivery_status: Optional[str] = None
    quality_review_status: Optional[str] = None


class ProductMarketRunStatus(BaseModel):
    """Execution trace for the product-market muscle chain.

    This is not strategic insight by itself. It is the proof strip that tells a
    dashboard reader whether Hermes ran the CI-OS product-market package and
    what Argus prioritized before drawing conclusions.
    """

    status: str = "not_recorded"
    next_sweep_plan_path: Optional[str] = None
    learning_apply_plan_path: Optional[str] = None
    learning_apply_plan_summary: dict[str, Any] = Field(default_factory=dict)
    target_count: int = 0
    target_company_count: int = 0
    target_companies: list[str] = Field(default_factory=list)
    surface_family_counts: dict[str, int] = Field(default_factory=dict)
    product_surface_execution_summary: dict[str, Any] = Field(default_factory=dict)
    product_muscle_gap_plan: dict[str, Any] = Field(default_factory=dict)
    post_run_product_muscle_gap_discovery: dict[str, Any] = Field(default_factory=dict)
    post_run_product_surface_promotion: dict[str, Any] = Field(default_factory=dict)
    post_run_next_sweep_status: Optional[str] = None
    learning_prioritized_count: int = 0
    prioritized_targets: list[dict[str, Any]] = Field(default_factory=list)
    runner_verdict: Optional[str] = None
    product_event_count: int = 0
    conversation_theme_count: int = 0
    demand_signal_count: int = 0
    pattern_count: int = 0
    recommendation_count: int = 0
    learning_instruction_count: int = 0
    consumed_learning_ids: list[int] = Field(default_factory=list)
    scout_artifact_count: int = 0
    demand_plane_status: str = "not_recorded"
    demand_readiness: dict[str, Any] = Field(default_factory=dict)
    looker_discovered_count: int = 0
    looker_ready_count: int = 0
    looker_error_count: int = 0
    looker_normalized_row_count: int = 0
    looker_skipped_row_count: int = 0
    looker_archived_count: int = 0
    looker_manifest_path: Optional[str] = None
    intelligence_brief: dict[str, Any] = Field(default_factory=dict)
    decision_read: dict[str, Any] = Field(default_factory=dict)
    next_monitoring_actions: list[dict[str, Any]] = Field(default_factory=list)
    movement_map: dict[str, Any] = Field(default_factory=dict)
    product_feature_comparison_read: dict[str, Any] = Field(default_factory=dict)
    window_comparison: dict[str, Any] = Field(default_factory=dict)
    conversion_diagnostics: dict[str, Any] = Field(default_factory=dict)
    stage_ledger: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _promote_movement_map_from_brief(self) -> "ProductMarketRunStatus":
        if self.movement_map:
            return self
        movement_map = self.intelligence_brief.get("movement_map")
        if isinstance(movement_map, dict):
            self.movement_map = dict(movement_map)
        return self

    @model_validator(mode="after")
    def _promote_decision_read_from_brief(self) -> "ProductMarketRunStatus":
        if self.decision_read:
            return self
        decision_read = self.intelligence_brief.get("decision_read")
        if isinstance(decision_read, dict):
            self.decision_read = dict(decision_read)
        return self

    @model_validator(mode="after")
    def _promote_next_monitoring_actions_from_brief(self) -> "ProductMarketRunStatus":
        if self.next_monitoring_actions:
            return self
        actions = self.intelligence_brief.get("next_monitoring_actions")
        if isinstance(actions, list):
            self.next_monitoring_actions = [
                dict(action)
                for action in actions
                if isinstance(action, dict)
            ]
        return self

    @model_validator(mode="after")
    def _promote_product_feature_comparison_from_brief(self) -> "ProductMarketRunStatus":
        if self.product_feature_comparison_read:
            return self
        comparison = self.intelligence_brief.get("product_feature_comparison")
        if isinstance(comparison, dict):
            self.product_feature_comparison_read = dict(comparison)
        return self

    @model_validator(mode="after")
    def _promote_conversion_diagnostics_from_brief(self) -> "ProductMarketRunStatus":
        if self.conversion_diagnostics:
            return self
        diagnostics = self.intelligence_brief.get("conversion_diagnostics")
        if isinstance(diagnostics, dict):
            self.conversion_diagnostics = dict(diagnostics)
        return self

    @model_validator(mode="after")
    def _promote_window_comparison_from_brief(self) -> "ProductMarketRunStatus":
        if self.window_comparison:
            return self
        comparison = self.intelligence_brief.get("window_comparison")
        if isinstance(comparison, dict):
            self.window_comparison = dict(comparison)
        return self


class ServiceHealth(BaseModel):
    name: str
    status: str  # ok | degraded | down | unknown
    detail: Optional[str] = None
    checked_at: Optional[datetime] = None


class ReportHistoryEntry(BaseModel):
    """One row of the "Report history" archive panel (Arijit's original
    layout). Sourced from the `reports` table (migrated V0 history + new V2
    runs) -- see PgReportHistoryRepository in cios/db/repos/dashboard.py.

    `status` is `reports.status` (draft | rendered | delivered) verbatim.
    There is no FK from quality_reviews to reports in schema.sql (
    quality_reviews is keyed by a free-text run_id, not report_id), so this
    is deliberately the report's own lifecycle status, not a fabricated
    "quality status" join -- truthful source over an invented-looking metric.
    """

    report_id: int
    report_date: date
    cadence: str
    title: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    html_path: Optional[str] = None


class SuppressedSignalEntry(BaseModel):
    """One row of the "Suppressed Signals" trust-diagnostics panel (Arijit's
    original layout). Sourced from `suppressed_diagnostics` -- the dedicated
    audit-trail table for findings intentionally kept out of the executive
    view because they did not pass semantic materiality gates."""

    suppressed_id: int
    reason: str
    finding_count: int
    suppressed_at: Optional[datetime] = None
    notes: Optional[str] = None


class BuildStatus(BaseModel):
    """System/build status section (Arijit's explicit requirement: system
    status must be visible ON the dashboard, not only in chat). Not tenant
    intelligence -- operational self-reporting of the CI-OS deployment that
    produced this DashboardState."""

    build_id: Optional[str] = None
    git_sha: Optional[str] = None
    deployed_at: Optional[datetime] = None
    environment: Optional[str] = None  # e.g. "hermes-prod", "local"
    services: list[ServiceHealth] = Field(default_factory=list)
    last_error: Optional[str] = None

    @property
    def all_services_ok(self) -> bool:
        return bool(self.services) and all(s.status == "ok" for s in self.services)


class PrescriptionSummary(BaseModel):
    """One prescribed play, as the cockpit's role lenses need it. Mirrors
    cios.prescribe.types.Prescription (title, team, play, urgency_window,
    expected_effect, grounding.evidence_urls) -- redeclared here (same
    convention as LaneStatus mirroring cios.brain.types.LaneStatus) so
    dashboard stays a pure read/render layer with no import dependency on
    the prescribe package."""

    title: str
    team: str  # cios.prescribe.types.Team value, e.g. "Marketing", "Sales Enablement"
    play: list[str] = Field(default_factory=list)
    urgency_window: str  # act_now | this_week | this_month
    expected_effect: Optional[str] = None
    evidence_urls: list[str] = Field(default_factory=list)
    effort: Optional[str] = None  # cios.prescribe.types.Effort value: S | M | L
    materiality_score: Optional[float] = None
    # Competitor attribution for the cockpit's barometer-row-filters-lenses
    # interaction (2026-07 findings fix). Prescriptions carry no
    # competitor_id of their own (cios.prescribe.types.Prescription is
    # tenant-scoped, not competitor-scoped) -- the state builder derives
    # this by tracing the prescription's own grounding evidence URLs back
    # to whichever competitor's material-delta evidence cites the same
    # URL. None when no match is found (honest "unattributed", never
    # guessed): such plays are only visible in the "All competitors"
    # default view, never claimed for a specific competitor filter.
    competitor_id: Optional[int] = None
    competitor_name: Optional[str] = None


class MonitoredCompetitor(BaseModel):
    """One row in the full competitor registry. This is intentionally
    separate from CompetitorSignalCard: the barometer shows material signals;
    this shows the monitored universe, including quiet competitors."""

    competitor_id: int
    competitor_name: str
    domain: Optional[str] = None
    category: Optional[str] = None
    status: str = "active"
    source_count: int = 0
    active_source_count: int = 0
    failed_source_count: int = 0
    last_checked_at: Optional[datetime] = None
    checked_today: bool = False
    material_signal_count: int = 0
    last_material_signal_at: Optional[datetime] = None
    latest_movement_summary: Optional[str] = None
    brief_href: Optional[str] = None
    monitored_sources: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def signal_status(self) -> str:
        if self.material_signal_count > 0:
            return "material_signal"
        if self.checked_today:
            return "no_material_signal"
        if self.last_checked_at is None:
            return "pending_first_sweep"
        return "no_material_signal"


class SourceHealthEntry(BaseModel):
    """Latest source-health state behind the registry."""

    source_id: int
    competitor_id: int
    competitor_name: str
    source_family: str
    url: str
    status: str
    latest_event_type: Optional[str] = None
    http_status: Optional[int] = None
    detail: Optional[str] = None
    checked_at: Optional[datetime] = None


class ProductMarketPatternSummary(BaseModel):
    """One product-market pattern Argus found by fusing product reality,
    market conversation, and demand signals."""

    pattern_id: int
    pattern_type: str
    capability_text: str
    summary: str
    involved_companies: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketHistoryEntry(BaseModel):
    """One historical product-market pattern from Argus memory.

    This is distinct from report_history: report_history proves that a brief
    was published; product_market_history proves what pattern Argus observed
    over time and which evidence supported it.
    """

    pattern_id: int
    observed_at: datetime
    pattern_type: str
    capability_text: str
    summary: str
    involved_companies: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketRunHistoryEntry(BaseModel):
    """One durable Argus run read from product_market_run_intelligence.

    Pattern history says what market patterns were observed. Run history says
    what Argus concluded for a sweep, what action it promoted or withheld, and
    which learning gates influenced the read.
    """

    run_intelligence_id: int
    observed_at: datetime
    verdict: str
    top_insight: str
    intelligence_brief: dict[str, Any] = Field(default_factory=dict)
    argus_packet: dict[str, Any] = Field(default_factory=dict)
    primary_action: Optional[str] = None
    watchlist: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    product_event_count: int = 0
    conversation_theme_count: int = 0
    demand_signal_count: int = 0
    pattern_count: int = 0
    recommendation_count: int = 0
    learning_instruction_count: int = 0
    learning_instruction_improvement_ids: list[int] = Field(default_factory=list)


class ProductMarketTrendSummary(BaseModel):
    """Derived trend over recent product-market pattern memory."""

    capability_text: str
    direction: str
    pattern_count_7d: int = 0
    pattern_count_30d: int = 0
    involved_companies: list[str] = Field(default_factory=list)
    latest_summary: str
    latest_observed_at: datetime
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketHeatmapCell(BaseModel):
    """One entity x capability heat cell derived from pattern memory."""

    entity_name: str
    capability_text: str
    heat_level: str
    intensity_score: float
    pattern_count_7d: int = 0
    pattern_count_30d: int = 0
    latest_summary: str
    latest_observed_at: datetime
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketEntityVelocitySummary(BaseModel):
    """One entity-level movement summary derived from product-market heat."""

    entity_name: str
    direction: str
    total_patterns_7d: int = 0
    total_patterns_30d: int = 0
    hot_capability_count: int = 0
    warm_capability_count: int = 0
    top_capabilities: list[str] = Field(default_factory=list)
    latest_summary: str
    latest_observed_at: datetime
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketThemeHeatmapCell(BaseModel):
    """One strategic theme heat cell derived from pattern memory."""

    theme_text: str
    heat_level: str
    direction: str
    intensity_score: float
    pattern_count_7d: int = 0
    pattern_count_30d: int = 0
    entity_count: int = 0
    leading_entities: list[str] = Field(default_factory=list)
    pattern_types: list[str] = Field(default_factory=list)
    latest_summary: str
    latest_observed_at: datetime
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketWindowDeltaSummary(BaseModel):
    """Current-window versus prior-window product-market movement."""

    subject_type: str
    subject_name: str
    direction: str
    current_window_label: str = "last_7d"
    previous_window_label: str = "prior_7d"
    current_pattern_count: int = 0
    previous_pattern_count: int = 0
    delta: int = 0
    related_entities: list[str] = Field(default_factory=list)
    related_capabilities: list[str] = Field(default_factory=list)
    latest_summary: str
    latest_observed_at: datetime
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ArgusRubricDimension(BaseModel):
    """One backend scoring dimension behind an Argus recommendation."""

    dimension: str
    score: int
    max_score: int
    rationale: str
    evidence_urls: list[str] = Field(default_factory=list)


class ArgusRecommendationScorecard(BaseModel):
    """Published recommendation rubric saved by the product-market brain."""

    total_score: int
    verdict: str
    summary: str
    dimension_scores: list[ArgusRubricDimension] = Field(default_factory=list)


class ArgusRecommendationSummary(BaseModel):
    """One owner-specific recommendation promoted by the product-market
    intelligence spine."""

    recommendation_id: int
    pattern_observation_id: Optional[int] = None
    owner: str
    action: str
    why_now: str
    urgency: str
    confidence: Optional[float] = None
    scorecard: Optional[ArgusRecommendationScorecard] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "open"


class DemandSignalSummary(BaseModel):
    """One tenant-side demand signal from GA / Looker Studio or an equivalent
    analytics export."""

    demand_signal_id: int
    topic: str
    metric: str
    value: float
    change_pct: Optional[float] = None
    source_label: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    argus_plan_context: dict[str, Any] = Field(default_factory=dict)


class DemandFeatureAlignmentCompany(BaseModel):
    """One company with product proof on a demand-matched capability."""

    company_name: str
    company_role: str = "competitor"
    position_status: str = "unknown"
    evidence_count: int = 0
    first_evidence_url: Optional[str] = None


class DemandFeatureAlignmentRow(BaseModel):
    """One demand topic mapped, or explicitly not mapped, to product proof.

    This is the dashboard contract for the inward-facing part of Argus:
    audience demand is only useful when it can be tied to product reality or
    called out as a taxonomy/product-proof gap.
    """

    demand_signal_id: int
    topic: str
    metric: str
    value: float
    change_pct: Optional[float] = None
    source_label: str
    demand_evidence_url: Optional[str] = None
    match_status: str = "unmatched"
    matched_capability: Optional[str] = None
    related_companies: list[DemandFeatureAlignmentCompany] = Field(default_factory=list)
    product_evidence_count: int = 0
    summary: str
    next_step: str


class DemandFeatureAlignmentState(BaseModel):
    """Inward demand aligned to the product muscle matrix.

    Status values:
      - no_current_demand: no demand rows were published with the run.
      - matched: every demand topic mapped to at least one product capability.
      - partially_matched: some demand topics mapped and some did not.
      - unmatched: demand exists, but none maps to captured product proof.
    """

    status: str = "no_current_demand"
    rows: list[DemandFeatureAlignmentRow] = Field(default_factory=list)
    signal_count_total: int = 0
    matched_signal_count: int = 0
    unmatched_signal_count: int = 0


class ArgusEvidenceNeedSummary(BaseModel):
    """One explicit evidence gap that blocks or limits Argus action.

    This prevents the dashboard from looking empty when the intelligence brain
    deliberately withholds recommendations. Absence of action must explain
    which evidence plane is missing and what unlocks the next decision.
    """

    evidence_plane: str
    status: str
    severity: str
    title: str
    why_needed: str
    blocks: list[str] = Field(default_factory=list)
    next_step: str
    related_run_intelligence_id: Optional[int] = None
    observed_pattern_count: int = 0
    accepted_input_formats: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    operator_surface: Optional[str] = None
    observed_state: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class FeatureMatrixRow(BaseModel):
    """One cell/row in the Product Muscle Matrix."""

    capability_text: str
    company_name: str
    company_role: str
    position_status: str
    summary: Optional[str] = None
    confidence: Optional[float] = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ProductFeatureComparisonCompany(BaseModel):
    """One company column in the public product/feature comparison.

    This is deliberately compact and evidence-limited. It is not a full admin
    registry row; it is the public dashboard's answer to "who has product
    proof on this capability, and who is still unknown in this evidence set?"
    """

    company_name: str
    company_role: str = "competitor"
    active_source_count: int = 0
    has_product_evidence: bool = False


class ProductFeatureComparisonCell(BaseModel):
    """One company-by-capability evidence cell."""

    company_name: str
    position_status: str = "unknown"
    summary: str
    confidence: Optional[float] = None
    evidence_count: int = 0
    first_evidence_url: Optional[str] = None


class ProductFeatureComparisonRow(BaseModel):
    """One capability row across the selected comparison companies."""

    capability_text: str
    cells: list[ProductFeatureComparisonCell] = Field(default_factory=list)
    proven_count: int = 0
    claimed_count: int = 0
    unknown_count: int = 0
    evidence_count: int = 0


class ProductFeatureComparisonState(BaseModel):
    """Public, compact product muscle matrix for the cockpit.

    Admin can own the full registry and all feature positions. The public
    dashboard gets a bounded comparison that is still honest: missing proof is
    shown as unknown, never silently omitted or implied as absence.
    """

    companies: list[ProductFeatureComparisonCompany] = Field(default_factory=list)
    rows: list[ProductFeatureComparisonRow] = Field(default_factory=list)
    row_count_total: int = 0
    company_count_total: int = 0
    row_limit: int = 12
    company_limit: int = 8
    capped: bool = False


class IntelligencePlaneSummary(BaseModel):
    """One evidence plane behind the current Argus read."""

    plane: str
    label: str
    status: str
    signal_count: int = 0
    evidence_count: int = 0
    summary: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class IntelligenceSpine(BaseModel):
    """One coherent proof object for how Argus earned the current read.

    The UI can render this directly instead of rediscovering the relationship
    between product reality, market conversation, demand, patterns, and actions.
    """

    verdict: str = "not_recorded"
    top_insight: str = "No Argus intelligence read has been stored yet."
    primary_action: Optional[str] = None
    confidence_limits: list[str] = Field(default_factory=list)
    planes: list[IntelligencePlaneSummary] = Field(default_factory=list)
    pattern_count: int = 0
    recommendation_count: int = 0
    feature_position_count: int = 0
    evidence_need_count: int = 0
    leading_entities: list[str] = Field(default_factory=list)
    leading_capabilities: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    can_recommend: bool = False
    next_operator_action: Optional[str] = None


class MarketFieldNode(BaseModel):
    """One visible entity in the Market Field knowledge graph."""

    node_id: str
    label: str
    node_type: str
    status: str = "present"
    summary: Optional[str] = None
    entity_id: Optional[int] = None
    href: Optional[str] = None


class MarketFieldEdge(BaseModel):
    """One relationship between Market Field nodes."""

    source_node_id: str
    target_node_id: str
    edge_type: str
    strength: str = "weak"
    status: str = "present"
    summary: Optional[str] = None


class MarketFieldHotspot(BaseModel):
    """A clickable market movement cluster surfaced on the first screen."""

    hotspot_id: str
    label: str
    argus_read: Optional[str] = None
    movement: str = "unknown"
    confidence_label: str = "unknown"
    proof_status: str = "unknown"
    time_window: str = "7d"
    connected_node_ids: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class MarketFieldAction(BaseModel):
    """One decision-ready action revealed from a selected hotspot."""

    owner: str
    priority: str
    action: str
    why_now: str
    evidence_basis: list[str] = Field(default_factory=list)
    confidence_label: str = "unknown"


class MarketFieldProofItem(BaseModel):
    """Proof summary behind a hotspot, grouped by intelligence plane."""

    plane: str
    summary: str
    source_count: int = 0
    href: Optional[str] = None


class MarketFieldState(BaseModel):
    """Market Field-first IA state for the CI-OS cockpit.

    Unknown boundaries are explicit graph nodes/statuses, not silent missing
    rows. This lets the UI distinguish confidence limits from real absence.
    """

    selected_hotspot_id: Optional[str] = None
    nodes: list[MarketFieldNode] = Field(default_factory=list)
    edges: list[MarketFieldEdge] = Field(default_factory=list)
    hotspots: list[MarketFieldHotspot] = Field(default_factory=list)
    actions: list[MarketFieldAction] = Field(default_factory=list)
    proof: list[MarketFieldProofItem] = Field(default_factory=list)
    time_windows: list[str] = Field(default_factory=lambda: ["today", "7d", "30d", "custom"])

    @property
    def selected_hotspot(self) -> Optional[MarketFieldHotspot]:
        if self.selected_hotspot_id:
            for hotspot in self.hotspots:
                if hotspot.hotspot_id == self.selected_hotspot_id:
                    return hotspot
        return self.hotspots[0] if self.hotspots else None


class DashboardOperatorCommand(BaseModel):
    """One admin/run-console command Argus recommends for the operator.

    The public cockpit may render the label and surface, but should not expose
    admin/API hrefs as public anonymous actions. The href remains in JSON for
    authenticated/admin surfaces that consume the same state contract.
    """

    label: str
    href: str
    method: str = "get"
    surface: Optional[str] = None


class DashboardOperatorCommandSummary(BaseModel):
    """Public-safe summary of one operator command.

    Unlike DashboardOperatorCommand, this model intentionally does not carry an
    href. It is safe for the public cockpit to render and for public dashboard
    JSON to expose.
    """

    label: str
    method: str = "get"
    surface: str
    route_kind: str = "unknown"


class DashboardOperatorHandoff(BaseModel):
    """Hermes/Argus handoff for this dashboard publication.

    This is the bridge from "screen" to "operating system": Hermes produces
    the handoff after the run, evidence queue, and Argus read. The dashboard
    renders it so readers can see whether Argus is actionable, blocked, or
    waiting on operator evidence.
    """

    tenant_slug: Optional[str] = None
    tenant_id: Optional[int] = None
    generated_at: Optional[str] = None
    status: str = "not_recorded"
    argus_readiness: str = "unknown"
    summary: str = "No Argus operator handoff has been attached to this dashboard."
    next_operator_action: str = "Run the Hermes daily sweep or rebuild the Argus operator handoff."
    top_blocker: Optional[dict[str, Any]] = None
    primary_command: Optional[DashboardOperatorCommand] = None
    secondary_command: Optional[DashboardOperatorCommand] = None
    operator_commands: list[DashboardOperatorCommandSummary] = Field(default_factory=list)
    demand_collection_plan: dict[str, Any] = Field(default_factory=dict)
    demand_plan_template: dict[str, Any] = Field(default_factory=dict)
    demand_plan_amendments: dict[str, Any] = Field(default_factory=dict)
    operator_brief: list[str] = Field(default_factory=list)
    artifact_refs: dict[str, Optional[str]] = Field(default_factory=dict)
    work_queue: dict[str, Any] = Field(default_factory=dict)
    artifact_path: Optional[str] = None
    artifact_found: bool = False


class DashboardState(BaseModel):
    """The full semantic snapshot dashboard_state.{daily_state,weekly_state}
    hold, reconstructed as typed data. One instance = one cadence's cockpit
    render for one tenant."""

    tenant_id: int
    cadence: str  # daily | weekly | ad_hoc
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    argus_read: ArgusRead = Field(default_factory=ArgusRead)
    coverage: CoverageBarometer = Field(default_factory=CoverageBarometer)
    competitor_cards: list[CompetitorSignalCard] = Field(default_factory=list)
    theses: list[LivingThesis] = Field(default_factory=list)
    run_health: RunHealth = Field(default_factory=RunHealth)
    product_market_run: ProductMarketRunStatus = Field(default_factory=ProductMarketRunStatus)
    build_status: BuildStatus = Field(default_factory=BuildStatus)
    report_history: list[ReportHistoryEntry] = Field(default_factory=list)
    suppressed_signals: list[SuppressedSignalEntry] = Field(default_factory=list)
    prescriptions: list[PrescriptionSummary] = Field(default_factory=list)
    monitored_competitors: list[MonitoredCompetitor] = Field(default_factory=list)
    source_health: list[SourceHealthEntry] = Field(default_factory=list)
    product_market_patterns: list[ProductMarketPatternSummary] = Field(default_factory=list)
    product_market_history: list[ProductMarketHistoryEntry] = Field(default_factory=list)
    product_market_run_history: list[ProductMarketRunHistoryEntry] = Field(default_factory=list)
    product_market_trends: list[ProductMarketTrendSummary] = Field(default_factory=list)
    product_market_heatmap: list[ProductMarketHeatmapCell] = Field(default_factory=list)
    product_market_entity_velocity: list[ProductMarketEntityVelocitySummary] = Field(default_factory=list)
    product_market_theme_heatmap: list[ProductMarketThemeHeatmapCell] = Field(default_factory=list)
    product_market_window_deltas: list[ProductMarketWindowDeltaSummary] = Field(default_factory=list)
    argus_recommendations: list[ArgusRecommendationSummary] = Field(default_factory=list)
    demand_signals: list[DemandSignalSummary] = Field(default_factory=list)
    demand_feature_alignment: DemandFeatureAlignmentState = Field(
        default_factory=DemandFeatureAlignmentState
    )
    argus_evidence_needs: list[ArgusEvidenceNeedSummary] = Field(default_factory=list)
    feature_matrix: list[FeatureMatrixRow] = Field(default_factory=list)
    product_feature_comparison: ProductFeatureComparisonState = Field(
        default_factory=ProductFeatureComparisonState
    )
    market_field: MarketFieldState = Field(default_factory=MarketFieldState)
    intelligence_spine: IntelligenceSpine = Field(default_factory=IntelligenceSpine)
    operator_handoff: DashboardOperatorHandoff = Field(default_factory=DashboardOperatorHandoff)

    material_delta_ids: list[Any] = Field(default_factory=list)
    action_item_ids: list[Any] = Field(default_factory=list)
    delivery_ids: list[Any] = Field(default_factory=list)

    @property
    def is_quiet(self) -> bool:
        """True only when coverage earned it AND there is nothing to show.
        This is the literal no-green-quiet gate: a dashboard with zero
        material deltas is NOT quiet-green if coverage is incomplete."""
        if not self.coverage.is_quiet_eligible:
            return False
        return not self.material_delta_ids and not self.competitor_cards

    @property
    def top_attention_level(self) -> AttentionLevel:
        if not self.competitor_cards:
            return AttentionLevel.NORMAL
        return self.competitor_cards[0].attention_level
