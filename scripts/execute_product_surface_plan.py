#!/usr/bin/env python3
"""Execute a product-surface export plan and summarize produced Scout files."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from pathlib import Path
from typing import Any


def _load_plan(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _execute_item(item: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    command = list(item["command"])
    output_path = Path(item["output_path"])
    target = _target(item)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "failed",
            "output_path": str(output_path),
            "error": f"timed out after {timeout_seconds:g}s",
            "returncode": None,
        }

    if completed.returncode != 0:
        return {
            "status": "failed",
            "output_path": str(output_path),
            "error": completed.stderr.strip() or completed.stdout.strip(),
            "returncode": completed.returncode,
        }
    if not output_path.exists():
        return {
            "status": "failed",
            "output_path": str(output_path),
            "error": "expected output file was not created",
            "returncode": completed.returncode,
        }
    try:
        row_count = _row_count(output_path)
    except ValueError as exc:
        return {
            "status": "failed",
            "output_path": str(output_path),
            "error": str(exc),
            "returncode": completed.returncode,
            **target,
        }
    if row_count == 0:
        return {
            "status": "empty",
            "output_path": str(output_path),
            "returncode": completed.returncode,
            "row_count": 0,
            **target,
        }
    return {
        "status": "succeeded",
        "output_path": str(output_path),
        "returncode": completed.returncode,
        "row_count": row_count,
        **target,
    }


def execute_plan(plan: dict[str, Any], *, timeout_seconds: float, max_workers: int = 1) -> dict[str, Any]:
    items = list(plan.get("items", []))
    worker_count = max(1, int(max_workers))
    if worker_count == 1 or len(items) <= 1:
        results = [_execute_item(item, timeout_seconds=timeout_seconds) for item in items]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(
                    lambda item: _execute_item(item, timeout_seconds=timeout_seconds),
                    items,
                )
            )
    succeeded = [result for result in results if result["status"] == "succeeded"]
    empty = [result for result in results if result["status"] == "empty"]
    failed = [result for result in results if result["status"] == "failed"]
    scout_paths = [result["output_path"] for result in succeeded]
    empty_scout_paths = [result["output_path"] for result in empty]
    product_row_count = sum(int(result.get("row_count") or 0) for result in succeeded)
    return {
        "tenant_id": plan.get("tenant_id"),
        "planned": len(items),
        "succeeded": len(succeeded),
        "empty": len(empty),
        "failed": len(failed),
        "max_workers": worker_count,
        "product_plane_status": _product_plane_status(
            planned=len(items),
            succeeded=len(succeeded),
            empty=len(empty),
            failed=len(failed),
        ),
        "product_row_count": product_row_count,
        "scout_paths": scout_paths,
        "empty_scout_paths": empty_scout_paths,
        "empty_outputs": [_empty_output_summary(result) for result in empty],
        "company_row_counts": _row_counts_by(results, "company_name"),
        "surface_family_row_counts": _row_counts_by(results, "surface_family"),
        "results": results,
    }


def _target(item: dict[str, Any]) -> dict[str, Any]:
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    result = {
        "company_name": str(target.get("company_name") or "").strip(),
        "surface_family": str(target.get("surface_family") or "").strip(),
    }
    focus_capability = str(item.get("focus_capability") or "").strip()
    if focus_capability:
        result["focus_capability"] = focus_capability
    return result


def _row_count(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid product-surface output JSON: {path}") from exc
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return len(payload["records"])
    raise ValueError(f"product-surface output must be a JSON list or records object: {path}")


def _product_plane_status(*, planned: int, succeeded: int, empty: int, failed: int) -> str:
    if planned == 0:
        return "not_planned"
    if succeeded > 0 and (empty > 0 or failed > 0):
        return "degraded"
    if succeeded > 0:
        return "ready"
    if empty > 0 and failed == 0:
        return "empty"
    if empty > 0 and failed > 0:
        return "failed_empty"
    return "failed"


def _empty_output_summary(result: dict[str, Any]) -> dict[str, str]:
    return {
        "output_path": str(result.get("output_path") or ""),
        "company_name": str(result.get("company_name") or ""),
        "surface_family": str(result.get("surface_family") or ""),
    }


def _row_counts_by(results: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        label = str(result.get(key) or "").strip()
        row_count = int(result.get("row_count") or 0)
        if not label or row_count <= 0:
            continue
        counts[label] = counts.get(label, 0) + row_count
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--command-timeout-seconds", type=float, default=180)
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args(argv)

    summary = execute_plan(
        _load_plan(Path(args.plan)),
        timeout_seconds=args.command_timeout_seconds,
        max_workers=args.max_workers,
    )
    output = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if summary["failed"] == 0 or summary["succeeded"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
