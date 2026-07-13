"""Compiles a DashboardState purely from injected, tenant-scoped repositories.

No DB or network access lives here (matches the brain/delivery package
convention). Postgres-backed implementations of the Protocols below live in
cios/db/repos/dashboard.py; tests use in-memory fakes (tests/dashboard/conftest.py).

Gate 5 acceptance criteria this module is responsible for:
  - "dashboard updates automatically from DB": build() is a pure function of
    whatever the injected repos currently return -- call it again after new
    rows land and the state reflects them, no caching.
  - "no green quiet unless all lanes ran": enforced by
    DashboardState.is_quiet (coverage-before-quiet), which this builder never
    overrides. build() does not set an "is_quiet" field directly -- it only
    supplies the coverage/material data the property derives from.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from cios.common.dedup import cluster_by_similarity
from cios.intelligence.capabilities import (
    capability_key as intelligence_capability_key,
    demand_capability_key as intelligence_demand_capability_key,
)

from .types import (
    ArgusRead,
    AttentionLevel,
    BuildStatus,
    ArgusEvidenceNeedSummary,
    ArgusRecommendationSummary,
    CompetitorSignalCard,
    CoverageBarometer,
    DashboardState,
    DemandFeatureAlignmentCompany,
    DemandFeatureAlignmentRow,
    DemandFeatureAlignmentState,
    DemandSignalSummary,
    FeatureMatrixRow,
    IntelligencePlaneSummary,
    IntelligenceSpine,
    LaneStatus,
    LivingThesis,
    MonitoredCompetitor,
    PrescriptionSummary,
    ProductFeatureComparisonCell,
    ProductFeatureComparisonCompany,
    ProductFeatureComparisonRow,
    ProductFeatureComparisonState,
    ProductMarketHeatmapCell,
    ProductMarketEntityVelocitySummary,
    ProductMarketHistoryEntry,
    ProductMarketPatternSummary,
    ProductMarketRunHistoryEntry,
    ProductMarketRunStatus,
    ProductMarketThemeHeatmapCell,
    ProductMarketTrendSummary,
    ProductMarketWindowDeltaSummary,
    ReportHistoryEntry,
    RunHealth,
    SourceHealthEntry,
    SuppressedSignalEntry,
    attention_level_for_score,
)


def _public_report_href(value: object) -> Optional[str]:
    if value is None:
        return None
    href = str(value).strip()
    if not href:
        return None
    if href.startswith(("http://", "https://", "./")):
        return href
    if href.startswith("/"):
        return None
    return href


def _first_matching_limit(values: list[str], needle: str, *, default: str) -> str:
    needle = needle.lower()
    for value in values:
        text = str(value).strip()
        if needle in text.lower():
            return text
    return default


DEMAND_IMPORT_FORMATS = ["csv", "json", "jsonl"]
DEMAND_IMPORT_REQUIRED_FIELDS = [
    "Page title",
    "Page path",
    "Engaged sessions",
    "Engaged sessions previous period",
    "Period start",
    "Period end",
    "Looker Studio URL",
]

FEATURE_COMPARISON_COMPANY_LIMIT = 8
FEATURE_COMPARISON_ROW_LIMIT = 12


# --------------------------------------------------------------------------
# Injected repository Protocols. Each returns plain data (dicts or simple
# records) already scoped to one tenant -- the builder does not take a
# tenant filter argument for the underlying queries, it trusts the repo was
# constructed/called tenant-scoped (matches the RLS + tenant_context
# convention in cios/db/session.py used by every Pg*Repository).
# --------------------------------------------------------------------------


class MaterialSignalsRepository(Protocol):
    def get_material_deltas(self, tenant_id: int) -> list[dict]:
        """Rows shaped like semantic_deltas joined to competitors, at
        minimum: id, competitor_id, competitor_name, delta_type,
        materiality_score, what_changed, why_it_matters, recommended_action,
        confidence, evidence_ids."""
        ...  # pragma: no cover - protocol


class ThesesRepository(Protocol):
    def get_active_theses(self, tenant_id: int) -> list[dict]:
        """Rows shaped like competitor_theses, at minimum: id, competitor_id,
        competitor_name, thesis, status, confidence, supporting_delta_ids,
        contradicting_delta_ids, updated_at."""
        ...  # pragma: no cover - protocol


class CoverageRepository(Protocol):
    def get_latest_coverage(self, tenant_id: int) -> Optional[dict]:
        """A dict with: lanes (list of {lane, ran, error}), coverage_score,
        false_negative_audit_status, missing_source_families. None if no
        coverage has ever been recorded for this tenant."""
        ...  # pragma: no cover - protocol


class RunRepository(Protocol):
    def get_latest_run(self, tenant_id: int, cadence: str) -> Optional[dict]:
        """A dict with: run_id, report_id, generated_at, model_tier,
        source_family_count, delivery_status, quality_review_status,
        argus_read (dict matching ArgusRead fields), action_item_ids,
        delivery_ids."""
        ...  # pragma: no cover - protocol


class BuildStatusProvider(Protocol):
    def get_build_status(self) -> Optional[dict]:
        """System-level (not tenant-scoped) build/deploy self-report: a dict
        with build_id, git_sha, deployed_at, environment, services (list of
        {name, status, detail, checked_at}), last_error."""
        ...  # pragma: no cover - protocol


class ReportHistoryRepository(Protocol):
    def get_recent_reports(self, tenant_id: int, limit: int = 10) -> list[dict]:
        """Rows shaped like `reports`, at minimum: id, report_date, cadence,
        title, summary, status, html_path. Most-recent-first."""
        ...  # pragma: no cover - protocol


class SuppressedSignalsRepository(Protocol):
    def get_recent_suppressed(self, tenant_id: int, limit: int = 10) -> list[dict]:
        """Rows shaped like `suppressed_diagnostics`, at minimum: id, reason,
        finding_ids, suppressed_at, notes. Most-recent-first."""
        ...  # pragma: no cover - protocol


class PrescriptionsRepository(Protocol):
    def get_current_prescriptions(self, tenant_id: int) -> list[dict]:
        """Rows shaped like cios.prescribe.types.Prescription, at minimum:
        title, team (Team.value), play (list[str]), urgency_window
        (UrgencyWindow.value), expected_effect, grounding (dict with
        evidence_urls). No table exists for this yet (Prescription engine
        wiring is a tracked backlog item) -- callers with nothing real to
        inject should pass None, not a fake repo. The builder renders that
        as an honest empty list, never invented plays."""
        ...  # pragma: no cover - protocol


class MonitoredCompetitorsRepository(Protocol):
    def get_monitored_competitors(self, tenant_id: int) -> list[dict]:
        """Rows for every monitored competitor, including competitors with no
        material signal this cycle."""
        ...  # pragma: no cover - protocol


class SourceHealthRepository(Protocol):
    def get_source_health(self, tenant_id: int) -> list[dict]:
        """Latest source-health rows for monitored sources."""
        ...  # pragma: no cover - protocol


class ProductMarketRepository(Protocol):
    def get_current_patterns(self, tenant_id: int) -> list[dict]:
        """Rows shaped like pattern_observations."""
        ...  # pragma: no cover - protocol

    def get_current_recommendations(self, tenant_id: int) -> list[dict]:
        """Rows shaped like argus_recommendations."""
        ...  # pragma: no cover - protocol

    def get_current_demand_signals(self, tenant_id: int) -> list[dict]:
        """Rows shaped like demand_signals."""
        ...  # pragma: no cover - protocol

    def get_feature_matrix(self, tenant_id: int) -> list[dict]:
        """Rows shaped like company_feature_positions joined to capabilities."""
        ...  # pragma: no cover - protocol

    def get_pattern_history(self, tenant_id: int, days: int = 30, limit: int = 100) -> list[dict]:
        """Recent pattern_observations over a bounded window for market memory."""
        ...  # pragma: no cover - protocol

    def get_latest_run_intelligence(self, tenant_id: int, limit: int = 10) -> list[dict]:
        """Recent product_market_run_intelligence rows, most-recent-first."""
        ...  # pragma: no cover - protocol


# Composite attention-score weights (Bug 4 fix). The old formula was
# `materiality * 100`, which meant two competitors sharing the same
# top-materiality finding always scored identically regardless of anything
# else -- degenerate, no differentiation. The composite below blends:
#   - materiality (50%): the existing top-signal materiality signal.
#   - signal volume for the competitor (30%, capped): more corroborating
#     signals earns more attention, but capped so one competitor spamming
#     signals cannot dominate the score by volume alone.
#   - evidence breadth (20%, capped): more DISTINCT sources cited for the
#     competitor is stronger corroboration than one source repeated.
# Thresholds (ATTENTION_THRESHOLD_* in .types) are applied against this same
# 0-100 composite score (via score/100), not against raw materiality alone.
ATTENTION_SCORE_MATERIALITY_WEIGHT = 50.0
ATTENTION_SCORE_VOLUME_WEIGHT = 30.0
ATTENTION_SCORE_EVIDENCE_WEIGHT = 20.0
ATTENTION_SCORE_VOLUME_CAP = 10
ATTENTION_SCORE_EVIDENCE_CAP = 10


def _composite_attention_score(materiality: float, signal_count: int, evidence_count: int) -> float:
    materiality_component = max(0.0, min(1.0, materiality)) * ATTENTION_SCORE_MATERIALITY_WEIGHT
    volume_component = (
        min(signal_count, ATTENTION_SCORE_VOLUME_CAP) / ATTENTION_SCORE_VOLUME_CAP
    ) * ATTENTION_SCORE_VOLUME_WEIGHT
    evidence_component = (
        min(evidence_count, ATTENTION_SCORE_EVIDENCE_CAP) / ATTENTION_SCORE_EVIDENCE_CAP
    ) * ATTENTION_SCORE_EVIDENCE_WEIGHT
    total = materiality_component + volume_component + evidence_component
    return round(max(0.0, min(100.0, total)), 1)


class DashboardStateBuilder:
    def __init__(
        self,
        *,
        signals: MaterialSignalsRepository,
        theses: ThesesRepository,
        coverage: CoverageRepository,
        runs: RunRepository,
        build_status: Optional[BuildStatusProvider] = None,
        report_history: Optional[ReportHistoryRepository] = None,
        suppressed_signals: Optional[SuppressedSignalsRepository] = None,
        prescriptions: Optional[PrescriptionsRepository] = None,
        product_market: Optional[ProductMarketRepository] = None,
        monitored_competitors: Optional[MonitoredCompetitorsRepository] = None,
        source_health: Optional[SourceHealthRepository] = None,
    ) -> None:
        self._signals = signals
        self._theses = theses
        self._coverage = coverage
        self._runs = runs
        self._build_status = build_status
        self._report_history = report_history
        self._suppressed_signals = suppressed_signals
        self._prescriptions = prescriptions
        self._product_market = product_market
        self._monitored_competitors = monitored_competitors
        self._source_health = source_health

    def build(self, *, tenant_id: int, cadence: str) -> DashboardState:
        coverage = self._build_coverage(tenant_id)
        deltas = self._signals.get_material_deltas(tenant_id)
        cards = self._build_competitor_cards(deltas)
        theses = self._build_theses(tenant_id)
        run = self._runs.get_latest_run(tenant_id, cadence) or {}
        run_health = self._build_run_health(run, rolling_material_delta_count=len(deltas))
        argus_read = ArgusRead(**(run.get("argus_read") or {}))
        build_status = self._build_build_status()
        report_history = self._build_report_history(tenant_id)
        suppressed_signals = self._build_suppressed_signals(tenant_id)
        prescriptions = self._build_prescriptions(tenant_id, deltas)
        monitored_competitors = self._build_monitored_competitors(tenant_id)
        source_health = self._build_source_health(tenant_id)
        product_market_patterns = self._build_product_market_patterns(tenant_id)
        product_market_history = self._build_product_market_history(tenant_id)
        product_market_run_history = self._build_product_market_run_history(tenant_id)
        demand_signals = self._build_demand_signals(tenant_id)
        product_market_run = self._build_product_market_run(
            run,
            latest_run_intelligence=product_market_run_history[0] if product_market_run_history else None,
            current_demand_signal_count=len(demand_signals),
        )
        product_market_trends = self._build_product_market_trends(product_market_history)
        product_market_heatmap = self._build_product_market_heatmap(product_market_history)
        product_market_entity_velocity = self._build_product_market_entity_velocity(product_market_heatmap)
        product_market_theme_heatmap = self._build_product_market_theme_heatmap(product_market_history)
        product_market_window_deltas = self._build_product_market_window_deltas(product_market_history)
        argus_recommendations = self._build_argus_recommendations(tenant_id)
        argus_evidence_needs = self._build_argus_evidence_needs(
            product_market_run_history,
            product_market_run=product_market_run,
        )
        feature_matrix = self._build_feature_matrix(tenant_id)
        product_feature_comparison = self._build_product_feature_comparison(
            feature_matrix,
            monitored_competitors,
        )
        demand_feature_alignment = self._build_demand_feature_alignment(
            demand_signals,
            feature_matrix,
        )
        intelligence_spine = self._build_intelligence_spine(
            product_market_run=product_market_run,
            product_market_patterns=product_market_patterns,
            product_market_history=product_market_history,
            product_market_run_history=product_market_run_history,
            argus_recommendations=argus_recommendations,
            demand_signals=demand_signals,
            demand_feature_alignment=demand_feature_alignment,
            argus_evidence_needs=argus_evidence_needs,
            feature_matrix=feature_matrix,
        )

        return DashboardState(
            tenant_id=tenant_id,
            cadence=cadence,
            argus_read=argus_read,
            coverage=coverage,
            competitor_cards=cards,
            theses=theses,
            run_health=run_health,
            product_market_run=product_market_run,
            build_status=build_status,
            report_history=report_history,
            suppressed_signals=suppressed_signals,
            prescriptions=prescriptions,
            monitored_competitors=monitored_competitors,
            source_health=source_health,
            product_market_patterns=product_market_patterns,
            product_market_history=product_market_history,
            product_market_run_history=product_market_run_history,
            product_market_trends=product_market_trends,
            product_market_heatmap=product_market_heatmap,
            product_market_entity_velocity=product_market_entity_velocity,
            product_market_theme_heatmap=product_market_theme_heatmap,
            product_market_window_deltas=product_market_window_deltas,
            argus_recommendations=argus_recommendations,
            demand_signals=demand_signals,
            demand_feature_alignment=demand_feature_alignment,
            argus_evidence_needs=argus_evidence_needs,
            feature_matrix=feature_matrix,
            product_feature_comparison=product_feature_comparison,
            intelligence_spine=intelligence_spine,
            material_delta_ids=[d["id"] for d in deltas if d.get("id") is not None],
            action_item_ids=list(run.get("action_item_ids") or []),
            delivery_ids=list(run.get("delivery_ids") or []),
        )

    # -- internals -----------------------------------------------------

    def _build_coverage(self, tenant_id: int) -> CoverageBarometer:
        raw = self._coverage.get_latest_coverage(tenant_id)
        if raw is None:
            # No coverage record at all is the least trustworthy state, not
            # the most: an empty CoverageBarometer has all_lanes_ran == False
            # by construction (bool([]) is False), so is_quiet_eligible is
            # False. Never green-quiet by default.
            return CoverageBarometer()
        return CoverageBarometer(
            lanes=[LaneStatus(**lane) for lane in raw.get("lanes", [])],
            coverage_score=raw.get("coverage_score"),
            false_negative_audit_status=raw.get("false_negative_audit_status"),
            missing_source_families=list(raw.get("missing_source_families") or []),
        )

    def _build_competitor_cards(self, deltas: list[dict]) -> list[CompetitorSignalCard]:
        # Cross-run dedup: `deltas` spans however many days of published
        # semantic_deltas the injected repo returns, so the same underlying
        # story can legitimately show up more than once (re-detected day
        # over day). Cluster same-competitor near-duplicates into one card
        # before ranking, instead of shipping N cards for one event.
        clusters = cluster_by_similarity(
            deltas,
            group_key=lambda d: d.get("competitor_id"),
            # Compare what_changed against what_changed ONLY (fallback to
            # why_it_matters when a row lacks it). Mixing in why_it_matters
            # diluted Jaccard on LLM paraphrases of the same story to ~0.3
            # (below threshold) and shipped duplicate cards on 2026-07-08 --
            # the why text varies far more between paraphrases than the
            # what text does.
            text=lambda d: d.get('what_changed') or d.get('why_it_matters') or '',
        )
        merged_deltas = [self._merge_delta_cluster(c.members) for c in clusters]

        # Per-competitor signal volume + evidence breadth, computed across
        # ALL of this competitor's deltas (not just the current cluster) --
        # "signal volume" and "evidence breadth" are competitor-level
        # attributes, not per-story ones.
        signal_counts: dict[Any, int] = {}
        evidence_by_competitor: dict[Any, set] = {}
        for d in deltas:
            cid = d.get("competitor_id")
            signal_counts[cid] = signal_counts.get(cid, 0) + 1
            urls = evidence_by_competitor.setdefault(cid, set())
            for e in d.get("evidence_ids") or []:
                urls.add(e)

        cards: list[CompetitorSignalCard] = []
        for d in merged_deltas:
            materiality = float(d.get("materiality_score") or 0.0)
            competitor_id = d["competitor_id"]
            signal_count = signal_counts.get(competitor_id, 0)
            evidence_count = len(evidence_by_competitor.get(competitor_id, ()))
            # attention_score is presented 0-100 (UX spec); materiality_score
            # is stored 0-1 (semantic_deltas.materiality_score numeric(5,4)).
            # Composite score (Bug 4 fix): materiality alone was degenerate
            # (two competitors sharing a top materiality scored identically);
            # blend in signal volume and evidence breadth. See
            # _composite_attention_score above.
            attention_score = _composite_attention_score(materiality, signal_count, evidence_count)
            level = attention_level_for_score(attention_score / 100.0)
            cards.append(
                CompetitorSignalCard(
                    competitor_id=d["competitor_id"],
                    competitor_name=d.get("competitor_name") or f"Competitor {d['competitor_id']}",
                    attention_score=attention_score,
                    attention_level=level,
                    action_cue=_action_cue(level, d.get("recommended_action")),
                    top_signal_headline=d.get("what_changed"),
                    what_changed=d.get("what_changed"),
                    why_it_matters=d.get("why_it_matters"),
                    recommended_action=d.get("recommended_action"),
                    materiality_score=materiality,
                    confidence=d.get("confidence"),
                    evidence_ids=list(d.get("evidence_ids") or []),
                    delta_id=d.get("id"),
                    thesis_id=d.get("thesis_id"),
                    duplicate_count=d.get("_duplicate_count", 1),
                )
            )
        # materiality-before-urgency: highest attention first, deterministic
        # tiebreak on competitor_id so repeated builds don't reorder ties.
        cards.sort(key=lambda c: (-c.attention_score, c.competitor_id))
        return cards

    @staticmethod
    def _merge_delta_cluster(members: list[dict]) -> dict:
        """Merges a cluster of near-duplicate delta rows into one: keep the
        highest-materiality member's fields (it is the most confidently
        described version of the story), union the evidence ids across all
        members (never drop evidence a duplicate carried), and record how
        many sources/days it was seen in."""
        if len(members) == 1:
            best = dict(members[0])
            best["_duplicate_count"] = 1
            return best

        best_member = max(members, key=lambda d: float(d.get("materiality_score") or 0.0))
        evidence: list = []
        seen: set = set()
        for m in members:
            for e in m.get("evidence_ids") or []:
                if e not in seen:
                    seen.add(e)
                    evidence.append(e)

        merged = dict(best_member)
        merged["evidence_ids"] = evidence
        merged["_duplicate_count"] = len(members)
        return merged

    def _build_theses(self, tenant_id: int) -> list[LivingThesis]:
        rows = self._theses.get_active_theses(tenant_id)
        # Same-hypothesis dedup (2026-07-08 live-page regression: one Elastic
        # repositioning hypothesis rendered six-plus times in paraphrase).
        # Cluster per competitor on the thesis text; keep the highest-
        # confidence wording, union the evidence ids so no supporting or
        # contradicting delta is dropped by the merge.
        # Threshold 0.4 with transitive linking, both measured on the real
        # 2026-07-08 production theses: six rewordings of one Elastic
        # hypothesis scored 0.35-0.53 pairwise (rep-only 0.6 merged zero),
        # while genuinely distinct stories measured <= 0.35. NOTE this is
        # symptomatic relief -- the upstream thesis writer should UPDATE the
        # standing thesis row instead of minting a fresh paraphrase each run
        # (tracked as its own task).
        clusters = cluster_by_similarity(
            rows,
            group_key=lambda r: r.get("competitor_id"),
            text=lambda r: r.get("thesis") or "",
            threshold=0.4,
            match="any",
        )
        theses: list[LivingThesis] = []
        for cluster in clusters:
            best = max(cluster.members, key=lambda r: float(r.get("confidence") or 0.0))
            supporting: set = set()
            contradicting: set = set()
            for m in cluster.members:
                supporting.update(m.get("supporting_delta_ids") or [])
                contradicting.update(m.get("contradicting_delta_ids") or [])
            theses.append(
                LivingThesis(
                    thesis_id=best["id"],
                    competitor_id=best["competitor_id"],
                    competitor_name=best.get("competitor_name"),
                    thesis=best["thesis"],
                    status=best.get("status", "active"),
                    confidence=best.get("confidence"),
                    supporting_delta_count=len(supporting),
                    contradicting_delta_count=len(contradicting),
                    updated_at=best.get("updated_at"),
                )
            )
        return theses

    def _build_run_health(self, run: dict, *, rolling_material_delta_count: int) -> RunHealth:
        current_material_delta_count = run.get("material_delta_count")
        if current_material_delta_count is None:
            current_material_delta_count = rolling_material_delta_count
        return RunHealth(
            run_id=run.get("run_id"),
            report_id=run.get("report_id"),
            generated_at=run.get("generated_at"),
            model_tier=run.get("model_tier"),
            source_family_count=run.get("source_family_count"),
            current_material_delta_count=int(current_material_delta_count or 0),
            rolling_material_delta_count=rolling_material_delta_count,
            material_delta_count=int(current_material_delta_count or 0),
            delivery_status=run.get("delivery_status"),
            quality_review_status=run.get("quality_review_status"),
        )

    def _build_product_market_run(
        self,
        run: dict,
        *,
        latest_run_intelligence: ProductMarketRunHistoryEntry | None = None,
        current_demand_signal_count: int = 0,
    ) -> ProductMarketRunStatus:
        summary = run.get("product_market_summary")
        if not isinstance(summary, dict):
            return ProductMarketRunStatus()

        plan_summary = summary.get("product_surface_plan_summary")
        if not isinstance(plan_summary, dict):
            plan_summary = {}
        runner_summary = summary.get("runner_summary")
        if not isinstance(runner_summary, dict):
            runner_summary = {}
        runner_summary = self._final_product_market_summary(summary, runner_summary)
        runner_summary = self._merge_latest_run_intelligence_summary(
            runner_summary,
            latest_run_intelligence,
        )
        scout_paths = summary.get("scout_paths") or []
        if not isinstance(scout_paths, list):
            scout_paths = []
        consumed_ids = runner_summary.get("learning_instruction_improvement_ids") or []
        if not isinstance(consumed_ids, list):
            consumed_ids = []
        intelligence_brief = runner_summary.get("intelligence_brief")
        if not isinstance(intelligence_brief, dict):
            intelligence_brief = {}
        conversion_diagnostics = runner_summary.get("conversion_diagnostics")
        if not isinstance(conversion_diagnostics, dict):
            conversion_diagnostics = intelligence_brief.get("conversion_diagnostics")
        if not isinstance(conversion_diagnostics, dict):
            conversion_diagnostics = {}
        movement_map = intelligence_brief.get("movement_map")
        if not isinstance(movement_map, dict):
            movement_map = {}
        window_comparison = intelligence_brief.get("window_comparison")
        if not isinstance(window_comparison, dict):
            window_comparison = {}
        errors = summary.get("errors") or []
        if not isinstance(errors, list):
            errors = [str(errors)]
        looker_discovered_count = int(summary.get("looker_discovered_count") or 0)
        looker_ready_count = int(summary.get("looker_ready_count") or 0)
        looker_error_count = int(summary.get("looker_error_count") or 0)
        looker_normalized_row_count = int(summary.get("looker_normalized_row_count") or 0)
        latest_demand_signal_count = (
            latest_run_intelligence.demand_signal_count
            if latest_run_intelligence is not None
            else 0
        )
        demand_signal_count = self._first_nonzero_int(
            runner_summary.get("demand_signal_count"),
            latest_demand_signal_count,
            current_demand_signal_count,
        )
        effective_demand_row_count = max(looker_normalized_row_count, current_demand_signal_count)

        return ProductMarketRunStatus(
            status=str(summary.get("status") or "not_recorded"),
            next_sweep_plan_path=summary.get("next_sweep_plan_path"),
            learning_apply_plan_path=summary.get("learning_apply_plan_path"),
            learning_apply_plan_summary=dict(summary.get("learning_apply_plan_summary") or {}),
            target_count=int(plan_summary.get("target_count") or 0),
            target_company_count=int(plan_summary.get("target_company_count") or 0),
            target_companies=[
                str(company)
                for company in (plan_summary.get("target_companies") or [])
                if str(company).strip()
            ],
            surface_family_counts={
                str(family): int(count)
                for family, count in (plan_summary.get("surface_family_counts") or {}).items()
                if str(family).strip()
            },
            product_surface_execution_summary=dict(
                summary.get("product_surface_execution_summary") or {}
            ),
            product_muscle_gap_plan=dict(summary.get("product_muscle_gap_plan") or {}),
            post_run_product_muscle_gap_discovery=dict(
                summary.get("post_run_product_muscle_gap_discovery") or {}
            ),
            post_run_product_surface_promotion=dict(
                summary.get("post_run_product_surface_promotion") or {}
            ),
            post_run_next_sweep_status=summary.get("post_run_next_sweep_status"),
            learning_prioritized_count=int(plan_summary.get("learning_prioritized_count") or 0),
            prioritized_targets=list(plan_summary.get("prioritized_targets") or []),
            runner_verdict=runner_summary.get("verdict"),
            learning_instruction_count=int(runner_summary.get("learning_instruction_count") or 0),
            consumed_learning_ids=[int(item) for item in consumed_ids if str(item).isdigit()],
            scout_artifact_count=len(scout_paths),
            demand_plane_status=self._product_market_demand_plane_status(
                status=str(summary.get("status") or "not_recorded"),
                discovered_count=looker_discovered_count,
                ready_count=looker_ready_count,
                error_count=looker_error_count,
                normalized_row_count=effective_demand_row_count,
                demand_signal_count=demand_signal_count,
            ),
            demand_readiness=dict(summary.get("demand_readiness") or {}),
            looker_discovered_count=looker_discovered_count,
            looker_ready_count=looker_ready_count,
            looker_error_count=looker_error_count,
            looker_normalized_row_count=effective_demand_row_count,
            looker_skipped_row_count=int(summary.get("looker_skipped_row_count") or 0),
            looker_archived_count=int(summary.get("looker_archived_count") or 0),
            looker_manifest_path=summary.get("looker_manifest_path"),
            intelligence_brief=dict(intelligence_brief),
            movement_map=dict(movement_map),
            window_comparison=dict(window_comparison),
            conversion_diagnostics=dict(conversion_diagnostics),
            stage_ledger=[
                dict(entry)
                for entry in (summary.get("stage_ledger") or [])
                if isinstance(entry, dict)
            ],
            product_event_count=DashboardStateBuilder._first_nonzero_int(
                runner_summary.get("product_event_count"),
                conversion_diagnostics.get("product_event_count"),
            ),
            conversation_theme_count=DashboardStateBuilder._first_nonzero_int(
                runner_summary.get("conversation_theme_count"),
                conversion_diagnostics.get("conversation_theme_count"),
            ),
            demand_signal_count=demand_signal_count,
            pattern_count=DashboardStateBuilder._first_nonzero_int(
                runner_summary.get("pattern_count"),
                conversion_diagnostics.get("pattern_count"),
            ),
            recommendation_count=DashboardStateBuilder._first_nonzero_int(
                runner_summary.get("recommendation_count"),
                conversion_diagnostics.get("recommendation_count"),
            ),
            errors=[str(error) for error in errors],
        )

    @staticmethod
    def _final_product_market_summary(summary: dict, fallback: dict) -> dict:
        ledger_status = str(summary.get("ledger_refresh_status") or "")
        ledger_summary = summary.get("ledger_refresh_summary")
        if ledger_status in {"ran", "completed"} and isinstance(ledger_summary, dict):
            return ledger_summary
        return fallback

    @staticmethod
    def _merge_latest_run_intelligence_summary(
        runner_summary: dict,
        latest_run_intelligence: ProductMarketRunHistoryEntry | None,
    ) -> dict:
        if latest_run_intelligence is None or not latest_run_intelligence.intelligence_brief:
            return runner_summary
        merged = dict(runner_summary)
        merged["verdict"] = latest_run_intelligence.verdict or merged.get("verdict")
        merged["product_event_count"] = DashboardStateBuilder._first_nonzero_int(
            latest_run_intelligence.product_event_count,
            merged.get("product_event_count"),
        )
        merged["conversation_theme_count"] = DashboardStateBuilder._first_nonzero_int(
            latest_run_intelligence.conversation_theme_count,
            merged.get("conversation_theme_count"),
        )
        merged["demand_signal_count"] = DashboardStateBuilder._first_nonzero_int(
            latest_run_intelligence.demand_signal_count,
            merged.get("demand_signal_count"),
        )
        merged["pattern_count"] = DashboardStateBuilder._first_nonzero_int(
            latest_run_intelligence.pattern_count,
            merged.get("pattern_count"),
        )
        merged["recommendation_count"] = DashboardStateBuilder._first_nonzero_int(
            latest_run_intelligence.recommendation_count,
            merged.get("recommendation_count"),
        )
        merged["learning_instruction_count"] = DashboardStateBuilder._first_nonzero_int(
            latest_run_intelligence.learning_instruction_count,
            merged.get("learning_instruction_count"),
        )
        if latest_run_intelligence.learning_instruction_improvement_ids:
            merged["learning_instruction_improvement_ids"] = list(
                latest_run_intelligence.learning_instruction_improvement_ids
            )
        merged["intelligence_brief"] = dict(latest_run_intelligence.intelligence_brief)
        return merged

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

    def _build_report_history(self, tenant_id: int) -> list[ReportHistoryEntry]:
        # No provider injected is not an error -- some callers (tests,
        # early cadences before the reports table has rows) legitimately
        # have nothing to show. Renderer shows the honest empty-state line.
        if self._report_history is None:
            return []
        rows = self._report_history.get_recent_reports(tenant_id)
        return [
            ReportHistoryEntry(
                report_id=r["id"],
                report_date=r["report_date"],
                cadence=r["cadence"],
                title=r.get("title"),
                summary=r.get("summary"),
                status=r.get("status"),
                html_path=_public_report_href(r.get("html_path")),
            )
            for r in rows
        ]

    def _build_suppressed_signals(self, tenant_id: int) -> list[SuppressedSignalEntry]:
        if self._suppressed_signals is None:
            return []
        rows = self._suppressed_signals.get_recent_suppressed(tenant_id)
        return [
            SuppressedSignalEntry(
                suppressed_id=r["id"],
                reason=r["reason"],
                finding_count=len(r.get("finding_ids") or []),
                suppressed_at=r.get("suppressed_at"),
                notes=r.get("notes"),
            )
            for r in rows
        ]

    def _build_prescriptions(self, tenant_id: int, deltas: list[dict]) -> list[PrescriptionSummary]:
        # No provider injected is not an error -- the prescription engine's
        # DB wiring is a tracked backlog item, not a schema table yet. The
        # cockpit renders the honest "no plays yet" empty state per lens
        # rather than inventing one.
        if self._prescriptions is None:
            return []
        rows = self._prescriptions.get_current_prescriptions(tenant_id)
        evidence_to_competitor = self._evidence_to_competitor_map(deltas)
        summaries: list[PrescriptionSummary] = []
        for r in rows:
            evidence_urls = list((r.get("grounding") or {}).get("evidence_urls") or r.get("evidence_urls") or [])
            competitor_id, competitor_name = self._attribute_competitor(evidence_urls, evidence_to_competitor)
            summaries.append(
                PrescriptionSummary(
                    title=r["title"],
                    team=r["team"],
                    play=list(r.get("play") or []),
                    urgency_window=r["urgency_window"],
                    expected_effect=r.get("expected_effect"),
                    evidence_urls=evidence_urls,
                    effort=r.get("effort"),
                    materiality_score=r.get("materiality_score"),
                    competitor_id=competitor_id,
                    competitor_name=competitor_name,
                )
            )
        return summaries

    def _build_monitored_competitors(self, tenant_id: int) -> list[MonitoredCompetitor]:
        if self._monitored_competitors is None:
            return []
        rows = self._monitored_competitors.get_monitored_competitors(tenant_id)
        competitors = [MonitoredCompetitor(**r) for r in rows]
        competitors.sort(key=lambda c: (c.status != "active", c.competitor_name.lower(), c.competitor_id))
        return competitors

    def _build_source_health(self, tenant_id: int) -> list[SourceHealthEntry]:
        if self._source_health is None:
            return []
        rows = self._source_health.get_source_health(tenant_id)
        return [SourceHealthEntry(**r) for r in rows]

    def _build_product_market_patterns(self, tenant_id: int) -> list[ProductMarketPatternSummary]:
        if self._product_market is None:
            return []
        rows = self._product_market.get_current_patterns(tenant_id)
        return [
            ProductMarketPatternSummary(
                pattern_id=r["id"],
                pattern_type=r["pattern_type"],
                capability_text=r["capability_text"],
                summary=r["summary"],
                involved_companies=list(r.get("involved_companies") or []),
                confidence=r.get("confidence"),
                evidence_refs=list(r.get("evidence_refs") or []),
            )
            for r in rows
        ]

    def _build_product_market_history(self, tenant_id: int) -> list[ProductMarketHistoryEntry]:
        if self._product_market is None:
            return []
        rows = self._product_market.get_pattern_history(tenant_id, days=30, limit=100)
        return [
            ProductMarketHistoryEntry(
                pattern_id=r["id"],
                observed_at=r.get("observed_at") or r["created_at"],
                pattern_type=r["pattern_type"],
                capability_text=r["capability_text"],
                summary=r["summary"],
                involved_companies=list(r.get("involved_companies") or []),
                confidence=r.get("confidence"),
                evidence_refs=list(r.get("evidence_refs") or []),
            )
            for r in rows
        ]

    def _build_product_market_run_history(self, tenant_id: int) -> list[ProductMarketRunHistoryEntry]:
        if self._product_market is None:
            return []
        get_latest_run_intelligence = getattr(self._product_market, "get_latest_run_intelligence", None)
        if not callable(get_latest_run_intelligence):
            return []
        rows = get_latest_run_intelligence(tenant_id, limit=10)
        history: list[ProductMarketRunHistoryEntry] = []
        for r in rows:
            brief = r.get("intelligence_brief")
            if not isinstance(brief, dict):
                brief = {}
            learning_ids = r.get("learning_instruction_improvement_ids") or []
            if not isinstance(learning_ids, list):
                learning_ids = []
            history.append(
                ProductMarketRunHistoryEntry(
                    run_intelligence_id=int(r["id"]),
                    observed_at=r["created_at"],
                    verdict=str(r.get("verdict") or brief.get("verdict") or "quiet"),
                    top_insight=str(brief.get("top_insight") or "No run intelligence brief was stored."),
                    intelligence_brief=dict(brief),
                    primary_action=brief.get("primary_action"),
                    watchlist=[str(item) for item in (brief.get("watchlist") or [])],
                    evidence_urls=[str(item) for item in (brief.get("evidence_urls") or [])],
                    confidence_limits=[str(item) for item in (brief.get("confidence_limits") or [])],
                    next_questions=[str(item) for item in (brief.get("next_questions") or [])],
                    product_event_count=int(r.get("product_event_count") or 0),
                    conversation_theme_count=int(r.get("conversation_theme_count") or 0),
                    demand_signal_count=int(r.get("demand_signal_count") or 0),
                    pattern_count=int(r.get("pattern_count") or 0),
                    recommendation_count=int(r.get("recommendation_count") or 0),
                    learning_instruction_count=int(r.get("learning_instruction_count") or 0),
                    learning_instruction_improvement_ids=[
                        int(item) for item in learning_ids if str(item).isdigit()
                    ],
                )
            )
        return history

    @staticmethod
    def _build_product_market_trends(
        history: list[ProductMarketHistoryEntry],
    ) -> list[ProductMarketTrendSummary]:
        if not history:
            return []

        latest_observed_at = max(entry.observed_at for entry in history)
        reference_date = latest_observed_at.date()
        by_capability: dict[str, list[ProductMarketHistoryEntry]] = {}
        for entry in history:
            age_days = (reference_date - entry.observed_at.date()).days
            if 0 <= age_days <= 30:
                by_capability.setdefault(entry.capability_text, []).append(entry)

        trends: list[ProductMarketTrendSummary] = []
        for capability, entries in by_capability.items():
            entries = sorted(entries, key=lambda item: item.observed_at, reverse=True)
            seven_day_entries = [
                entry for entry in entries if 0 <= (reference_date - entry.observed_at.date()).days <= 7
            ]
            direction = DashboardStateBuilder._trend_direction(
                seven_day_count=len(seven_day_entries),
                thirty_day_count=len(entries),
            )
            companies: list[str] = []
            evidence_refs: list[dict[str, Any]] = []
            seen_urls: set[str] = set()
            confidences: list[float] = []
            for entry in entries:
                for company in entry.involved_companies:
                    if company not in companies:
                        companies.append(company)
                if entry.confidence is not None:
                    confidences.append(float(entry.confidence))
                for evidence in entry.evidence_refs:
                    url = str(evidence.get("source_url") or "")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    evidence_refs.append(evidence)
                    if len(evidence_refs) >= 8:
                        break
                if len(evidence_refs) >= 8:
                    break

            latest = entries[0]
            confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
            trends.append(
                ProductMarketTrendSummary(
                    capability_text=capability,
                    direction=direction,
                    pattern_count_7d=len(seven_day_entries),
                    pattern_count_30d=len(entries),
                    involved_companies=companies,
                    latest_summary=latest.summary,
                    latest_observed_at=latest.observed_at,
                    confidence=confidence,
                    evidence_refs=evidence_refs,
                )
            )

        return sorted(
            trends,
            key=lambda item: (item.pattern_count_7d, item.pattern_count_30d, item.latest_observed_at),
            reverse=True,
        )

    @staticmethod
    def _trend_direction(*, seven_day_count: int, thirty_day_count: int) -> str:
        if seven_day_count >= 2 and seven_day_count / max(thirty_day_count, 1) >= 0.6:
            return "accelerating"
        if seven_day_count > 0 and thirty_day_count > seven_day_count:
            return "sustained"
        if seven_day_count > 0:
            return "emerging"
        return "dormant"

    @staticmethod
    def _build_product_market_heatmap(
        history: list[ProductMarketHistoryEntry],
    ) -> list[ProductMarketHeatmapCell]:
        if not history:
            return []

        latest_observed_at = max(entry.observed_at for entry in history)
        reference_date = latest_observed_at.date()
        grouped: dict[tuple[str, str], list[ProductMarketHistoryEntry]] = {}
        for entry in history:
            age_days = (reference_date - entry.observed_at.date()).days
            if age_days < 0 or age_days > 30:
                continue
            for company in entry.involved_companies:
                if company:
                    grouped.setdefault((company, entry.capability_text), []).append(entry)

        cells: list[ProductMarketHeatmapCell] = []
        for (company, capability), entries in grouped.items():
            entries = sorted(entries, key=lambda item: item.observed_at, reverse=True)
            seven_day_entries = [
                entry for entry in entries if 0 <= (reference_date - entry.observed_at.date()).days <= 7
            ]
            confidences = [float(entry.confidence) for entry in entries if entry.confidence is not None]
            confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
            intensity = DashboardStateBuilder._heatmap_intensity(
                seven_day_count=len(seven_day_entries),
                thirty_day_count=len(entries),
                confidence=confidence,
            )
            evidence_refs = DashboardStateBuilder._dedupe_evidence_refs(entries, limit=6)
            latest = entries[0]
            cells.append(
                ProductMarketHeatmapCell(
                    entity_name=company,
                    capability_text=capability,
                    heat_level=DashboardStateBuilder._heat_level(len(seven_day_entries), len(entries)),
                    intensity_score=intensity,
                    pattern_count_7d=len(seven_day_entries),
                    pattern_count_30d=len(entries),
                    latest_summary=latest.summary,
                    latest_observed_at=latest.observed_at,
                    confidence=confidence,
                    evidence_refs=evidence_refs,
                )
            )

        return sorted(
            cells,
            key=lambda item: (item.intensity_score, item.pattern_count_7d, item.pattern_count_30d, item.entity_name),
            reverse=True,
        )

    @staticmethod
    def _heat_level(seven_day_count: int, thirty_day_count: int) -> str:
        if seven_day_count >= 2:
            return "hot"
        if seven_day_count >= 1:
            return "warm"
        if thirty_day_count >= 1:
            return "watch"
        return "cold"

    @staticmethod
    def _heatmap_intensity(*, seven_day_count: int, thirty_day_count: int, confidence: float | None) -> float:
        score = (seven_day_count * 35.0) + (thirty_day_count * 10.0)
        if confidence is not None:
            score += confidence * 20.0
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _build_product_market_entity_velocity(
        heatmap: list[ProductMarketHeatmapCell],
    ) -> list[ProductMarketEntityVelocitySummary]:
        if not heatmap:
            return []

        by_entity: dict[str, list[ProductMarketHeatmapCell]] = {}
        for cell in heatmap:
            by_entity.setdefault(cell.entity_name, []).append(cell)

        summaries: list[ProductMarketEntityVelocitySummary] = []
        for entity_name, cells in by_entity.items():
            cells = sorted(
                cells,
                key=lambda item: (item.latest_observed_at, item.intensity_score, item.capability_text),
                reverse=True,
            )
            total_7d = sum(cell.pattern_count_7d for cell in cells)
            total_30d = sum(cell.pattern_count_30d for cell in cells)
            hot_count = sum(1 for cell in cells if cell.heat_level == "hot")
            warm_count = sum(1 for cell in cells if cell.heat_level == "warm")
            confidences = [float(cell.confidence) for cell in cells if cell.confidence is not None]
            confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
            top_capabilities = [
                cell.capability_text
                for cell in sorted(cells, key=lambda item: (-item.intensity_score, item.capability_text))[:5]
            ]
            latest = cells[0]
            summaries.append(
                ProductMarketEntityVelocitySummary(
                    entity_name=entity_name,
                    direction=DashboardStateBuilder._entity_velocity_direction(
                        total_patterns_7d=total_7d,
                        total_patterns_30d=total_30d,
                        hot_capability_count=hot_count,
                    ),
                    total_patterns_7d=total_7d,
                    total_patterns_30d=total_30d,
                    hot_capability_count=hot_count,
                    warm_capability_count=warm_count,
                    top_capabilities=top_capabilities,
                    latest_summary=latest.latest_summary,
                    latest_observed_at=latest.latest_observed_at,
                    confidence=confidence,
                    evidence_refs=DashboardStateBuilder._dedupe_heatmap_evidence_refs(cells, limit=8),
                )
            )

        return sorted(
            summaries,
            key=lambda item: (
                item.hot_capability_count,
                item.total_patterns_7d,
                item.total_patterns_30d,
                item.latest_observed_at,
                item.entity_name,
            ),
            reverse=True,
        )

    @staticmethod
    def _entity_velocity_direction(
        *,
        total_patterns_7d: int,
        total_patterns_30d: int,
        hot_capability_count: int,
    ) -> str:
        if hot_capability_count > 0 or total_patterns_7d >= 2:
            return "accelerating"
        if total_patterns_7d > 0 and total_patterns_30d > total_patterns_7d:
            return "sustained"
        if total_patterns_7d > 0:
            return "emerging"
        return "dormant"

    @staticmethod
    def _dedupe_heatmap_evidence_refs(
        cells: list[ProductMarketHeatmapCell],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        evidence_refs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for cell in sorted(cells, key=lambda item: item.latest_observed_at, reverse=True):
            for evidence in cell.evidence_refs:
                url = str(evidence.get("source_url") or "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                evidence_refs.append(evidence)
                if len(evidence_refs) >= limit:
                    return evidence_refs
        return evidence_refs

    @staticmethod
    def _build_product_market_theme_heatmap(
        history: list[ProductMarketHistoryEntry],
    ) -> list[ProductMarketThemeHeatmapCell]:
        if not history:
            return []

        latest_observed_at = max(entry.observed_at for entry in history)
        reference_date = latest_observed_at.date()
        by_theme: dict[str, list[ProductMarketHistoryEntry]] = {}
        for entry in history:
            age_days = (reference_date - entry.observed_at.date()).days
            if 0 <= age_days <= 30:
                by_theme.setdefault(entry.capability_text, []).append(entry)

        cells: list[ProductMarketThemeHeatmapCell] = []
        for theme, entries in by_theme.items():
            entries = sorted(entries, key=lambda item: item.observed_at, reverse=True)
            seven_day_entries = [
                entry for entry in entries if 0 <= (reference_date - entry.observed_at.date()).days <= 7
            ]
            leading_entities: list[str] = []
            pattern_types: list[str] = []
            confidences: list[float] = []
            for entry in entries:
                for company in entry.involved_companies:
                    if company and company not in leading_entities:
                        leading_entities.append(company)
                if entry.pattern_type not in pattern_types:
                    pattern_types.append(entry.pattern_type)
                if entry.confidence is not None:
                    confidences.append(float(entry.confidence))

            confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
            intensity = DashboardStateBuilder._theme_heatmap_intensity(
                seven_day_count=len(seven_day_entries),
                thirty_day_count=len(entries),
                entity_count=len(leading_entities),
                confidence=confidence,
            )
            latest = entries[0]
            cells.append(
                ProductMarketThemeHeatmapCell(
                    theme_text=theme,
                    heat_level=DashboardStateBuilder._heat_level(len(seven_day_entries), len(entries)),
                    direction=DashboardStateBuilder._trend_direction(
                        seven_day_count=len(seven_day_entries),
                        thirty_day_count=len(entries),
                    ),
                    intensity_score=intensity,
                    pattern_count_7d=len(seven_day_entries),
                    pattern_count_30d=len(entries),
                    entity_count=len(leading_entities),
                    leading_entities=leading_entities[:8],
                    pattern_types=pattern_types,
                    latest_summary=latest.summary,
                    latest_observed_at=latest.observed_at,
                    confidence=confidence,
                    evidence_refs=DashboardStateBuilder._dedupe_evidence_refs(entries, limit=8),
                )
            )

        return sorted(
            cells,
            key=lambda item: (
                item.intensity_score,
                item.pattern_count_7d,
                item.pattern_count_30d,
                item.entity_count,
                item.latest_observed_at,
            ),
            reverse=True,
        )

    @staticmethod
    def _theme_heatmap_intensity(
        *,
        seven_day_count: int,
        thirty_day_count: int,
        entity_count: int,
        confidence: float | None,
    ) -> float:
        score = (seven_day_count * 35.0) + (thirty_day_count * 10.0) + (entity_count * 6.0)
        if confidence is not None:
            score += confidence * 20.0
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _build_product_market_window_deltas(
        history: list[ProductMarketHistoryEntry],
    ) -> list[ProductMarketWindowDeltaSummary]:
        if not history:
            return []

        latest_observed_at = max(entry.observed_at for entry in history)
        reference_date = latest_observed_at.date()
        grouped: dict[tuple[str, str], list[ProductMarketHistoryEntry]] = {}
        for entry in history:
            age_days = (reference_date - entry.observed_at.date()).days
            if age_days < 0 or age_days > 14:
                continue
            grouped.setdefault(("theme", entry.capability_text), []).append(entry)
            for company in entry.involved_companies:
                if company:
                    grouped.setdefault(("entity", company), []).append(entry)

        deltas: list[ProductMarketWindowDeltaSummary] = []
        for (subject_type, subject_name), entries in grouped.items():
            current_entries = [
                entry for entry in entries if 0 <= (reference_date - entry.observed_at.date()).days <= 7
            ]
            previous_entries = [
                entry for entry in entries if 8 <= (reference_date - entry.observed_at.date()).days <= 14
            ]
            if not current_entries and not previous_entries:
                continue
            combined_entries = sorted(entries, key=lambda item: item.observed_at, reverse=True)
            latest = combined_entries[0]
            confidences = [float(entry.confidence) for entry in combined_entries if entry.confidence is not None]
            confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
            current_count = len(current_entries)
            previous_count = len(previous_entries)
            deltas.append(
                ProductMarketWindowDeltaSummary(
                    subject_type=subject_type,
                    subject_name=subject_name,
                    direction=DashboardStateBuilder._window_delta_direction(
                        current_count=current_count,
                        previous_count=previous_count,
                    ),
                    current_pattern_count=current_count,
                    previous_pattern_count=previous_count,
                    delta=current_count - previous_count,
                    related_entities=DashboardStateBuilder._dedupe_history_companies(combined_entries, limit=8),
                    related_capabilities=DashboardStateBuilder._dedupe_history_capabilities(
                        combined_entries,
                        limit=8,
                    ),
                    latest_summary=latest.summary,
                    latest_observed_at=latest.observed_at,
                    confidence=confidence,
                    evidence_refs=DashboardStateBuilder._dedupe_evidence_refs(combined_entries, limit=8),
                )
            )

        return sorted(
            deltas,
            key=lambda item: (
                item.current_pattern_count,
                item.delta,
                item.previous_pattern_count,
                item.latest_observed_at,
                item.subject_type,
                item.subject_name,
            ),
            reverse=True,
        )

    @staticmethod
    def _window_delta_direction(*, current_count: int, previous_count: int) -> str:
        if current_count > 0 and previous_count == 0:
            return "new"
        if current_count > previous_count:
            return "rising"
        if current_count < previous_count:
            return "falling"
        if current_count > 0:
            return "flat"
        return "inactive"

    @staticmethod
    def _dedupe_history_companies(entries: list[ProductMarketHistoryEntry], *, limit: int) -> list[str]:
        companies: list[str] = []
        for entry in entries:
            for company in entry.involved_companies:
                if company and company not in companies:
                    companies.append(company)
                if len(companies) >= limit:
                    return companies
        return companies

    @staticmethod
    def _dedupe_history_capabilities(entries: list[ProductMarketHistoryEntry], *, limit: int) -> list[str]:
        capabilities: list[str] = []
        for entry in entries:
            if entry.capability_text not in capabilities:
                capabilities.append(entry.capability_text)
            if len(capabilities) >= limit:
                return capabilities
        return capabilities

    @staticmethod
    def _dedupe_evidence_refs(entries: list[ProductMarketHistoryEntry], *, limit: int) -> list[dict[str, Any]]:
        evidence_refs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for entry in entries:
            for evidence in entry.evidence_refs:
                url = str(evidence.get("source_url") or "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                evidence_refs.append(evidence)
                if len(evidence_refs) >= limit:
                    return evidence_refs
        return evidence_refs

    def _build_argus_recommendations(self, tenant_id: int) -> list[ArgusRecommendationSummary]:
        if self._product_market is None:
            return []
        rows = self._product_market.get_current_recommendations(tenant_id)
        return [
            ArgusRecommendationSummary(
                recommendation_id=r["id"],
                pattern_observation_id=r.get("pattern_observation_id"),
                owner=r["owner"],
                action=r["action"],
                why_now=r["why_now"],
                urgency=r["urgency"],
                confidence=r.get("confidence"),
                scorecard=r.get("scorecard"),
                evidence_refs=list(r.get("evidence_refs") or []),
                status=r.get("status") or "open",
            )
            for r in rows
        ]

    def _build_demand_signals(self, tenant_id: int) -> list[DemandSignalSummary]:
        if self._product_market is None:
            return []
        rows = self._product_market.get_current_demand_signals(tenant_id)
        return [
            DemandSignalSummary(
                demand_signal_id=r["id"],
                topic=r["topic"],
                metric=r["metric"],
                value=float(r["value"]),
                change_pct=r.get("change_pct"),
                source_label=r["source_label"],
                evidence_refs=list(r.get("evidence_refs") or []),
                argus_plan_context=self._argus_plan_context(r.get("metadata")),
            )
            for r in rows
        ]

    @staticmethod
    def _argus_plan_context(metadata: Any) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        mapping = {
            "argus_capability_key": "capability_key",
            "argus_assessment": "assessment",
            "argus_suggested_filters": "suggested_filters",
            "argus_related_competitors": "related_competitors",
            "argus_why_collect": "why_collect",
            "argus_evidence_urls": "evidence_urls",
        }
        return {
            public_key: metadata[source_key]
            for source_key, public_key in mapping.items()
            if source_key in metadata and metadata[source_key] not in (None, "", [])
        }

    @staticmethod
    def _build_argus_evidence_needs(
        run_history: list[ProductMarketRunHistoryEntry],
        *,
        product_market_run: ProductMarketRunStatus,
    ) -> list[ArgusEvidenceNeedSummary]:
        if not run_history:
            return []
        latest = run_history[0]
        if latest.recommendation_count > 0:
            return []

        needs: list[ArgusEvidenceNeedSummary] = []
        if latest.pattern_count > 0 and latest.demand_signal_count == 0:
            needs.append(
                ArgusEvidenceNeedSummary(
                    evidence_plane="demand",
                    status="missing",
                    severity="blocks_action",
                    title="Demand plane missing",
                    why_needed=_first_matching_limit(
                        latest.confidence_limits,
                        "demand",
                        default=(
                            "Argus found product-market patterns, but no tenant-side demand "
                            "evidence was captured in this run."
                        ),
                    ),
                    blocks=["owner recommendations", "priority ranking", "action promotion"],
                    next_step=(
                        "Upload GA4 / Looker demand export for the current and previous periods."
                    ),
                    related_run_intelligence_id=latest.run_intelligence_id,
                    observed_pattern_count=latest.pattern_count,
                    accepted_input_formats=list(DEMAND_IMPORT_FORMATS),
                    required_fields=list(DEMAND_IMPORT_REQUIRED_FIELDS),
                    operator_surface="CI-OS local admin demand imports",
                    observed_state=DashboardStateBuilder._demand_observed_state(product_market_run),
                    evidence_refs=[],
                )
            )
        if latest.conversation_theme_count > 0 and latest.product_event_count == 0:
            needs.append(
                ArgusEvidenceNeedSummary(
                    evidence_plane="product_muscle",
                    status="missing",
                    severity="blocks_action",
                    title="Product proof missing",
                    why_needed=(
                        "Argus captured market conversation, but no changelog, docs, release, "
                        "pricing, API, or product-surface proof was captured for the run."
                    ),
                    blocks=["feature comparison", "product gap scoring", "action promotion"],
                    next_step=(
                        "Add or repair Scout product-surface sources for changelog, docs, release notes, "
                        "pricing, API docs, and product pages."
                    ),
                    related_run_intelligence_id=latest.run_intelligence_id,
                    observed_pattern_count=latest.pattern_count,
                    evidence_refs=[],
                )
            )
        if latest.product_event_count > 0 and latest.conversation_theme_count == 0:
            needs.append(
                ArgusEvidenceNeedSummary(
                    evidence_plane="conversation",
                    status="missing",
                    severity="limits_priority",
                    title="Conversation plane missing",
                    why_needed=(
                        "Argus captured product proof, but no public GTM, content, executive, or "
                        "market conversation evidence was captured for the run."
                    ),
                    blocks=["narrative-gap scoring", "sales messaging priority"],
                    next_step=(
                        "Add or repair outward conversation sources: blogs, campaigns, news, "
                        "case studies, executive speech, and social surfaces."
                    ),
                    related_run_intelligence_id=latest.run_intelligence_id,
                    observed_pattern_count=latest.pattern_count,
                    evidence_refs=[],
                )
            )
        return needs

    @staticmethod
    def _build_demand_feature_alignment(
        demand_signals: list[DemandSignalSummary],
        feature_matrix: list[FeatureMatrixRow],
    ) -> DemandFeatureAlignmentState:
        if not demand_signals:
            return DemandFeatureAlignmentState()

        feature_rows_by_key: dict[str, list[FeatureMatrixRow]] = {}
        capability_labels: dict[str, str] = {}
        for row in feature_matrix:
            key = DashboardStateBuilder._canonical_capability_key(row.capability_text)
            if not key:
                continue
            feature_rows_by_key.setdefault(key, []).append(row)
            capability_labels.setdefault(key, row.capability_text)

        rows: list[DemandFeatureAlignmentRow] = []
        matched_count = 0
        for signal in demand_signals:
            demand_key = DashboardStateBuilder._demand_capability_key(signal)
            matched_rows = feature_rows_by_key.get(demand_key, [])
            related_companies = DashboardStateBuilder._demand_alignment_companies(matched_rows)
            product_evidence_count = sum(company.evidence_count for company in related_companies)
            demand_evidence_url = DashboardStateBuilder._first_evidence_url(signal.evidence_refs)
            if matched_rows:
                matched_count += 1
                matched_capability = capability_labels[demand_key]
                company_names = [company.company_name for company in related_companies]
                rows.append(
                    DemandFeatureAlignmentRow(
                        demand_signal_id=signal.demand_signal_id,
                        topic=signal.topic,
                        metric=signal.metric,
                        value=signal.value,
                        change_pct=signal.change_pct,
                        source_label=signal.source_label,
                        demand_evidence_url=demand_evidence_url,
                        match_status="matched",
                        matched_capability=matched_capability,
                        related_companies=related_companies,
                        product_evidence_count=product_evidence_count,
                        summary=(
                            f"Audience demand for {signal.topic} maps to {matched_capability}; "
                            f"product proof is captured for "
                            f"{DashboardStateBuilder._human_join(company_names)}."
                        ),
                        next_step="Compare matched product proof before promoting owner recommendations.",
                    )
                )
                continue

            rows.append(
                DemandFeatureAlignmentRow(
                    demand_signal_id=signal.demand_signal_id,
                    topic=signal.topic,
                    metric=signal.metric,
                    value=signal.value,
                    change_pct=signal.change_pct,
                    source_label=signal.source_label,
                    demand_evidence_url=demand_evidence_url,
                    match_status="unmatched",
                    matched_capability=None,
                    related_companies=[],
                    product_evidence_count=0,
                    summary=(
                        f"Audience demand for {signal.topic} is present, but no product "
                        "capability row is mapped to it yet."
                    ),
                    next_step=(
                        "Map this demand topic to a product capability or add Scout product proof "
                        "before Argus promotes an owner action."
                    ),
                )
            )

        unmatched_count = len(rows) - matched_count
        if matched_count == len(rows):
            status = "matched"
        elif matched_count > 0:
            status = "partially_matched"
        else:
            status = "unmatched"
        return DemandFeatureAlignmentState(
            status=status,
            rows=rows,
            signal_count_total=len(rows),
            matched_signal_count=matched_count,
            unmatched_signal_count=unmatched_count,
        )

    @staticmethod
    def _demand_alignment_companies(
        feature_rows: list[FeatureMatrixRow],
        *,
        limit: int = 6,
    ) -> list[DemandFeatureAlignmentCompany]:
        best_by_company: dict[str, FeatureMatrixRow] = {}
        for row in feature_rows:
            company_key = DashboardStateBuilder._normalize_comparison_key(row.company_name)
            existing = best_by_company.get(company_key)
            if existing is None or DashboardStateBuilder._feature_position_sort_key(row) > DashboardStateBuilder._feature_position_sort_key(existing):
                best_by_company[company_key] = row

        rows = sorted(
            best_by_company.values(),
            key=lambda row: (
                0 if row.company_role == "own" else 1,
                -DashboardStateBuilder._feature_position_status_score(row.position_status),
                -len(row.evidence_refs),
                row.company_name.lower(),
            ),
        )
        return [
            DemandFeatureAlignmentCompany(
                company_name=row.company_name,
                company_role=row.company_role or "competitor",
                position_status=row.position_status or "unknown",
                evidence_count=len(row.evidence_refs),
                first_evidence_url=DashboardStateBuilder._first_evidence_url(row.evidence_refs),
            )
            for row in rows[:limit]
        ]

    @staticmethod
    def _canonical_capability_key(value: str) -> str:
        return intelligence_capability_key(value) or DashboardStateBuilder._normalize_comparison_key(value)

    @staticmethod
    def _demand_capability_key(signal: DemandSignalSummary) -> str:
        return intelligence_demand_capability_key(
            signal.topic,
            plan_context=signal.argus_plan_context,
        ) or DashboardStateBuilder._normalize_comparison_key(signal.topic)

    @staticmethod
    def _human_join(values: list[str]) -> str:
        values = [str(value).strip() for value in values if str(value).strip()]
        if not values:
            return "no companies"
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]} and {values[1]}"
        return f"{', '.join(values[:-1])}, and {values[-1]}"

    @staticmethod
    def _demand_observed_state(product_market_run: ProductMarketRunStatus) -> dict[str, Any]:
        observed_state: dict[str, Any] = {
            "demand_plane_status": product_market_run.demand_plane_status,
            "looker_discovered_count": product_market_run.looker_discovered_count,
            "looker_ready_count": product_market_run.looker_ready_count,
            "looker_error_count": product_market_run.looker_error_count,
            "looker_normalized_row_count": product_market_run.looker_normalized_row_count,
            "looker_skipped_row_count": product_market_run.looker_skipped_row_count,
            "looker_archived_count": product_market_run.looker_archived_count,
        }
        if product_market_run.looker_manifest_path:
            observed_state["looker_manifest_path"] = product_market_run.looker_manifest_path
        return observed_state

    @staticmethod
    def _build_intelligence_spine(
        *,
        product_market_run: ProductMarketRunStatus,
        product_market_patterns: list[ProductMarketPatternSummary],
        product_market_history: list[ProductMarketHistoryEntry],
        product_market_run_history: list[ProductMarketRunHistoryEntry],
        argus_recommendations: list[ArgusRecommendationSummary],
        demand_signals: list[DemandSignalSummary],
        demand_feature_alignment: DemandFeatureAlignmentState,
        argus_evidence_needs: list[ArgusEvidenceNeedSummary],
        feature_matrix: list[FeatureMatrixRow],
    ) -> IntelligenceSpine:
        latest_run = product_market_run_history[0] if product_market_run_history else None
        brief = product_market_run.intelligence_brief if isinstance(product_market_run.intelligence_brief, dict) else {}
        top_insight = (
            latest_run.top_insight
            if latest_run is not None
            else str(brief.get("top_insight") or "No Argus intelligence read has been stored yet.")
        )
        primary_action = (
            latest_run.primary_action
            if latest_run is not None
            else brief.get("primary_action")
        )
        verdict = (
            latest_run.verdict
            if latest_run is not None
            else str(product_market_run.runner_verdict or brief.get("verdict") or product_market_run.status)
        )
        confidence_limits = (
            latest_run.confidence_limits
            if latest_run is not None
            else [str(item) for item in (brief.get("confidence_limits") or [])]
        )

        product_event_count = DashboardStateBuilder._first_nonzero_int(
            latest_run.product_event_count if latest_run is not None else 0,
            product_market_run.conversion_diagnostics.get("product_event_count"),
            len(feature_matrix),
        )
        conversation_theme_count = DashboardStateBuilder._first_nonzero_int(
            latest_run.conversation_theme_count if latest_run is not None else 0,
            product_market_run.conversion_diagnostics.get("conversation_theme_count"),
            len(product_market_patterns),
        )
        demand_signal_count = DashboardStateBuilder._first_nonzero_int(
            latest_run.demand_signal_count if latest_run is not None else 0,
            product_market_run.conversion_diagnostics.get("demand_signal_count"),
            demand_feature_alignment.signal_count_total,
            len(demand_signals),
        )
        pattern_count = DashboardStateBuilder._first_nonzero_int(
            latest_run.pattern_count if latest_run is not None else 0,
            product_market_run.conversion_diagnostics.get("pattern_count"),
            len(product_market_patterns),
        )
        recommendation_count = DashboardStateBuilder._first_nonzero_int(
            latest_run.recommendation_count if latest_run is not None else 0,
            len(argus_recommendations),
        )
        feature_position_count = DashboardStateBuilder._first_nonzero_int(
            product_market_run.conversion_diagnostics.get("feature_position_count"),
            len(feature_matrix),
        )

        product_evidence = DashboardStateBuilder._dedupe_any_evidence_refs(
            [*(row.evidence_refs for row in feature_matrix), *(row.evidence_refs for row in product_market_patterns)],
            limit=8,
        )
        conversation_evidence = DashboardStateBuilder._dedupe_any_evidence_refs(
            [*(row.evidence_refs for row in product_market_patterns), *(row.evidence_refs for row in product_market_history)],
            limit=8,
        )
        demand_evidence = DashboardStateBuilder._dedupe_any_evidence_refs(
            [*(row.evidence_refs for row in demand_signals)],
            limit=8,
        )
        demand_status = product_market_run.demand_plane_status
        if demand_signal_count > 0 and demand_status in {"missing", "not_recorded"}:
            demand_status = "present"
        if any(need.evidence_plane == "demand" and need.status == "missing" for need in argus_evidence_needs):
            demand_status = "missing"

        planes = [
            IntelligencePlaneSummary(
                plane="product_reality",
                label="Product reality",
                status="present" if product_event_count > 0 or feature_position_count > 0 else "missing",
                signal_count=product_event_count,
                evidence_count=len(product_evidence),
                summary=DashboardStateBuilder._plane_summary(
                    present=product_event_count > 0 or feature_position_count > 0,
                    present_text=(
                        f"{product_event_count} product event"
                        f"{'' if product_event_count == 1 else 's'} and "
                        f"{feature_position_count} feature position"
                        f"{'' if feature_position_count == 1 else 's'} support the read."
                    ),
                    missing_text="No changelog, docs, release, pricing, API, or product-page proof supports this read yet.",
                ),
                evidence_refs=product_evidence,
            ),
            IntelligencePlaneSummary(
                plane="market_conversation",
                label="Market conversation",
                status="present" if conversation_theme_count > 0 else "missing",
                signal_count=conversation_theme_count,
                evidence_count=len(conversation_evidence),
                summary=DashboardStateBuilder._plane_summary(
                    present=conversation_theme_count > 0,
                    present_text=(
                        f"{conversation_theme_count} conversation theme"
                        f"{'' if conversation_theme_count == 1 else 's'} support the read."
                    ),
                    missing_text="No public GTM, content, executive, analyst, or market conversation proof supports this read yet.",
                ),
                evidence_refs=conversation_evidence,
            ),
            IntelligencePlaneSummary(
                plane="audience_demand",
                label="Audience demand",
                status=DashboardStateBuilder._normalized_demand_spine_status(demand_status),
                signal_count=demand_signal_count,
                evidence_count=len(demand_evidence),
                summary=DashboardStateBuilder._plane_summary(
                    present=demand_signal_count > 0,
                    present_text=(
                        f"{demand_signal_count} tenant-side demand signal"
                        f"{'' if demand_signal_count == 1 else 's'} support the read."
                    ),
                    missing_text="No GA / Looker demand proof supports this read yet.",
                ),
                evidence_refs=demand_evidence,
            ),
        ]

        blocked_actions = DashboardStateBuilder._spine_blocked_actions(argus_evidence_needs)
        leading_entities = DashboardStateBuilder._spine_leading_entities(
            product_market_patterns=product_market_patterns,
            product_market_history=product_market_history,
            feature_matrix=feature_matrix,
        )
        leading_capabilities = DashboardStateBuilder._spine_leading_capabilities(
            product_market_patterns=product_market_patterns,
            product_market_history=product_market_history,
            feature_matrix=feature_matrix,
            demand_signals=demand_signals,
        )
        evidence_urls = DashboardStateBuilder._spine_evidence_urls(
            run=latest_run,
            recommendations=argus_recommendations,
            planes=planes,
            limit=10,
        )
        can_recommend = bool(argus_recommendations) and not blocked_actions
        return IntelligenceSpine(
            verdict=verdict or "not_recorded",
            top_insight=top_insight,
            primary_action=primary_action,
            confidence_limits=confidence_limits,
            planes=planes,
            pattern_count=pattern_count,
            recommendation_count=recommendation_count,
            feature_position_count=feature_position_count,
            evidence_need_count=len(argus_evidence_needs),
            leading_entities=leading_entities,
            leading_capabilities=leading_capabilities,
            evidence_urls=evidence_urls,
            blocked_actions=blocked_actions,
            can_recommend=can_recommend,
            next_operator_action=DashboardStateBuilder._spine_next_operator_action(
                can_recommend=can_recommend,
                primary_action=primary_action,
                evidence_needs=argus_evidence_needs,
            ),
        )

    @staticmethod
    def _first_nonzero_int(*values: object) -> int:
        for value in values:
            try:
                number = int(value or 0)
            except (TypeError, ValueError):
                number = 0
            if number > 0:
                return number
        return 0

    @staticmethod
    def _plane_summary(*, present: bool, present_text: str, missing_text: str) -> str:
        return present_text if present else missing_text

    @staticmethod
    def _normalized_demand_spine_status(status: str) -> str:
        if status == "processed":
            return "present"
        if status in {"degraded", "error", "missing", "empty", "not_recorded"}:
            return status
        return "present" if status else "missing"

    @staticmethod
    def _dedupe_any_evidence_refs(groups: list[list[dict[str, Any]]], *, limit: int) -> list[dict[str, Any]]:
        evidence_refs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for group in groups:
            for evidence in group:
                url = str(evidence.get("source_url") or "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                evidence_refs.append(evidence)
                if len(evidence_refs) >= limit:
                    return evidence_refs
        return evidence_refs

    @staticmethod
    def _spine_leading_entities(
        *,
        product_market_patterns: list[ProductMarketPatternSummary],
        product_market_history: list[ProductMarketHistoryEntry],
        feature_matrix: list[FeatureMatrixRow],
    ) -> list[str]:
        entities: list[str] = []
        for pattern in [*product_market_patterns, *product_market_history]:
            for company in pattern.involved_companies:
                if company and company not in entities:
                    entities.append(company)
        for row in feature_matrix:
            if row.company_name and row.company_name not in entities:
                entities.append(row.company_name)
        return entities[:8]

    @staticmethod
    def _spine_leading_capabilities(
        *,
        product_market_patterns: list[ProductMarketPatternSummary],
        product_market_history: list[ProductMarketHistoryEntry],
        feature_matrix: list[FeatureMatrixRow],
        demand_signals: list[DemandSignalSummary],
    ) -> list[str]:
        capabilities: list[str] = []
        for value in [
            *(row.capability_text for row in product_market_patterns),
            *(row.capability_text for row in product_market_history),
            *(row.capability_text for row in feature_matrix),
            *(row.topic for row in demand_signals),
        ]:
            if value and value not in capabilities:
                capabilities.append(value)
        return capabilities[:8]

    @staticmethod
    def _spine_blocked_actions(evidence_needs: list[ArgusEvidenceNeedSummary]) -> list[str]:
        blocked: list[str] = []
        for need in evidence_needs:
            if need.severity not in {"blocks_action", "limits_priority"}:
                continue
            for action in need.blocks:
                if action not in blocked:
                    blocked.append(action)
        return blocked

    @staticmethod
    def _spine_evidence_urls(
        *,
        run: ProductMarketRunHistoryEntry | None,
        recommendations: list[ArgusRecommendationSummary],
        planes: list[IntelligencePlaneSummary],
        limit: int,
    ) -> list[str]:
        urls: list[str] = []
        for url in (run.evidence_urls if run is not None else []):
            if url and url not in urls:
                urls.append(url)
        for recommendation in recommendations:
            for evidence in recommendation.evidence_refs:
                url = str(evidence.get("source_url") or "")
                if url and url not in urls:
                    urls.append(url)
                if len(urls) >= limit:
                    return urls
        for plane in planes:
            for evidence in plane.evidence_refs:
                url = str(evidence.get("source_url") or "")
                if url and url not in urls:
                    urls.append(url)
                if len(urls) >= limit:
                    return urls
        return urls[:limit]

    @staticmethod
    def _spine_next_operator_action(
        *,
        can_recommend: bool,
        primary_action: str | None,
        evidence_needs: list[ArgusEvidenceNeedSummary],
    ) -> str:
        if evidence_needs:
            return evidence_needs[0].next_step
        if can_recommend:
            return f"Argus has enough evidence; safe to promote this action: {primary_action or 'review the top recommendation.'}"
        return "Inspect the evidence planes before promoting this read into owner work."

    def _build_feature_matrix(self, tenant_id: int) -> list[FeatureMatrixRow]:
        if self._product_market is None:
            return []
        rows = self._product_market.get_feature_matrix(tenant_id)
        return [
            FeatureMatrixRow(
                capability_text=r["capability_text"],
                company_name=r["company_name"],
                company_role=r["company_role"],
                position_status=r["position_status"],
                summary=r.get("summary"),
                confidence=r.get("confidence"),
                evidence_refs=list(r.get("evidence_refs") or []),
            )
            for r in rows
        ]

    @staticmethod
    def _build_product_feature_comparison(
        feature_matrix: list[FeatureMatrixRow],
        monitored_competitors: list[MonitoredCompetitor],
    ) -> ProductFeatureComparisonState:
        if not feature_matrix:
            return ProductFeatureComparisonState(
                row_limit=FEATURE_COMPARISON_ROW_LIMIT,
                company_limit=FEATURE_COMPARISON_COMPANY_LIMIT,
            )

        company_meta: dict[str, dict[str, Any]] = {}
        company_order: dict[str, int] = {}
        capability_order: dict[str, int] = {}
        capability_labels: dict[str, str] = {}
        positions_by_capability: dict[str, dict[str, FeatureMatrixRow]] = {}

        for row in feature_matrix:
            capability_key = DashboardStateBuilder._normalize_comparison_key(row.capability_text)
            company_key = DashboardStateBuilder._normalize_comparison_key(row.company_name)
            capability_order.setdefault(capability_key, len(capability_order))
            company_order.setdefault(company_key, len(company_order))
            capability_labels.setdefault(capability_key, row.capability_text)
            meta = company_meta.setdefault(
                company_key,
                {
                    "company_name": row.company_name,
                    "company_role": row.company_role or "competitor",
                    "active_source_count": 0,
                    "evidence_count": 0,
                    "has_product_evidence": False,
                },
            )
            if row.company_role == "own":
                meta["company_role"] = "own"
            evidence_count = len(row.evidence_refs)
            meta["evidence_count"] = int(meta["evidence_count"]) + evidence_count
            meta["has_product_evidence"] = True

            positions = positions_by_capability.setdefault(capability_key, {})
            existing = positions.get(company_key)
            if existing is None or DashboardStateBuilder._feature_position_sort_key(row) > DashboardStateBuilder._feature_position_sort_key(existing):
                positions[company_key] = row

        for competitor in monitored_competitors:
            company_key = DashboardStateBuilder._normalize_comparison_key(competitor.competitor_name)
            company_order.setdefault(company_key, len(company_order))
            meta = company_meta.setdefault(
                company_key,
                {
                    "company_name": competitor.competitor_name,
                    "company_role": "competitor",
                    "active_source_count": 0,
                    "evidence_count": 0,
                    "has_product_evidence": False,
                },
            )
            meta["active_source_count"] = max(
                int(meta.get("active_source_count") or 0),
                int(competitor.active_source_count or 0),
            )

        sorted_company_keys = sorted(
            company_meta,
            key=lambda key: (
                0 if company_meta[key].get("company_role") == "own" else 1,
                0 if company_meta[key].get("has_product_evidence") else 1,
                -int(company_meta[key].get("evidence_count") or 0),
                company_order.get(key, 9999),
                str(company_meta[key].get("company_name") or ""),
            ),
        )
        selected_company_keys = sorted_company_keys[:FEATURE_COMPARISON_COMPANY_LIMIT]
        companies = [
            ProductFeatureComparisonCompany(
                company_name=str(company_meta[key]["company_name"]),
                company_role=str(company_meta[key].get("company_role") or "competitor"),
                active_source_count=int(company_meta[key].get("active_source_count") or 0),
                has_product_evidence=bool(company_meta[key].get("has_product_evidence")),
            )
            for key in selected_company_keys
        ]

        sorted_capability_keys = sorted(
            positions_by_capability,
            key=lambda key: (
                -DashboardStateBuilder._capability_proven_count(positions_by_capability[key]),
                -DashboardStateBuilder._capability_evidence_count(positions_by_capability[key]),
                capability_order.get(key, 9999),
                capability_labels.get(key, ""),
            ),
        )

        comparison_rows: list[ProductFeatureComparisonRow] = []
        for capability_key in sorted_capability_keys[:FEATURE_COMPARISON_ROW_LIMIT]:
            capability_text = capability_labels[capability_key]
            positions = positions_by_capability[capability_key]
            cells: list[ProductFeatureComparisonCell] = []
            proven_count = 0
            claimed_count = 0
            unknown_count = 0
            evidence_count = 0
            for company_key in selected_company_keys:
                meta = company_meta[company_key]
                company_name = str(meta["company_name"])
                row = positions.get(company_key)
                if row is None:
                    unknown_count += 1
                    cells.append(
                        ProductFeatureComparisonCell(
                            company_name=company_name,
                            position_status="unknown",
                            summary=(
                                f"No product proof captured for {company_name} on "
                                f"{capability_text} in this evidence set."
                            ),
                            evidence_count=0,
                        )
                    )
                    continue

                status = row.position_status or "unknown"
                status_score = DashboardStateBuilder._feature_position_status_score(status)
                if status_score >= 3:
                    proven_count += 1
                elif status_score >= 2:
                    claimed_count += 1
                else:
                    unknown_count += 1
                row_evidence_count = len(row.evidence_refs)
                evidence_count += row_evidence_count
                cells.append(
                    ProductFeatureComparisonCell(
                        company_name=company_name,
                        position_status=status,
                        summary=row.summary or f"{company_name} has {status} evidence for {capability_text}.",
                        confidence=row.confidence,
                        evidence_count=row_evidence_count,
                        first_evidence_url=DashboardStateBuilder._first_evidence_url(row.evidence_refs),
                    )
                )
            comparison_rows.append(
                ProductFeatureComparisonRow(
                    capability_text=capability_text,
                    cells=cells,
                    proven_count=proven_count,
                    claimed_count=claimed_count,
                    unknown_count=unknown_count,
                    evidence_count=evidence_count,
                )
            )

        return ProductFeatureComparisonState(
            companies=companies,
            rows=comparison_rows,
            row_count_total=len(sorted_capability_keys),
            company_count_total=len(sorted_company_keys),
            row_limit=FEATURE_COMPARISON_ROW_LIMIT,
            company_limit=FEATURE_COMPARISON_COMPANY_LIMIT,
            capped=(
                len(sorted_capability_keys) > FEATURE_COMPARISON_ROW_LIMIT
                or len(sorted_company_keys) > FEATURE_COMPARISON_COMPANY_LIMIT
            ),
        )

    @staticmethod
    def _normalize_comparison_key(value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _feature_position_sort_key(row: FeatureMatrixRow) -> tuple[int, int, float]:
        return (
            DashboardStateBuilder._feature_position_status_score(row.position_status),
            len(row.evidence_refs),
            float(row.confidence or 0.0),
        )

    @staticmethod
    def _feature_position_status_score(status: str) -> int:
        normalized = str(status or "").strip().lower()
        if normalized in {"proven", "has_proof", "shipped", "released"}:
            return 3
        if normalized in {"claimed", "positioned", "announced"}:
            return 2
        if normalized in {"mentioned", "partial", "watch"}:
            return 1
        return 0

    @staticmethod
    def _capability_proven_count(positions: dict[str, FeatureMatrixRow]) -> int:
        return sum(
            1
            for row in positions.values()
            if DashboardStateBuilder._feature_position_status_score(row.position_status) >= 3
        )

    @staticmethod
    def _capability_evidence_count(positions: dict[str, FeatureMatrixRow]) -> int:
        return sum(len(row.evidence_refs) for row in positions.values())

    @staticmethod
    def _first_evidence_url(evidence_refs: list[dict[str, Any]]) -> Optional[str]:
        for ref in evidence_refs:
            url = ref.get("source_url") or ref.get("url")
            if url:
                return str(url)
        return None

    @staticmethod
    def _evidence_to_competitor_map(deltas: list[dict]) -> dict[Any, tuple[Any, str]]:
        """Maps each evidence URL a material delta cites to the competitor it
        was cited for. Real backend attribution (not fabricated): a
        prescription carries no competitor_id of its own
        (cios.prescribe.types.Prescription is tenant-scoped only), so the
        only truthful way to attribute a play to a competitor is to trace
        its own grounding evidence URLs back to whichever signal(s) cited
        that same URL. Built once per build() call from every delta this
        cycle supplied (not just the merged/ranked cards), so a prescription
        grounded in a duplicate-cluster member's evidence still resolves."""
        mapping: dict[Any, tuple[Any, str]] = {}
        for d in deltas:
            competitor_id = d.get("competitor_id")
            competitor_name = d.get("competitor_name") or f"Competitor {competitor_id}"
            for url in d.get("evidence_ids") or []:
                # First delta to cite a URL wins the attribution -- stable,
                # deterministic, and matches the merge rule elsewhere in this
                # module (best/first member's fields win over later dupes).
                mapping.setdefault(url, (competitor_id, competitor_name))
        return mapping

    @staticmethod
    def _attribute_competitor(
        evidence_urls: list[str], evidence_to_competitor: dict[Any, tuple[Any, str]]
    ) -> tuple[Optional[Any], Optional[str]]:
        for url in evidence_urls:
            match = evidence_to_competitor.get(url)
            if match is not None:
                return match
        # No traceable overlap: an honest, unattributed play. Never guess.
        return None, None

    def _build_build_status(self) -> BuildStatus:
        if self._build_status is None:
            return BuildStatus(environment="unknown", last_error="no build-status provider injected")
        raw = self._build_status.get_build_status()
        if raw is None:
            return BuildStatus(environment="unknown", last_error="build-status provider returned no data")
        from .types import ServiceHealth

        return BuildStatus(
            build_id=raw.get("build_id"),
            git_sha=raw.get("git_sha"),
            deployed_at=raw.get("deployed_at"),
            environment=raw.get("environment"),
            services=[ServiceHealth(**s) for s in raw.get("services", [])],
            last_error=raw.get("last_error"),
        )


def _action_cue(level: AttentionLevel, recommended_action: Optional[str]) -> str:
    """Per UX spec Attention Barometer rule: every row must include an action
    cue explaining what to watch/monitor, not a bare score."""
    if recommended_action:
        return recommended_action
    return {
        AttentionLevel.ACT_NOW: "Act now: review this signal before the next brief.",
        AttentionLevel.WATCH: "Watch: confirm before it changes messaging or pricing guidance.",
        AttentionLevel.MONITOR: "Monitor: no action yet, keep this on the radar.",
        AttentionLevel.NORMAL: "Normal: no attention needed this cycle.",
    }[level]
