"""Admin control for bounded product-surface repair retries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProductSurfaceRepairControl:
    """Run the package repair script against the latest Hermes artifacts."""

    def __init__(
        self,
        *,
        app_dir: Path | None = None,
        work_root: Path | None = None,
        python_bin: str | None = None,
    ) -> None:
        self.app_dir = app_dir or _default_app_dir()
        self.work_root = work_root or _default_work_root()
        self.python_bin = python_bin or sys.executable

    def run(
        self,
        *,
        tenant_slug: str,
        tenant_id: int,
        company_name: str | None = None,
        company_id: int | None = None,
        surface_id: int | None = None,
        category: str | None = None,
        use_js: bool = True,
        repair_timeout_seconds: float = 240,
        command_timeout_seconds: float = 300,
        limit: int = 1,
    ) -> dict[str, Any]:
        tenant_root = self.work_root / tenant_slug
        plan_path = tenant_root / "product-surface-plan.json"
        execution_summary_path = tenant_root / "product-surface-execution-summary.json"
        if not plan_path.exists():
            raise ValueError(f"missing product-surface plan: {plan_path}")
        if not execution_summary_path.exists():
            raise ValueError(f"missing product-surface execution summary: {execution_summary_path}")

        repair_root = tenant_root / "product-surface-repairs" / _stamp()
        summary_path = repair_root / "repair-summary.json"
        command = [
            self.python_bin,
            str(self.app_dir / "scripts" / "run_product_surface_repair.py"),
            "--plan",
            str(plan_path),
            "--execution-summary",
            str(execution_summary_path),
            "--repair-output-dir",
            str(repair_root),
            "--summary-output",
            str(summary_path),
            "--repair-timeout-seconds",
            _number_arg(repair_timeout_seconds),
            "--command-timeout-seconds",
            _number_arg(command_timeout_seconds),
            "--limit",
            str(max(1, int(limit))),
        ]
        if company_name:
            command.extend(["--company-name", company_name])
        if company_id is not None:
            command.extend(["--company-id", str(company_id)])
        if surface_id is not None:
            command.extend(["--surface-id", str(surface_id)])
        if category:
            command.extend(["--category", category])
        if use_js:
            command.append("--js")

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(command_timeout_seconds + 15, command_timeout_seconds),
            check=False,
        )
        if summary_path.exists():
            payload = _json_object(summary_path)
            payload["tenant_id"] = payload.get("tenant_id") or tenant_id
            payload["command_status"] = "ok" if completed.returncode == 0 else "failed"
            payload["returncode"] = completed.returncode
            return payload
        detail = _concise_error(completed.stderr or completed.stdout)
        raise RuntimeError(detail or f"product-surface repair failed with return code {completed.returncode}")


class ProductSurfaceRepairHistoryStore:
    """Read recent product-surface repair summaries for the admin surface."""

    def __init__(self, *, work_root: Path | None = None) -> None:
        self.work_root = work_root or _default_work_root()

    def status(self, tenant_slug: str, *, limit: int = 5) -> dict[str, Any]:
        repair_root = self.work_root / tenant_slug / "product-surface-repairs"
        attempts = _repair_attempts(repair_root)
        limited = attempts[: max(1, int(limit))]
        return {
            "tenant_slug": tenant_slug,
            "repair_root": str(repair_root),
            "attempt_count": len(attempts),
            "latest": limited[0] if limited else None,
            "attempts": limited,
        }


def write_product_surface_repair_admin_summary(repair: dict[str, Any]) -> None:
    """Persist the admin-level repair result beside the raw script summary."""
    repair_output_dir = repair.get("repair_output_dir")
    if not repair_output_dir:
        return
    path = Path(str(repair_output_dir)) / "admin-repair-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(repair, indent=2, sort_keys=True), encoding="utf-8")


def _repair_attempts(repair_root: Path) -> list[dict[str, Any]]:
    if not repair_root.exists():
        return []
    attempts: list[dict[str, Any]] = []
    for child in repair_root.iterdir():
        if not child.is_dir():
            continue
        summary_path = child / "admin-repair-summary.json"
        if not summary_path.exists():
            summary_path = child / "repair-summary.json"
        if not summary_path.exists():
            continue
        payload = _json_object(summary_path)
        if not payload:
            continue
        attempts.append(_attempt_from_payload(payload, summary_path))
    attempts.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return attempts


def _attempt_from_payload(payload: dict[str, Any], summary_path: Path) -> dict[str, Any]:
    result = _first_result(payload)
    target = result.get("target") if isinstance(result.get("target"), dict) else {}
    argus_refresh = payload.get("argus_refresh") if isinstance(payload.get("argus_refresh"), dict) else {}
    argus_read = payload.get("argus_read") if isinstance(payload.get("argus_read"), dict) else {}
    return {
        "status": str(payload.get("status") or "unknown"),
        "selected": int(payload.get("selected") or 0),
        "succeeded": int(payload.get("succeeded") or 0),
        "failed": int(payload.get("failed") or 0),
        "generated_at": payload.get("generated_at"),
        "summary_path": str(summary_path),
        "repair_output_dir": payload.get("repair_output_dir") or str(summary_path.parent),
        "company_name": target.get("company_name"),
        "surface_id": target.get("surface_id"),
        "category": result.get("category"),
        "row_count": int(result.get("row_count") or 0),
        "error": result.get("error"),
        "scout_paths": [str(path) for path in payload.get("scout_paths", []) if str(path).strip()],
        "imported_product_event_count": int(argus_refresh.get("product_event_count") or 0),
        "argus_verdict": argus_refresh.get("verdict"),
        "argus_top_insight": argus_read.get("top_insight"),
    }


def _first_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    if isinstance(results, list):
        for result in results:
            if isinstance(result, dict):
                return result
    return {}


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_app_dir() -> Path:
    configured = os.environ.get("CIOS_APP_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3]


def _default_work_root() -> Path:
    configured = os.environ.get("CIOS_PRODUCT_MARKET_WORKDIR")
    if configured:
        return Path(configured)
    return Path("/tmp/cios-product-market")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _number_arg(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _concise_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Traceback"):
            continue
        return line[:500]
    return ""


__all__ = [
    "ProductSurfaceRepairControl",
    "ProductSurfaceRepairHistoryStore",
    "write_product_surface_repair_admin_summary",
]
