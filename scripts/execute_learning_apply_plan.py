#!/usr/bin/env python3
"""Execute a CI-OS learning apply plan safely inside the package boundary.

Default behavior is proposal-only. Supplying `--approved-by` records approved,
idempotent config-policy entries for `config/*.yaml` targets. Manual-review
targets remain proposal-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.learn.apply import LearningApplyExecutor  # noqa: E402
from cios.learn.feedback import LearningApplyPlan  # noqa: E402


def _load_plan(path: Path) -> LearningApplyPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("learning apply plan must be a JSON object")
    return LearningApplyPlan.model_validate(data)


def execute_learning_apply_plan_payload(
    plan_path: Path,
    *,
    package_root: Path,
    approved_by: Optional[str] = None,
) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    result = LearningApplyExecutor(package_root=package_root).execute(
        plan,
        approved_by=approved_by,
    )
    return result.model_dump(mode="json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path, help="Path to learning-apply-plan.json")
    parser.add_argument(
        "--package-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Installed CI-OS package root.",
    )
    parser.add_argument(
        "--approved-by",
        help="Human approver id/name. Omit for proposal-only execution.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON result path. Prints to stdout when omitted.")
    args = parser.parse_args(argv)

    payload = execute_learning_apply_plan_payload(
        args.plan,
        package_root=args.package_root,
        approved_by=args.approved_by,
    )
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{encoded}\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
