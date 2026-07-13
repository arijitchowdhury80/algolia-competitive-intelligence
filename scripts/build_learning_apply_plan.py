#!/usr/bin/env python3
"""Build a gated CI-OS learning apply plan from a next-sweep plan.

Hermes may call this after `build_next_sweep_learning_plan.py` to make
approved Argus learning durable as package-scoped work. The command does not
apply changes. It emits the exact CI-OS policy/config targets an operator or
future gated apply runner should review, preserving evidence/improvement
traceability and the Hermes-core boundary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.learn.feedback import LearningApplyPlanner, NextSweepInstruction


def _load_plan(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("next-sweep plan must be a JSON object")
    instructions = data.get("instructions")
    if not isinstance(instructions, list):
        raise ValueError("next-sweep plan instructions must be a list")
    return data


def build_apply_plan_payload(path: Path, *, tenant_id: int | None = None) -> dict[str, Any]:
    data = _load_plan(path)
    plan_tenant_id = data.get("tenant_id")
    resolved_tenant_id = tenant_id if tenant_id is not None else plan_tenant_id
    if resolved_tenant_id is None:
        raise ValueError("tenant_id must be supplied by the plan or --tenant-id")
    resolved_tenant_id = int(resolved_tenant_id)
    if plan_tenant_id is not None and int(plan_tenant_id) != resolved_tenant_id:
        raise ValueError("next-sweep plan tenant_id does not match requested tenant_id")

    instructions = [
        NextSweepInstruction.model_validate(item)
        for item in data.get("instructions", [])
    ]
    apply_plan = LearningApplyPlanner().build(
        tenant_id=resolved_tenant_id,
        instructions=instructions,
    )
    return apply_plan.model_dump(mode="json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, help="Path to next-sweep-learning-plan.json")
    parser.add_argument("--tenant-id", type=int, help="Optional tenant id override/check")
    parser.add_argument("--output", help="Optional JSON artifact path. Prints to stdout when omitted.")
    args = parser.parse_args(argv)

    payload = build_apply_plan_payload(Path(args.plan), tenant_id=args.tenant_id)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{encoded}\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
