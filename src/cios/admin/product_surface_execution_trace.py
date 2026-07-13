"""Read Hermes product-surface execution artifacts for admin work queues."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


TraceByCompany = dict[tuple[str, str], dict[str, Any]]


class ProductSurfaceExecutionTraceStore:
    """Build a per-company trace from the latest product-surface run artifacts."""

    def __init__(
        self,
        *,
        work_root: Path | None = None,
        plan_path: Path | None = None,
        summary_path: Path | None = None,
    ) -> None:
        self.work_root = work_root
        self.plan_path = plan_path
        self.summary_path = summary_path

    def status(self, tenant_slug: str) -> TraceByCompany:
        plan_path, summary_path = self._paths(tenant_slug)
        if not plan_path.exists() or not summary_path.exists():
            return {}
        return load_product_surface_execution_trace(plan_path=plan_path, summary_path=summary_path)

    def _paths(self, tenant_slug: str) -> tuple[Path, Path]:
        if self.plan_path is not None and self.summary_path is not None:
            return self.plan_path, self.summary_path
        tenant_root = (self.work_root or _default_work_root()) / tenant_slug
        return (
            self.plan_path or tenant_root / "product-surface-plan.json",
            self.summary_path or tenant_root / "product-surface-execution-summary.json",
        )


def load_product_surface_execution_trace(*, plan_path: Path, summary_path: Path) -> TraceByCompany:
    plan = _json_object(plan_path)
    summary = _json_object(summary_path)
    result_by_output = {
        str(result.get("output_path")): result
        for result in summary.get("results", [])
        if isinstance(result, dict) and result.get("output_path")
    }
    trace: TraceByCompany = {}
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        target = item.get("target")
        if not isinstance(target, dict):
            continue
        company_name = str(target.get("company_name") or "").strip()
        if not company_name:
            continue
        company_role = str(target.get("company_role") or "competitor").strip() or "competitor"
        output_path = str(item.get("output_path") or "")
        result = result_by_output.get(output_path, {})
        key = (_norm(company_name), company_role)
        company = trace.setdefault(
            key,
            {
                "planned_surface_count": 0,
                "succeeded_surface_count": 0,
                "failed_surface_count": 0,
                "row_count": 0,
                "empty_output_count": 0,
                "last_error": None,
                "plan_path": str(plan_path),
                "summary_path": str(summary_path),
            },
        )
        company["planned_surface_count"] += 1
        if result.get("status") == "succeeded":
            company["succeeded_surface_count"] += 1
            row_count = _row_count(Path(output_path)) if output_path else 0
            company["row_count"] += row_count
            if row_count == 0:
                company["empty_output_count"] += 1
        elif result:
            company["failed_surface_count"] += 1
            error = str(result.get("error") or "").strip()
            if error:
                company["last_error"] = error.splitlines()[-1]
    return trace


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _row_count(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("records", "rows", "product_events", "changes"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def _default_work_root() -> Path:
    configured = os.environ.get("CIOS_PRODUCT_MARKET_WORKDIR")
    if configured:
        return Path(configured)
    return Path("/tmp/cios-product-market")


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


__all__ = [
    "ProductSurfaceExecutionTraceStore",
    "TraceByCompany",
    "load_product_surface_execution_trace",
]
