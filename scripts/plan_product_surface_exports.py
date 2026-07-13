#!/usr/bin/env python3
"""Build a Hermes-executable Scout export plan for active product surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.db.repos.product_surfaces import PgProductSurfaceRepository  # noqa: E402
from cios.db.session import get_connection  # noqa: E402
from cios.intelligence.product_surface_planner import plan_product_surface_exports  # noqa: E402


def _default_export_script_path() -> Path:
    return Path(__file__).resolve().with_name("export_product_surface_with_scout.py")


def _learning_instructions(path: str | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a next-sweep plan object")
    instructions = data.get("instructions", [])
    if not isinstance(instructions, list):
        raise ValueError(f"{path} instructions must be a list")
    return [dict(item) for item in instructions]


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _filtered_targets(
    targets: list[Any],
    *,
    company_name: str | None,
    company_id: int | None,
    surface_id: int | None,
    limit: int | None,
) -> list[Any]:
    filtered: list[Any] = []
    normalized_company_name = _norm(company_name or "") if company_name else None
    for target in targets:
        if normalized_company_name and _norm(str(target.company_name)) != normalized_company_name:
            continue
        if company_id is not None and int(target.company_id) != company_id:
            continue
        if surface_id is not None and int(target.surface_id or -1) != surface_id:
            continue
        filtered.append(target)
        if limit is not None and len(filtered) >= max(1, int(limit)):
            break
    return filtered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--plan-output", required=True)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--script-path", default=str(_default_export_script_path()))
    parser.add_argument("--scout-bin", default="scout")
    parser.add_argument("--provider", default="ollama/llama3.2:3b")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--js", action="store_true")
    parser.add_argument("--learning-plan", help="Next-sweep learning plan JSON for coverage prioritization.")
    parser.add_argument("--company-name")
    parser.add_argument("--focus-capability")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--surface-id", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    with get_connection() as conn:
        targets = PgProductSurfaceRepository(conn).get_active_targets(args.tenant_id)
    targets = _filtered_targets(
        targets,
        company_name=args.company_name,
        company_id=args.company_id,
        surface_id=args.surface_id,
        limit=args.limit,
    )

    plan = plan_product_surface_exports(
        targets,
        output_dir=Path(args.output_dir),
        python_bin=args.python_bin,
        script_path=Path(args.script_path),
        scout_bin=args.scout_bin,
        provider=args.provider,
        timeout_seconds=args.timeout_seconds,
        use_js=args.js,
        learning_instructions=_learning_instructions(args.learning_plan),
        focus_capability=args.focus_capability,
    )
    payload = {
        "tenant_id": args.tenant_id,
        "target_count": len(targets),
        "items": [item.model_dump(mode="json") for item in plan],
    }

    output = Path(args.plan_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
