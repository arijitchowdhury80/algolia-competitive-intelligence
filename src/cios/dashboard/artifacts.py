"""Dashboard artifact validation and staged publication helpers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


def require_dashboard_artifact(path: Path, *, kind: str) -> None:
    if kind == "dir":
        if not path.is_dir():
            raise FileNotFoundError(f"missing dashboard artifact directory: {path}")
        return
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"missing dashboard artifact file: {path}")


def publish_dashboard_artifacts(*, out_dir: Path, public_dir: Path) -> dict[str, Any]:
    """Publish a rerendered dashboard artifact set with a staged copy.

    The helper intentionally mirrors the Hermes daily wrapper contract:
    `argus-dashboard.html`, `brief.html`, `argus-dashboard.json`,
    `argus-data-plane-manifest.json`, and `briefs/` are produced under
    `out_dir`, then copied to the public root plus `/v2`.
    """

    cockpit = out_dir / "argus-dashboard.html"
    brief = out_dir / "brief.html"
    dashboard_json = out_dir / "argus-dashboard.json"
    data_plane_manifest = out_dir / "argus-data-plane-manifest.json"
    public_run_status = out_dir / "argus-public-run-status.json"
    demand_plan_template = out_dir / "argus-demand-plan-template.csv"
    demand_work_order_guide = out_dir / "argus-demand-work-order-guide.json"
    briefs = out_dir / "briefs"
    require_dashboard_artifact(cockpit, kind="file")
    require_dashboard_artifact(brief, kind="file")
    require_dashboard_artifact(dashboard_json, kind="file")
    require_dashboard_artifact(data_plane_manifest, kind="file")
    require_dashboard_artifact(briefs, kind="dir")

    public_dir.mkdir(parents=True, exist_ok=True)
    stage = public_dir / f".argus-publish.{os.getpid()}"
    if stage.exists():
        shutil.rmtree(stage)
    try:
        (stage / "data").mkdir(parents=True)
        (stage / "v2" / "data").mkdir(parents=True)
        shutil.copy2(cockpit, stage / "index.html")
        shutil.copy2(cockpit, stage / "v2" / "index.html")
        shutil.copy2(brief, stage / "brief.html")
        shutil.copy2(brief, stage / "v2" / "brief.html")
        shutil.copy2(dashboard_json, stage / "data" / "semantic-dashboard.json")
        shutil.copy2(dashboard_json, stage / "v2" / "data" / "semantic-dashboard.json")
        shutil.copy2(data_plane_manifest, stage / "data" / "argus-data-plane-manifest.json")
        shutil.copy2(data_plane_manifest, stage / "v2" / "data" / "argus-data-plane-manifest.json")
        if public_run_status.is_file() and public_run_status.stat().st_size > 0:
            shutil.copy2(public_run_status, stage / "data" / "argus-latest-run-status.json")
            shutil.copy2(public_run_status, stage / "v2" / "data" / "argus-latest-run-status.json")
        if demand_plan_template.is_file() and demand_plan_template.stat().st_size > 0:
            shutil.copy2(demand_plan_template, stage / "data" / "argus-demand-plan-template.csv")
            shutil.copy2(demand_plan_template, stage / "v2" / "data" / "argus-demand-plan-template.csv")
        if demand_work_order_guide.is_file() and demand_work_order_guide.stat().st_size > 0:
            shutil.copy2(demand_work_order_guide, stage / "data" / "argus-demand-work-order-guide.json")
            shutil.copy2(demand_work_order_guide, stage / "v2" / "data" / "argus-demand-work-order-guide.json")
        shutil.copytree(briefs, stage / "briefs")
        shutil.copytree(briefs, stage / "v2" / "briefs")

        (public_dir / "data").mkdir(parents=True, exist_ok=True)
        (public_dir / "v2" / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage / "index.html", public_dir / "index.html")
        shutil.copy2(stage / "v2" / "index.html", public_dir / "v2" / "index.html")
        shutil.copy2(stage / "brief.html", public_dir / "brief.html")
        shutil.copy2(stage / "v2" / "brief.html", public_dir / "v2" / "brief.html")
        shutil.copy2(stage / "data" / "semantic-dashboard.json", public_dir / "data" / "semantic-dashboard.json")
        shutil.copy2(stage / "v2" / "data" / "semantic-dashboard.json", public_dir / "v2" / "data" / "semantic-dashboard.json")
        shutil.copy2(
            stage / "data" / "argus-data-plane-manifest.json",
            public_dir / "data" / "argus-data-plane-manifest.json",
        )
        shutil.copy2(
            stage / "v2" / "data" / "argus-data-plane-manifest.json",
            public_dir / "v2" / "data" / "argus-data-plane-manifest.json",
        )
        if (stage / "data" / "argus-latest-run-status.json").exists():
            shutil.copy2(
                stage / "data" / "argus-latest-run-status.json",
                public_dir / "data" / "argus-latest-run-status.json",
            )
            shutil.copy2(
                stage / "v2" / "data" / "argus-latest-run-status.json",
                public_dir / "v2" / "data" / "argus-latest-run-status.json",
            )
        if (stage / "data" / "argus-demand-plan-template.csv").exists():
            shutil.copy2(
                stage / "data" / "argus-demand-plan-template.csv",
                public_dir / "data" / "argus-demand-plan-template.csv",
            )
            shutil.copy2(
                stage / "v2" / "data" / "argus-demand-plan-template.csv",
                public_dir / "v2" / "data" / "argus-demand-plan-template.csv",
            )
        if (stage / "data" / "argus-demand-work-order-guide.json").exists():
            shutil.copy2(
                stage / "data" / "argus-demand-work-order-guide.json",
                public_dir / "data" / "argus-demand-work-order-guide.json",
            )
            shutil.copy2(
                stage / "v2" / "data" / "argus-demand-work-order-guide.json",
                public_dir / "v2" / "data" / "argus-demand-work-order-guide.json",
            )
        for target in (public_dir / "briefs", public_dir / "v2" / "briefs"):
            if target.exists():
                shutil.rmtree(target)
        shutil.copytree(stage / "briefs", public_dir / "briefs")
        shutil.copytree(stage / "v2" / "briefs", public_dir / "v2" / "briefs")
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    return {
        "status": "published",
        "public_dir": str(public_dir),
        "index": str(public_dir / "index.html"),
        "json": str(public_dir / "data" / "semantic-dashboard.json"),
        "data_plane_manifest": str(public_dir / "data" / "argus-data-plane-manifest.json"),
        "public_run_status": str(public_dir / "data" / "argus-latest-run-status.json"),
        "demand_plan_template": str(public_dir / "data" / "argus-demand-plan-template.csv"),
        "demand_work_order_guide": str(public_dir / "data" / "argus-demand-work-order-guide.json"),
        "briefs": str(public_dir / "briefs"),
    }
