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

from typing import Optional, Protocol

from .types import (
    ArgusRead,
    AttentionLevel,
    BuildStatus,
    CompetitorSignalCard,
    CoverageBarometer,
    DashboardState,
    LaneStatus,
    LivingThesis,
    PrescriptionSummary,
    ReportHistoryEntry,
    RunHealth,
    SuppressedSignalEntry,
    attention_level_for_score,
)

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
    ) -> None:
        self._signals = signals
        self._theses = theses
        self._coverage = coverage
        self._runs = runs
        self._build_status = build_status
        self._report_history = report_history
        self._suppressed_signals = suppressed_signals
        self._prescriptions = prescriptions

    def build(self, *, tenant_id: int, cadence: str) -> DashboardState:
        coverage = self._build_coverage(tenant_id)
        deltas = self._signals.get_material_deltas(tenant_id)
        cards = self._build_competitor_cards(deltas)
        theses = self._build_theses(tenant_id)
        run = self._runs.get_latest_run(tenant_id, cadence) or {}
        run_health = self._build_run_health(run, source_count=len(deltas))
        argus_read = ArgusRead(**(run.get("argus_read") or {}))
        build_status = self._build_build_status()
        report_history = self._build_report_history(tenant_id)
        suppressed_signals = self._build_suppressed_signals(tenant_id)
        prescriptions = self._build_prescriptions(tenant_id)

        return DashboardState(
            tenant_id=tenant_id,
            cadence=cadence,
            argus_read=argus_read,
            coverage=coverage,
            competitor_cards=cards,
            theses=theses,
            run_health=run_health,
            build_status=build_status,
            report_history=report_history,
            suppressed_signals=suppressed_signals,
            prescriptions=prescriptions,
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
        cards: list[CompetitorSignalCard] = []
        for d in deltas:
            materiality = float(d.get("materiality_score") or 0.0)
            # attention_score is presented 0-100 (UX spec); materiality_score
            # is stored 0-1 (semantic_deltas.materiality_score numeric(5,4)).
            attention_score = round(materiality * 100, 1)
            level = attention_level_for_score(materiality)
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
                )
            )
        # materiality-before-urgency: highest attention first, deterministic
        # tiebreak on competitor_id so repeated builds don't reorder ties.
        cards.sort(key=lambda c: (-c.attention_score, c.competitor_id))
        return cards

    def _build_theses(self, tenant_id: int) -> list[LivingThesis]:
        rows = self._theses.get_active_theses(tenant_id)
        theses: list[LivingThesis] = []
        for r in rows:
            theses.append(
                LivingThesis(
                    thesis_id=r["id"],
                    competitor_id=r["competitor_id"],
                    competitor_name=r.get("competitor_name"),
                    thesis=r["thesis"],
                    status=r.get("status", "active"),
                    confidence=r.get("confidence"),
                    supporting_delta_count=len(r.get("supporting_delta_ids") or []),
                    contradicting_delta_count=len(r.get("contradicting_delta_ids") or []),
                    updated_at=r.get("updated_at"),
                )
            )
        return theses

    def _build_run_health(self, run: dict, *, source_count: int) -> RunHealth:
        return RunHealth(
            run_id=run.get("run_id"),
            report_id=run.get("report_id"),
            generated_at=run.get("generated_at"),
            model_tier=run.get("model_tier"),
            source_family_count=run.get("source_family_count"),
            material_delta_count=source_count,
            delivery_status=run.get("delivery_status"),
            quality_review_status=run.get("quality_review_status"),
        )

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
                html_path=r.get("html_path"),
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

    def _build_prescriptions(self, tenant_id: int) -> list[PrescriptionSummary]:
        # No provider injected is not an error -- the prescription engine's
        # DB wiring is a tracked backlog item, not a schema table yet. The
        # cockpit renders the honest "no plays yet" empty state per lens
        # rather than inventing one.
        if self._prescriptions is None:
            return []
        rows = self._prescriptions.get_current_prescriptions(tenant_id)
        return [
            PrescriptionSummary(
                title=r["title"],
                team=r["team"],
                play=list(r.get("play") or []),
                urgency_window=r["urgency_window"],
                expected_effect=r.get("expected_effect"),
                evidence_urls=list((r.get("grounding") or {}).get("evidence_urls") or r.get("evidence_urls") or []),
            )
            for r in rows
        ]

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
