#!/usr/bin/env python3
"""Attach the Hermes/Argus operator handoff to the public dashboard state.

The daily wrapper builds the operator handoff after the evidence work queue is
exported. This command makes that handoff visible to the public read model by
updating `argus-dashboard.json` and re-rendering `argus-dashboard.html` from the
same typed DashboardState.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cios.dashboard.cockpit_renderer import render_cockpit_html
from cios.dashboard.publisher import to_json_str
from cios.dashboard.types import DashboardOperatorHandoff, DashboardState


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def attach_operator_handoff_payload(
    *,
    dashboard: dict[str, Any],
    handoff: dict[str, Any],
    artifact_path: str | None = None,
) -> dict[str, Any]:
    dashboard_tenant_id = dashboard.get("tenant_id")
    handoff_tenant_id = handoff.get("tenant_id")
    if (
        dashboard_tenant_id is not None
        and handoff_tenant_id is not None
        and int(dashboard_tenant_id) != int(handoff_tenant_id)
    ):
        raise ValueError(
            f"operator handoff tenant_id {handoff_tenant_id} "
            f"does not match dashboard tenant_id {dashboard_tenant_id}"
        )

    attached = {
        **handoff,
        "artifact_path": artifact_path,
        "artifact_found": True,
    }
    # Validate before mutating the dashboard payload so malformed handoffs fail
    # fast and do not publish a half-updated JSON file.
    handoff_model = DashboardOperatorHandoff.model_validate(attached)
    payload = {
        **dashboard,
        "operator_handoff": handoff_model.model_dump(mode="json"),
    }
    return _sync_blocking_handoff_into_spine(payload)


def _sync_blocking_handoff_into_spine(payload: dict[str, Any]) -> dict[str, Any]:
    handoff = payload.get("operator_handoff")
    if not isinstance(handoff, dict) or not _handoff_blocks_action(handoff):
        return payload
    spine = payload.get("intelligence_spine")
    if not isinstance(spine, dict):
        spine = {}
    synced = dict(spine)
    synced["next_operator_action"] = handoff.get("next_operator_action")
    synced["can_recommend"] = False

    top_blocker = handoff.get("top_blocker")
    blocked_actions = list(synced.get("blocked_actions") or [])
    if isinstance(top_blocker, dict):
        blocked_actions = _append_unique(blocked_actions, top_blocker.get("blocks") or [])
    synced["blocked_actions"] = blocked_actions

    confidence_limits = list(synced.get("confidence_limits") or [])
    summary = handoff.get("summary")
    if summary:
        confidence_limits = _append_unique(confidence_limits, [summary])
    synced["confidence_limits"] = confidence_limits
    return {**payload, "intelligence_spine": synced}


def _handoff_blocks_action(handoff: dict[str, Any]) -> bool:
    top_blocker = handoff.get("top_blocker")
    top_severity = top_blocker.get("severity") if isinstance(top_blocker, dict) else None
    return (
        handoff.get("status") == "blocked_on_evidence"
        or handoff.get("argus_readiness") == "not_actionable"
        or top_severity == "blocks_action"
    )


def _append_unique(existing: list[Any], additions: list[Any]) -> list[Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for item in [*existing, *additions]:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def attach_and_render(*, dashboard_path: Path, handoff_path: Path, html_path: Path) -> DashboardState:
    dashboard = load_json(dashboard_path)
    handoff = load_json(handoff_path)
    payload = attach_operator_handoff_payload(
        dashboard=dashboard,
        handoff=handoff,
        artifact_path=str(handoff_path),
    )
    state = DashboardState.model_validate(payload)
    write_text_atomic(dashboard_path, f"{to_json_str(state)}\n")
    write_text_atomic(html_path, render_cockpit_html(state))
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Attach Argus operator handoff to dashboard JSON and HTML.")
    parser.add_argument("--dashboard", required=True, type=Path, help="argus-dashboard.json path.")
    parser.add_argument("--handoff", required=True, type=Path, help="argus-operator-handoff.json path.")
    parser.add_argument("--html", required=True, type=Path, help="argus-dashboard.html path to re-render.")
    args = parser.parse_args(argv)

    state = attach_and_render(dashboard_path=args.dashboard, handoff_path=args.handoff, html_path=args.html)
    print(f"attached operator handoff to dashboard for tenant_id={state.tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
