"""Admin control for first-run product-surface Scout extraction."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class ProductSurfaceExtractionControl:
    """Plan and execute product-surface exports for active surfaces.

    This is the first-run counterpart to product-surface repair. Repair retries
    failed or empty rows from an existing plan. Extraction creates the filtered
    plan when a company already has active product surfaces but no feature
    evidence yet.
    """

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
        focus_capability: str | None = None,
        company_id: int | None = None,
        surface_id: int | None = None,
        use_js: bool = True,
        timeout_seconds: float = 160,
        command_timeout_seconds: float = 220,
        max_workers: int = 1,
        limit: int = 1,
    ) -> dict[str, Any]:
        tenant_root = self.work_root / tenant_slug
        output_dir = tenant_root / "surface-exports"
        plan_path = tenant_root / "product-surface-plan.json"
        summary_path = tenant_root / "product-surface-execution-summary.json"
        scripts = self.app_dir / "scripts"
        scout_bin = os.environ.get("CIOS_SCOUT_BIN") or str(scripts / "scout_http_shim")
        provider = os.environ.get("CIOS_PRODUCT_MARKET_PROVIDER", "gemini/gemini-2.5-flash")

        plan_command = [
            self.python_bin,
            str(scripts / "plan_product_surface_exports.py"),
            "--tenant-id",
            str(tenant_id),
            "--output-dir",
            str(output_dir),
            "--plan-output",
            str(plan_path),
            "--python-bin",
            self.python_bin,
            "--script-path",
            str(scripts / "export_product_surface_with_scout.py"),
            "--scout-bin",
            scout_bin,
            "--provider",
            provider,
            "--timeout-seconds",
            _number_arg(timeout_seconds),
            "--limit",
            str(max(1, int(limit))),
        ]
        if company_name:
            plan_command.extend(["--company-name", company_name])
        if focus_capability:
            plan_command.extend(["--focus-capability", focus_capability])
        if company_id is not None:
            plan_command.extend(["--company-id", str(company_id)])
        if surface_id is not None:
            plan_command.extend(["--surface-id", str(surface_id)])
        if use_js:
            plan_command.append("--js")

        plan_result = _run_command(cmd=plan_command, cwd=self.app_dir)
        if not plan_path.exists():
            raise RuntimeError("product-surface extraction failed: missing plan artifact")

        execute_command = [
            self.python_bin,
            str(scripts / "execute_product_surface_plan.py"),
            "--plan",
            str(plan_path),
            "--summary-output",
            str(summary_path),
            "--command-timeout-seconds",
            _number_arg(command_timeout_seconds),
            "--max-workers",
            str(max(1, int(max_workers))),
        ]
        execute_result = _run_command(cmd=execute_command, cwd=self.app_dir, allow_failure=True)
        if not summary_path.exists():
            detail = execute_result.get("stderr") or execute_result.get("stdout") or "missing execution summary"
            raise RuntimeError(f"product-surface extraction failed: {detail}")

        summary = _json_object(summary_path)
        summary["tenant_id"] = summary.get("tenant_id") or tenant_id
        summary["status"] = summary.get("product_plane_status") or "unknown"
        summary["command_status"] = "ok" if int(execute_result["returncode"]) == 0 else "failed"
        summary["returncode"] = execute_result["returncode"]
        summary["plan"] = plan_result
        summary["execution"] = execute_result
        summary["plan_path"] = str(plan_path)
        summary["summary_path"] = str(summary_path)
        summary["output_dir"] = str(output_dir)
        return summary


def _run_command(*, cmd: list[str], cwd: Path, allow_failure: bool = False) -> dict[str, Any]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    result = {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.returncode != 0 and not allow_failure:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"product-surface extraction command failed: {detail}")
    return result


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


def _number_arg(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


__all__ = ["ProductSurfaceExtractionControl"]
