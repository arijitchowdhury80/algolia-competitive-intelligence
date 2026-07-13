#!/usr/bin/env python3
"""Export the current Argus demand collection plan as a CSV work order."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.admin.demand_imports import demand_collection_plan_operator_guide, demand_collection_plan_template_csv


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_csv_from_readiness(readiness: dict[str, Any]) -> str:
    plan = readiness.get("demand_collection_plan")
    return demand_collection_plan_template_csv(plan if isinstance(plan, dict) else {})


def build_guide_from_readiness(readiness: dict[str, Any], *, tenant_slug: str) -> dict[str, Any]:
    plan = readiness.get("demand_collection_plan")
    return demand_collection_plan_operator_guide(plan if isinstance(plan, dict) else {}, tenant_slug=tenant_slug)


def write_csv(content: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def write_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Argus demand plan CSV template.")
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--guide-output", type=Path)
    parser.add_argument("--tenant", default="algolia")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    readiness = _load_json(args.readiness)
    write_csv(build_csv_from_readiness(readiness), args.output)
    if args.guide_output is not None:
        write_json(build_guide_from_readiness(readiness, tenant_slug=args.tenant), args.guide_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
