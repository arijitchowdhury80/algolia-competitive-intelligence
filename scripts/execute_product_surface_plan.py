#!/usr/bin/env python3
"""Execute a product-surface export plan and summarize produced Scout files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.intelligence import product_surface_executor as executor_module  # noqa: E402
from cios.platform.process_supervisor import install_shutdown_handlers  # noqa: E402


execute_plan = executor_module.execute_plan


def _load_plan(path: Path) -> dict:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--command-timeout-seconds", type=float, default=180)
    parser.add_argument("--batch-timeout-seconds", type=float, default=600)
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args(argv)

    summary = execute_plan(
        _load_plan(Path(args.plan)),
        timeout_seconds=args.command_timeout_seconds,
        batch_timeout_seconds=args.batch_timeout_seconds,
        max_workers=args.max_workers,
    )
    output = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if summary["failed"] == 0 or summary["succeeded"] > 0 else 1


if __name__ == "__main__":
    install_shutdown_handlers()
    raise SystemExit(main())
