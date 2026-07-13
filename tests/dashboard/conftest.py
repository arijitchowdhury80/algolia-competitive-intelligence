"""In-memory fakes for the dashboard state builder Protocols."""

from __future__ import annotations

from typing import Any, Optional


class FakeSignalsRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_material_deltas(self, tenant_id: int) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))


class FakeThesesRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_active_theses(self, tenant_id: int) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))


class FakeCoverageRepository:
    def __init__(self, by_tenant: dict[int, Optional[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_latest_coverage(self, tenant_id: int) -> Optional[dict]:
        return self._by_tenant.get(tenant_id)


class FakeRunRepository:
    def __init__(self, by_tenant: dict[int, dict]) -> None:
        self._by_tenant = by_tenant

    def get_latest_run(self, tenant_id: int, cadence: str) -> Optional[dict]:
        return self._by_tenant.get(tenant_id)


class FakeBuildStatusProvider:
    def __init__(self, status: Optional[dict]) -> None:
        self._status = status

    def get_build_status(self) -> Optional[dict]:
        return self._status


class FakeReportHistoryRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_recent_reports(self, tenant_id: int, limit: int = 10) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))[:limit]


class FakeSuppressedSignalsRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_recent_suppressed(self, tenant_id: int, limit: int = 10) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))[:limit]


class FakePrescriptionsRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_current_prescriptions(self, tenant_id: int) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))


class FakeMonitoredCompetitorsRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_monitored_competitors(self, tenant_id: int) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))


class FakeSourceHealthRepository:
    def __init__(self, by_tenant: dict[int, list[dict]]) -> None:
        self._by_tenant = by_tenant

    def get_source_health(self, tenant_id: int) -> list[dict]:
        return list(self._by_tenant.get(tenant_id, []))


class FakeProductMarketRepository:
    def __init__(
        self,
        *,
        patterns: dict[int, list[dict]] | None = None,
        recommendations: dict[int, list[dict]] | None = None,
        demand_signals: dict[int, list[dict]] | None = None,
        feature_positions: dict[int, list[dict]] | None = None,
        history: dict[int, list[dict]] | None = None,
        run_history: dict[int, list[dict]] | None = None,
    ) -> None:
        self._patterns = patterns or {}
        self._recommendations = recommendations or {}
        self._demand_signals = demand_signals or {}
        self._feature_positions = feature_positions or {}
        self._history = history or {}
        self._run_history = run_history or {}

    def get_current_patterns(self, tenant_id: int) -> list[dict]:
        return list(self._patterns.get(tenant_id, []))

    def get_current_recommendations(self, tenant_id: int) -> list[dict]:
        return list(self._recommendations.get(tenant_id, []))

    def get_current_demand_signals(self, tenant_id: int) -> list[dict]:
        return list(self._demand_signals.get(tenant_id, []))

    def get_feature_matrix(self, tenant_id: int) -> list[dict]:
        return list(self._feature_positions.get(tenant_id, []))

    def get_pattern_history(self, tenant_id: int, days: int = 30, limit: int = 100) -> list[dict]:
        return list(self._history.get(tenant_id, []))[:limit]

    def get_latest_run_intelligence(self, tenant_id: int, limit: int = 10) -> list[dict]:
        return list(self._run_history.get(tenant_id, []))[:limit]


def report_row(
    *,
    id: int = 1,
    report_date=None,
    cadence: str = "daily",
    title: str = "Argus daily brief",
    summary: str = "No material signal recorded.",
    status: str = "rendered",
    html_path: Optional[str] = "archive/2026-07-08.html",
) -> dict:
    from datetime import date

    return {
        "id": id,
        "report_date": report_date or date(2026, 7, 8),
        "cadence": cadence,
        "title": title,
        "summary": summary,
        "status": status,
        "html_path": html_path,
    }


def suppressed_row(
    *,
    id: int = 1,
    reason: str = "Below materiality threshold",
    finding_ids: Optional[list[Any]] = None,
    suppressed_at=None,
    notes: Optional[str] = None,
) -> dict:
    return {
        "id": id,
        "reason": reason,
        "finding_ids": finding_ids if finding_ids is not None else [101, 102],
        "suppressed_at": suppressed_at,
        "notes": notes,
    }


