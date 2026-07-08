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

from pydantic import BaseModel, Field

# Schema version for the published JSON contract (publisher.py). Bump this
# whenever the shape of dashboard-state.v{N}.json changes in a
# backward-incompatible way.
DASHBOARD_STATE_SCHEMA_VERSION = 2


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
    delta_id: Optional[int] = None
    thesis_id: Optional[int] = None


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
    material_delta_count: int = 0
    delivery_status: Optional[str] = None
    quality_review_status: Optional[str] = None


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
    build_status: BuildStatus = Field(default_factory=BuildStatus)
    report_history: list[ReportHistoryEntry] = Field(default_factory=list)
    suppressed_signals: list[SuppressedSignalEntry] = Field(default_factory=list)
    prescriptions: list[PrescriptionSummary] = Field(default_factory=list)

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
