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
        prescriptions = self._build_prescriptions(tenant_id, deltas)

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
        clusters = cluster_by_similarity(
            rows,
            group_key=lambda r: r.get("competitor_id"),
            text=lambda r: r.get("thesis") or "",
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
