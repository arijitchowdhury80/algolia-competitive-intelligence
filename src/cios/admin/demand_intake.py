"""Admin control and history for Hermes-facing inward-demand intake runs."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cios.admin.demand_imports import default_app_dir, default_work_root


class DemandIntakeControl:
    """Run the package demand-intake coordinator with bounded execution."""

    def __init__(
        self,
        *,
        app_dir: Path | None = None,
        work_root: Path | None = None,
        python_bin: str | None = None,
    ) -> None:
        self.app_dir = app_dir or default_app_dir()
        self.work_root = work_root or default_work_root()
        self.python_bin = python_bin or sys.executable

    def run(
        self,
        *,
        tenant_slug: str,
        tenant_id: int,
        own_company_name: str | None = None,
        days: int = 30,
        limit: int = 500,
        command_timeout_seconds: float = 300,
        demand_quality: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        run_dir = self.work_root / tenant_slug / "demand-intake-runs" / _stamp()
        summary_path = run_dir / "demand-intake-summary.json"
        command = [
            self.python_bin,
            str(self.app_dir / "scripts" / "run_argus_demand_intake.py"),
            "--tenant",
            tenant_slug,
            "--app-dir",
            str(self.app_dir),
            "--work-root",
            str(self.work_root),
            "--tenant-id",
            str(tenant_id),
            "--days",
            str(max(1, int(days))),
            "--limit",
            str(max(1, int(limit))),
            "--output",
            str(summary_path),
        ]
        if own_company_name:
            command.extend(["--own-company-name", own_company_name])
        if demand_quality:
            if "change_floor" in demand_quality:
                command.extend(["--demand-change-floor", str(demand_quality["change_floor"])])
            if "value_floor" in demand_quality:
                command.extend(["--demand-value-floor", str(demand_quality["value_floor"])])

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
            payload["returncode"] = completed.returncode
            payload["command_status"] = _command_status(completed.returncode)
            payload["run_output_dir"] = str(run_dir)
            payload["summary_path"] = str(summary_path)
            return payload
        detail = _concise_error(completed.stderr or completed.stdout)
        raise RuntimeError(detail or f"demand intake failed with return code {completed.returncode}")


class DemandIntakeHistoryStore:
    """Read recent demand-intake summaries for the admin surface."""

    def __init__(self, *, work_root: Path | None = None) -> None:
        self.work_root = work_root or default_work_root()

    def status(self, tenant_slug: str, *, limit: int = 5) -> dict[str, Any]:
        run_root = self.work_root / tenant_slug / "demand-intake-runs"
        attempts = _intake_attempts(run_root)
        limited = attempts[: max(1, int(limit))]
        return {
            "tenant_slug": tenant_slug,
            "run_root": str(run_root),
            "attempt_count": len(attempts),
            "latest": limited[0] if limited else None,
            "attempts": limited,
        }


def _intake_attempts(run_root: Path) -> list[dict[str, Any]]:
    if not run_root.exists():
        return []
    attempts: list[dict[str, Any]] = []
    for child in run_root.iterdir():
        if not child.is_dir():
            continue
        summary_path = child / "demand-intake-summary.json"
        if not summary_path.exists():
            continue
        payload = _json_object(summary_path)
        if not payload:
            continue
        attempts.append(_attempt_from_payload(payload, summary_path))
    attempts.sort(key=_attempt_sort_key, reverse=True)
    return attempts


def _attempt_sort_key(item: dict[str, Any]) -> tuple[float, str]:
    raw_time = str(item.get("generated_at") or item.get("run_id") or "")
    parsed_time = _parse_attempt_time(raw_time)
    if parsed_time is None:
        parsed_time = _parse_attempt_time(str(item.get("run_id") or ""))
    return (parsed_time.timestamp() if parsed_time else 0.0, str(item.get("run_id") or ""))


def _parse_attempt_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.split("Z-", 1)[0] + "Z" if "Z-" in value else value
    if normalized.endswith("Z") and "-" in normalized:
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    try:
        return datetime.strptime(normalized, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _attempt_from_payload(payload: dict[str, Any], summary_path: Path) -> dict[str, Any]:
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    demand_import = payload.get("demand_import") if isinstance(payload.get("demand_import"), dict) else {}
    prepare = demand_import.get("prepare") if isinstance(demand_import.get("prepare"), dict) else {}
    demand_ledger = demand_import.get("demand_ledger") if isinstance(demand_import.get("demand_ledger"), dict) else {}
    ga4_export = payload.get("ga4_export") if isinstance(payload.get("ga4_export"), dict) else {}
    argus_read = demand_import.get("argus_read") if isinstance(demand_import.get("argus_read"), dict) else {}
    return {
        "status": str(payload.get("status") or "unknown"),
        "exit_code": int(payload.get("exit_code") if payload.get("exit_code") is not None else payload.get("returncode") or 0),
        "mode": payload.get("mode"),
        "tenant": payload.get("tenant"),
        "next_hermes_action": payload.get("next_hermes_action"),
        "readiness_status": readiness.get("status"),
        "readiness_summary": readiness.get("summary"),
        "ga4_record_count": int(ga4_export.get("record_count") or 0),
        "normalized_row_count": int(prepare.get("normalized_row_count") or 0),
        "ready_count": int(prepare.get("ready_count") or 0),
        "demand_signal_count": int(demand_ledger.get("demand_signal_count") or 0),
        "argus_top_insight": argus_read.get("top_insight"),
        "error": _attempt_error(payload, demand_import, ga4_export),
        "generated_at": payload.get("generated_at") or summary_path.parent.name,
        "run_id": summary_path.parent.name,
        "summary_path": str(summary_path),
        "run_output_dir": str(summary_path.parent),
    }


def _attempt_error(
    payload: dict[str, Any],
    demand_import: dict[str, Any],
    ga4_export: dict[str, Any],
) -> str | None:
    for candidate in (
        payload.get("error"),
        demand_import.get("error"),
        ga4_export.get("error"),
    ):
        if candidate:
            return str(candidate)
    return None


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _command_status(returncode: int) -> str:
    if returncode == 0:
        return "ok"
    if returncode in {2, 3}:
        return "blocked"
    return "failed"


def _concise_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Traceback"):
            continue
        return line[:500]
    return ""


__all__ = ["DemandIntakeControl", "DemandIntakeHistoryStore"]
