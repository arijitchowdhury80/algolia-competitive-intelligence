#!/usr/bin/env python3
"""Audit approved CI-OS learning policies before Hermes production runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.learn.apply import audit_learning_policies  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Installed CI-OS package root.",
    )
    parser.add_argument("--tenant-id", type=int, help="Optional tenant id to audit.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    result = audit_learning_policies(args.package_root, tenant_id=args.tenant_id)
    payload = result.model_dump(mode="json")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif result.passed:
        print(
            "PASS: CI-OS learning policy audit clean "
            f"policies={result.policy_count} ok={result.ok_count}"
        )
    else:
        print(
            "FAIL: CI-OS learning policy audit found issues "
            f"policies={result.policy_count} issues={result.issue_count}",
            file=sys.stderr,
        )
        for issue in result.issues:
            print(
                f"{issue.code}: {issue.package_path}: {issue.message}. {issue.rollback_hint}",
                file=sys.stderr,
            )
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