def full_coverage(*, lanes: Optional[list[str]] = None) -> dict:
    lanes = lanes or ["news", "social", "pricing", "product", "exec_speech"]
    return {
        "lanes": [{"lane": lane, "ran": True, "error": None} for lane in lanes],
        "coverage_score": 1.0,
        "false_negative_audit_status": "clean",
        "missing_source_families": [],
    }


def broken_coverage(*, missing: str = "pricing") -> dict:
    return {
        "lanes": [
            {"lane": "news", "ran": True, "error": None},
            {"lane": missing, "ran": False, "error": "credential expired"},
        ],
        "coverage_score": 0.5,
        "false_negative_audit_status": "at_risk",
        "missing_source_families": [missing],
    }


def delta(
    *,
    id: int = 1,
    competitor_id: int = 1,
    competitor_name: str = "Constructor.io",
    materiality_score: float = 0.8,
    confidence: float = 0.7,
    recommended_action: Optional[str] = "Brief Sales on the pricing shift.",
    evidence_ids: Optional[list[Any]] = None,
) -> dict:
    return {
        "id": id,
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "delta_type": "pricing",
        "materiality_score": materiality_score,
        "what_changed": "Entry tier price dropped 20%.",
        "why_it_matters": "Undercuts our mid-market motion.",
        "recommended_action": recommended_action,
        "confidence": confidence,
        "evidence_ids": evidence_ids if evidence_ids is not None else ["https://rival.com/pricing"],
        "thesis_id": None,
    }


def thesis(
    *,
    id: int = 1,
    competitor_id: int = 1,
    competitor_name: str = "Constructor.io",
    text: str = "Constructor is moving downmarket on price.",
    status: str = "active",
    confidence: float = 0.6,
    supporting: int = 2,
    contradicting: int = 0,
) -> dict:
    return {
        "id": id,
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "thesis": text,
        "status": status,
        "confidence": confidence,
        "supporting_delta_ids": list(range(supporting)),
        "contradicting_delta_ids": list(range(contradicting)),
        "updated_at": None,
    }


def prescription_row(
    *,
    title: str = "Brief sales on the pricing shift",
    team: str = "Sales Enablement",
    play: Optional[list[str]] = None,
    urgency_window: str = "act_now",
    expected_effect: str = "Sales stops improvising the response.",
    evidence_urls: Optional[list[str]] = None,
    effort: str = "S",
    materiality_score: float = 0.8,
) -> dict:
    return {
        "title": title,
        "team": team,
        "play": play if play is not None else ["Send a Slack summary", "Add a battlecard note"],
        "urgency_window": urgency_window,
        "expected_effect": expected_effect,
        "evidence_urls": evidence_urls if evidence_urls is not None else ["https://rival.com/pricing"],
        "effort": effort,
        "materiality_score": materiality_score,
    }


def monitored_competitor_row(
    *,
    competitor_id: int = 1,
    competitor_name: str = "Constructor.io",
    domain: str = "constructor.com",
    category: str = "commerce search",
    status: str = "active",
    source_count: int = 3,
    active_source_count: int = 3,
    failed_source_count: int = 0,
    last_checked_at=None,
    checked_today: bool = True,
    material_signal_count: int = 0,
    last_material_signal_at=None,
    latest_movement_summary: str | None = None,
    monitored_sources: list[dict] | None = None,
) -> dict:
    return {
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "domain": domain,
        "category": category,
        "status": status,
        "source_count": source_count,
        "active_source_count": active_source_count,
        "failed_source_count": failed_source_count,
        "last_checked_at": last_checked_at,
        "checked_today": checked_today,
        "material_signal_count": material_signal_count,
        "last_material_signal_at": last_material_signal_at,
        "latest_movement_summary": latest_movement_summary,
        "monitored_sources": monitored_sources if monitored_sources is not None else [],
    }


