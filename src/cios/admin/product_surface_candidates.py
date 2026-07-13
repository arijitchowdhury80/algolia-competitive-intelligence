"""Admin control for promoting validated product-surface candidates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class ProductSurfaceCandidatePromotionControl:
    """Promote validated candidate product surfaces through the package script."""

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
        surface_family: str | None = None,
        discovery_source: str = "product_muscle_gap_plan",
        promoted_by: str = "argus",
        limit: int = 1,
    ) -> dict[str, Any]:
        output = self.work_root / tenant_slug / "product-surface-candidate-promotion-summary.json"
        command = [
            self.python_bin,
            str(self.app_dir / "scripts" / "promote_product_surface_candidates.py"),
            "--tenant-id",
            str(tenant_id),
            "--discovery-source",
            discovery_source,
            "--promoted-by",
            promoted_by,
            "--limit",
            str(max(1, int(limit))),
            "--output",
            str(output),
        ]
        if company_name:
            command.extend(["--company-name", company_name])
        if company_id is not None:
            command.extend(["--company-id", str(company_id)])
        if surface_family:
            command.extend(["--surface-family", surface_family])

        completed = subprocess.run(
            command,
            cwd=str(self.app_dir),
            text=True,
            capture_output=True,
            check=False,
        )
        if not output.exists():
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise RuntimeError(f"product-surface candidate promotion failed: {detail}")
        payload = _json_object(output)
        payload["tenant_id"] = payload.get("tenant_id") or tenant_id
        payload["tenant_slug"] = payload.get("tenant_slug") or tenant_slug
        payload["command_status"] = "ok" if completed.returncode == 0 else "failed"
        payload["returncode"] = completed.returncode
        payload["summary_path"] = str(output)
        if completed.returncode != 0:
            payload["error"] = completed.stderr.strip() or completed.stdout.strip()
        return payload


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


__all__ = ["ProductSurfaceCandidatePromotionControl"]
