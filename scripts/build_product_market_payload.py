#!/usr/bin/env python3
"""Build a product-market runner payload from collector export files.

This script is intentionally a CI-OS package utility. Hermes can schedule it
before `scripts/run_product_market_intelligence.py`, but no Hermes core code
is modified or imported here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.intelligence.demand_quality import DemandQualityConfig
from cios.intelligence.importers import build_payload_from_exports
from cios.intelligence.scout_adapter import ScoutCommandSpec, run_scout_export


def _path(value: str | None) -> Path | None:
    return None if value is None else Path(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--own-company-name", required=True)
    parser.add_argument("--tenant-id", type=int)
    parser.add_argument(
        "--scout",
        action="append",
        default=[],
        help="Scout product/changelog export, JSON/JSONL/CSV. Repeatable.",
    )
    parser.add_argument(
        "--scout-command-json",
        action="append",
        default=[],
        help="JSON ScoutCommandSpec to execute before building the payload. Repeatable.",
    )
    parser.add_argument("--conversation", help="Conversation/narrative export, JSON/JSONL/CSV")
    parser.add_argument(
        "--looker",
        action="append",
        default=[],
        help="Looker/GA export, JSON/JSONL/CSV. Repeatable.",
    )
    parser.add_argument(
        "--learning-plan",
        help="Next-sweep learning plan JSON from build_next_sweep_learning_plan.py.",
    )
    parser.add_argument("--demand-change-floor", type=float, help="Minimum fractional demand lift for rising demand")
    parser.add_argument("--demand-value-floor", type=float, help="Minimum metric value for rising demand")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    scout_records = []
    for raw_command in args.scout_command_json:
        spec = ScoutCommandSpec.model_validate_json(raw_command)
        scout_records.extend(run_scout_export(spec))

    payload = build_payload_from_exports(
        own_company_name=args.own_company_name,
        tenant_id=args.tenant_id,
        scout_paths=[Path(path) for path in args.scout],
        scout_records=scout_records,
        conversation_path=_path(args.conversation),
        looker_paths=[Path(path) for path in args.looker],
        learning_plan_path=_path(args.learning_plan),
    )
    if args.demand_change_floor is not None or args.demand_value_floor is not None:
        default_quality = DemandQualityConfig()
        payload = payload.model_copy(
            update={
                "demand_quality": DemandQualityConfig(
                    change_floor=(
                        default_quality.change_floor
                        if args.demand_change_floor is None
                        else args.demand_change_floor
                    ),
                    value_floor=(
                        default_quality.value_floor
                        if args.demand_value_floor is None
                        else args.demand_value_floor
                    ),
                )
            }
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
