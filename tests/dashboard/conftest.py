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
