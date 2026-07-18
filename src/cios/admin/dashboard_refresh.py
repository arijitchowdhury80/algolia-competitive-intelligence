"""Admin-triggered dashboard refresh for already-computed Argus intelligence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cios.dashboard.artifacts import publish_dashboard_artifacts


def _default_app_dir() -> Path:
    configured = os.environ.get("CIOS_APP_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3]


def _default_out_dir(app_dir: Path) -> Path:
    configured = os.environ.get("CIOS_OUTPUT_DIR") or os.environ.get("CIOS_DASHBOARD_OUT_DIR")
    if configured:
        return Path(configured)
    return app_dir / "out"


def _default_public_dir() -> Path | None:
    configured = os.environ.get("CIOS_PUBLIC_DIR")
    return Path(configured) if configured else None


def _default_work_root() -> Path:
    configured = os.environ.get("CIOS_PRODUCT_MARKET_WORKDIR") or os.environ.get("CIOS_PRODUCT_MARKET_WORK_DIR")
    if configured:
        return Path(configured)
    return Path("/tmp/cios-product-market")


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _dashboard_run_id(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("dashboard refresh missing valid run identity") from exc
    run_id = str((payload.get("run_health") or {}).get("run_id") or "").strip()
    if not run_id:
        raise RuntimeError("dashboard refresh missing valid run identity")
    return run_id


@dataclass
class AdminDashboardRefreshRunner:
    """Rerender dashboard artifacts from DB state and optionally publish them.

    This is intentionally a package-level operator runner, not Hermes core
    behavior. Hermes owns the schedule; CI-OS owns how its dashboard artifacts
    are refreshed from the CI-OS ledger.

    "Refresh" here means the complete public Argus artifact set, not only
    HTML. Admin-triggered refreshes must rebuild the same sidecars that the
    Hermes daily wrapper publishes: demand readiness, evidence work queue,
    operator handoff, and the Argus data-plane manifest.
    """

    app_dir: Path | None = None
    out_dir: Path | None = None
    public_dir: Path | None = None
    work_root: Path | None = None
    python_bin: str | None = None
    public_store: Path | None = None
    publication_v2: bool | None = None

    def __call__(self, *, tenant_slug: str) -> dict[str, Any]:
        app_dir = self.app_dir or _default_app_dir()
        out_dir = self.out_dir or _default_out_dir(app_dir)
        public_dir = self.public_dir if self.public_dir is not None else _default_public_dir()
        work_root = self.work_root or _default_work_root()
        python_bin = self.python_bin or sys.executable
        script = app_dir / "scripts" / "rerender_dashboard.py"
        cmd = [
            python_bin,
            str(script),
            "--tenant",
            tenant_slug,
            "--out-dir",
            str(out_dir),
        ]
        completed = subprocess.run(
            cmd,
            cwd=str(app_dir),
            text=True,
            capture_output=True,
            check=False,
        )
        rerender = {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "out_dir": str(out_dir),
        }
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise RuntimeError(f"dashboard rerender failed: {detail}")

        use_publication_v2 = self.publication_v2 if self.publication_v2 is not None else _env_flag("CIOS_PUBLICATION_V2")
        run_id = _dashboard_run_id(out_dir / "argus-dashboard.json") if use_publication_v2 else None
        sidecars = _refresh_argus_sidecars(
            tenant_slug=tenant_slug,
            app_dir=app_dir,
            out_dir=out_dir,
            work_root=work_root,
            python_bin=python_bin,
            run_id=run_id,
        )

        result: dict[str, Any] = {
            "status": "rerendered",
            "rerender": rerender,
            "sidecars": sidecars,
            "out_dir": str(out_dir),
        }
        if use_publication_v2:
            store = self.public_store or Path(os.environ.get("CIOS_PUBLIC_STORE_DIR", "/opt/cios/public-store"))
            publish_cmd = [
                python_bin,
                str(app_dir / "scripts" / "publish_generation.py"),
                "--store-root",
                str(store),
                "--run-id",
                str(run_id),
                "--tenant",
                tenant_slug,
                "--kind",
                "diagnostic",
                "--status",
                str(out_dir / "argus-public-run-status.json"),
                "--demand-plan-template",
                str(out_dir / "argus-demand-plan-template.csv"),
                "--output",
                str(out_dir / "publication-integrity-verdict.json"),
            ]
            guide = out_dir / "argus-demand-work-order-guide.json"
            if guide.is_file():
                publish_cmd.extend(["--demand-work-order-guide", str(guide)])
            result["publish"] = _run_step(
                name="immutable_diagnostic_publish",
                cmd=publish_cmd,
                cwd=app_dir,
            )
            result["status"] = "diagnostic_published"
        elif public_dir:
            result["publish"] = publish_dashboard_artifacts(out_dir=out_dir, public_dir=public_dir)
            result["status"] = "published"
        return result


def _run_step(*, name: str, cmd: list[str], cwd: Path) -> dict[str, Any]:
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
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"dashboard sidecar {name} failed: {detail}")
    return result


def _run_demand_intake_sidecar(*, cmd: list[str], cwd: Path, output: Path) -> dict[str, Any]:
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
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("dashboard sidecar demand_intake failed: missing demand intake artifact")
    return result


def _refresh_argus_sidecars(
    *,
    tenant_slug: str,
    app_dir: Path,
    out_dir: Path,
    work_root: Path,
    python_bin: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    dashboard = out_dir / "argus-dashboard.json"
    html = out_dir / "argus-dashboard.html"
    demand_readiness = out_dir / "argus-demand-readiness.json"
    demand_plan_template = out_dir / "argus-demand-plan-template.csv"
    demand_intake = out_dir / "argus-demand-intake.json"
    evidence_queue = out_dir / "argus-evidence-work-queue.json"
    product_muscle_queue = out_dir / "argus-product-muscle-work-queue.json"
    handoff = out_dir / "argus-operator-handoff.json"
    data_plane_manifest = out_dir / "argus-data-plane-manifest.json"
    public_run_status = out_dir / "argus-public-run-status.json"
    scripts = app_dir / "scripts"

    steps: list[tuple[str, list[str]]] = [
        (
            "demand_readiness",
            [
                python_bin,
                str(scripts / "export_argus_demand_readiness.py"),
                "--tenant",
                tenant_slug,
                "--app-dir",
                str(app_dir),
                "--work-root",
                str(work_root),
                "--dashboard",
                str(dashboard),
                "--output",
                str(demand_readiness),
            ],
        ),
        (
            "demand_plan_template",
            [
                python_bin,
                str(scripts / "export_argus_demand_plan_template.py"),
                "--readiness",
                str(demand_readiness),
                "--output",
                str(demand_plan_template),
            ],
        ),
        (
            "demand_intake",
            [
                python_bin,
                str(scripts / "run_argus_demand_intake.py"),
                "--tenant",
                tenant_slug,
                "--app-dir",
                str(app_dir),
                "--work-root",
                str(work_root),
                "--out-dir",
                str(out_dir),
                "--dashboard",
                str(dashboard),
                "--python-bin",
                python_bin,
                "--record-history",
                "--output",
                str(demand_intake),
            ],
        ),
        (
            "attach_demand_readiness",
            [
                python_bin,
                str(scripts / "attach_post_run_summaries.py"),
                "--dashboard",
                str(dashboard),
                "--demand-readiness",
                str(demand_readiness),
            ],
        ),
        (
            "evidence_work_queue",
            [
                python_bin,
                str(scripts / "export_argus_evidence_work_queue.py"),
                "--tenant",
                tenant_slug,
                "--output",
                str(evidence_queue),
            ],
        ),
        (
            "product_muscle_work_queue",
            [
                python_bin,
                str(scripts / "export_argus_product_muscle_work_queue.py"),
                "--tenant",
                tenant_slug,
                "--work-root",
                str(work_root),
                "--output",
                str(product_muscle_queue),
            ],
        ),
        (
            "operator_handoff",
            [
                python_bin,
                str(scripts / "build_argus_operator_handoff.py"),
                "--tenant",
                tenant_slug,
                "--work-queue",
                str(evidence_queue),
                "--product-muscle-queue",
                str(product_muscle_queue),
                "--demand-readiness",
                str(demand_readiness),
                "--demand-plan-template",
                str(demand_plan_template),
                "--dashboard",
                str(dashboard),
                "--output",
                str(handoff),
            ],
        ),
        (
            "attach_operator_handoff",
            [
                python_bin,
                str(scripts / "attach_operator_handoff_to_dashboard.py"),
                "--dashboard",
                str(dashboard),
                "--handoff",
                str(handoff),
                "--html",
                str(html),
            ],
        ),
        (
            "data_plane_manifest",
            [
                python_bin,
                str(scripts / "export_argus_data_plane_manifest.py"),
                "--tenant",
                tenant_slug,
                "--dashboard",
                str(dashboard),
                "--demand-readiness",
                str(demand_readiness),
                "--demand-plan-template",
                str(demand_plan_template),
                "--demand-intake",
                str(demand_intake),
                "--evidence-work-queue",
                str(evidence_queue),
                "--product-muscle-work-queue",
                str(product_muscle_queue),
                "--operator-handoff",
                str(handoff),
                "--output",
                str(data_plane_manifest),
            ],
        ),
        (
            "public_run_status",
            [
                python_bin,
                str(scripts / "export_public_run_status.py"),
                "--tenant",
                tenant_slug,
                "--manifest",
                str(data_plane_manifest),
                "--dashboard",
                str(dashboard),
                "--publish-status",
                "blocked",
                "--output",
                str(public_run_status),
            ],
        ),
    ]
    if run_id:
        for name, cmd in steps:
            if name in {"data_plane_manifest", "public_run_status"}:
                cmd.extend(["--run-id", run_id])
    results: dict[str, Any] = {}
    for name, cmd in steps:
        if name == "demand_intake":
            results[name] = _run_demand_intake_sidecar(cmd=cmd, cwd=app_dir, output=demand_intake)
            continue
        results[name] = _run_step(name=name, cmd=cmd, cwd=app_dir)
    return results