def source_health_row(
    *,
    source_id: int = 10,
    competitor_id: int = 1,
    competitor_name: str = "Constructor.io",
    source_family: str = "blog",
    url: str = "https://constructor.com/blog",
    status: str = "active",
    latest_event_type: str | None = "ok",
    http_status: int | None = 200,
    detail: str | None = None,
    checked_at=None,
) -> dict:
    return {
        "source_id": source_id,
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "source_family": source_family,
        "url": url,
        "status": status,
        "latest_event_type": latest_event_type,
        "http_status": http_status,
        "detail": detail,
        "checked_at": checked_at,
    }


def product_market_pattern_row(
    *,
    id: int = 1,
    pattern_type: str = "own_narrative_gap",
    capability_text: str = "agentic product discovery",
    summary: str = "Constructor is shipping and saying agentic product discovery while Algolia has proof but weaker narrative.",
    involved_companies: list[str] | None = None,
    confidence: float = 0.78,
    evidence_refs: list[dict] | None = None,
) -> dict:
    return {
        "id": id,
        "pattern_type": pattern_type,
        "capability_text": capability_text,
        "summary": summary,
        "involved_companies": involved_companies if involved_companies is not None else ["Algolia", "Constructor"],
        "confidence": confidence,
        "evidence_refs": evidence_refs
        if evidence_refs is not None
        else [{"source_url": "https://constructor.com/changelog", "method": "scout_changelog"}],
    }


def product_market_history_row(
    *,
    id: int = 1,
    pattern_type: str = "own_narrative_gap",
    capability_text: str = "agentic product discovery",
    summary: str = "Constructor's agentic product discovery pressure persisted across the week.",
    involved_companies: list[str] | None = None,
    confidence: float = 0.78,
    evidence_refs: list[dict] | None = None,
    created_at=None,
) -> dict:
    from datetime import datetime, timezone

    return {
        "id": id,
        "pattern_type": pattern_type,
        "capability_text": capability_text,
        "summary": summary,
        "involved_companies": involved_companies if involved_companies is not None else ["Algolia", "Constructor"],
        "confidence": confidence,
        "evidence_refs": evidence_refs
        if evidence_refs is not None
        else [{"source_url": "https://constructor.com/changelog", "method": "scout_changelog"}],
        "created_at": created_at or datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
    }


def product_market_run_history_row(
    *,
    id: int = 1,
    verdict: str = "watch",
    top_insight: str = "Constructor moved, but coverage learning held the action.",
    primary_action: str | None = None,
    evidence_urls: list[str] | None = None,
    confidence_limits: list[str] | None = None,
    created_at=None,
    product_event_count: int = 2,
    conversation_theme_count: int = 1,
    demand_signal_count: int = 1,
    pattern_count: int = 1,
    recommendation_count: int = 0,
    learning_instruction_count: int = 1,
    learning_instruction_improvement_ids: list[int] | None = None,
) -> dict:
    from datetime import datetime, timezone

    return {
        "id": id,
        "verdict": verdict,
        "intelligence_brief": {
            "verdict": verdict,
            "top_insight": top_insight,
            "primary_action": primary_action,
            "watchlist": ["Re-audit Coveo before restoring Constructor priority."],
            "evidence_urls": evidence_urls if evidence_urls is not None else ["https://constructor.com/changelog"],
            "confidence_limits": confidence_limits
            if confidence_limits is not None
            else ["Coverage learning gate was active."],
            "next_questions": ["Did Coveo publish a matching release?"],
        },
        "product_event_count": product_event_count,
        "conversation_theme_count": conversation_theme_count,
        "demand_signal_count": demand_signal_count,
        "pattern_count": pattern_count,
        "recommendation_count": recommendation_count,
        "learning_instruction_count": learning_instruction_count,
        "learning_instruction_improvement_ids": learning_instruction_improvement_ids
        if learning_instruction_improvement_ids is not None
        else [202],
        "created_at": created_at or datetime(2026, 7, 10, 5, 13, tzinfo=timezone.utc),
    }


