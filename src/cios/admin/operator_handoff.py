"""Admin read model for the Hermes-produced Argus operator handoff artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cios.admin.types import ArgusOperatorCommand, ArgusOperatorHandoff


class ArgusOperatorHandoffStore:
    """Reads the latest Argus operator handoff emitted by the Hermes wrapper."""

    def __init__(
        self,
        *,
        out_dir: Path | None = None,
        work_root: Path | None = None,
        artifact_path: Path | None = None,
    ) -> None:
        self.out_dir = out_dir
        self.work_root = work_root
        self.artifact_path = artifact_path

    def status(self, tenant_slug: str) -> ArgusOperatorHandoff:
        path = self._resolve_path(tenant_slug)
        if not path.exists():
            return _missing_handoff(tenant_slug, path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _invalid_handoff(tenant_slug, path, str(exc))
        if not isinstance(payload, dict):
            return _invalid_handoff(tenant_slug, path, "operator handoff artifact must be a JSON object")
        if payload.get("tenant_slug") not in {None, tenant_slug}:
            return _invalid_handoff(
                tenant_slug,
                path,
                f"operator handoff tenant {payload.get('tenant_slug')} does not match {tenant_slug}",
            )
        return ArgusOperatorHandoff.model_validate(
            {
                **payload,
                "tenant_slug": tenant_slug,
                "artifact_path": str(path),
                "artifact_found": True,
            }
        )

    def _resolve_path(self, tenant_slug: str) -> Path:
        for path in self._candidate_paths(tenant_slug):
            if path.exists():
                return path
        return self._candidate_paths(tenant_slug)[0]

    def _candidate_paths(self, tenant_slug: str) -> list[Path]:
        candidates: list[Path] = []
        if self.artifact_path is not None:
            return [self.artifact_path]
        if self.out_dir is not None:
            return [self.out_dir / "argus-operator-handoff.json"]

        explicit = _env_path("CIOS_OPERATOR_HANDOFF_PATH")
        if explicit:
            candidates.append(explicit)
        out_dir = _default_out_dir()
        candidates.append(out_dir / "argus-operator-handoff.json")
        work_root = self.work_root or _default_work_root()
        candidates.append(work_root / tenant_slug / "argus-operator-handoff.json")

        deduped: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(path)
        return deduped


def _missing_handoff(tenant_slug: str, path: Path) -> ArgusOperatorHandoff:
    return ArgusOperatorHandoff(
        tenant_slug=tenant_slug,
        status="not_recorded",
        argus_readiness="unknown",
        summary="No Argus operator handoff artifact has been recorded for this tenant.",
        next_operator_action="Run the Hermes daily sweep or rebuild the Argus operator handoff.",
        primary_command=ArgusOperatorCommand(
            label="Open Argus run console",
            href=f"/admin?tenant={tenant_slug}#argus-run-console",
            method="get",
            surface="Argus run console",
        ),
        operator_brief=[
            "Hermes has not published an operator handoff artifact for this tenant yet.",
            "Run the daily sweep or rebuild the handoff after the evidence work queue is generated.",
        ],
        artifact_refs={},
        work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "item_ids": []},
        artifact_path=str(path),
        artifact_found=False,
    )


def _invalid_handoff(tenant_slug: str, path: Path, detail: str) -> ArgusOperatorHandoff:
    return ArgusOperatorHandoff(
        tenant_slug=tenant_slug,
        status="artifact_error",
        argus_readiness="unknown",
        summary=f"Argus operator handoff artifact could not be read: {detail}",
        next_operator_action="Rebuild the Argus operator handoff before trusting the run console.",
        primary_command=ArgusOperatorCommand(
            label="Open Argus run console",
            href=f"/admin?tenant={tenant_slug}#argus-run-console",
            method="get",
            surface="Argus run console",
        ),
        operator_brief=["The operator handoff artifact is present but invalid."],
        artifact_refs={},
        work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "item_ids": []},
        artifact_path=str(path),
        artifact_found=False,
    )


def _default_app_dir() -> Path:
    configured = os.environ.get("CIOS_APP_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3]


def _default_out_dir() -> Path:
    configured = os.environ.get("CIOS_OUTPUT_DIR") or os.environ.get("CIOS_DASHBOARD_OUT_DIR")
    if configured:
        return Path(configured)
    return _default_app_dir() / "out"


def _default_work_root() -> Path:
    configured = os.environ.get("CIOS_PRODUCT_MARKET_WORKDIR")
    if configured:
        return Path(configured)
    return Path("/tmp/cios-product-market")


def _env_path(name: str) -> Path | None:
    configured = os.environ.get(name)
    if not configured:
        return None
    return Path(configured).expanduser()