def argus_recommendation_row(
    *,
    id: int = 1,
    pattern_observation_id: int = 1,
    owner: str = "PMM",
    action: str = "Create the agentic product discovery narrative.",
    why_now: str = "Competitor product proof, conversation, and demand align.",
    urgency: str = "this_week",
    confidence: float = 0.78,
    scorecard: dict | None = None,
    evidence_refs: list[dict] | None = None,
    status: str = "open",
) -> dict:
    return {
        "id": id,
        "pattern_observation_id": pattern_observation_id,
        "owner": owner,
        "action": action,
        "why_now": why_now,
        "urgency": urgency,
        "confidence": confidence,
        "scorecard": scorecard
        if scorecard is not None
        else {
            "total_score": 78,
            "verdict": "actionable",
            "summary": "Competitor product proof, public narrative, and demand all align.",
            "dimension_scores": [
                {
                    "dimension": "product_reality",
                    "score": 20,
                    "max_score": 25,
                    "rationale": "Constructor has release evidence.",
                    "evidence_urls": ["https://constructor.com/changelog"],
                },
                {
                    "dimension": "market_conversation",
                    "score": 18,
                    "max_score": 20,
                    "rationale": "Constructor is publicly positioning the theme.",
                    "evidence_urls": ["https://constructor.com/blog"],
                },
                {
                    "dimension": "audience_demand",
                    "score": 20,
                    "max_score": 20,
                    "rationale": "Algolia audience demand is rising.",
                    "evidence_urls": ["looker://algolia/ga4/topics"],
                },
                {
                    "dimension": "own_response_gap",
                    "score": 10,
                    "max_score": 15,
                    "rationale": "Algolia has product proof but no matching narrative.",
                    "evidence_urls": ["https://www.algolia.com/changelog/agentic-discovery"],
                },
                {
                    "dimension": "evidence_breadth",
                    "score": 10,
                    "max_score": 20,
                    "rationale": "Four distinct evidence refs support the recommendation.",
                    "evidence_urls": [
                        "https://constructor.com/changelog",
                        "https://constructor.com/blog",
                        "looker://algolia/ga4/topics",
                        "https://www.algolia.com/changelog/agentic-discovery",
                    ],
                },
            ],
        },
        "evidence_refs": evidence_refs
        if evidence_refs is not None
        else [{"source_url": "https://constructor.com/changelog", "method": "scout_changelog"}],
        "status": status,
    }


def demand_signal_row(
    *,
    id: int = 1,
    topic: str = "agentic product discovery",
    metric: str = "engaged_sessions",
    value: float = 1234.0,
    change_pct: float = 0.23,
    source_label: str = "Looker Studio GA4 export",
    evidence_refs: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "id": id,
        "topic": topic,
        "metric": metric,
        "value": value,
        "change_pct": change_pct,
        "source_label": source_label,
        "evidence_refs": evidence_refs
        if evidence_refs is not None
        else [{"source_url": "looker://algolia/ga4/topics", "method": "looker_export"}],
        "metadata": metadata or {},
    }


def feature_position_row(
    *,
    capability_text: str = "agentic product discovery",
    company_name: str = "Constructor",
    company_role: str = "competitor",
    position_status: str = "proven",
    summary: str = "Constructor has public proof for AI Shopping Agent.",
    confidence: float = 0.81,
    evidence_refs: list[dict] | None = None,
) -> dict:
    return {
        "capability_text": capability_text,
        "company_name": company_name,
        "company_role": company_role,
        "position_status": position_status,
        "summary": summary,
        "confidence": confidence,
        "evidence_refs": evidence_refs
        if evidence_refs is not None
        else [{"source_url": "https://constructor.com/changelog", "method": "scout_changelog"}],
    }


def build_status_ok() -> dict:
    return {
        "build_id": "2026.07.08-1",
        "git_sha": "abc1234",
        "deployed_at": None,
        "environment": "hermes-prod",
        "services": [
            {"name": "collector", "status": "ok", "detail": None, "checked_at": None},
            {"name": "brain", "status": "ok", "detail": None, "checked_at": None},
        ],
        "last_error": None,
    }
