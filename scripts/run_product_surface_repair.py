#!/usr/bin/env python3
"""Retry failed product-surface exports with bounded repair settings."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _result_by_output(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for result in summary.get("results", []):
        if not isinstance(result, dict):
            continue
        output_path = str(result.get("output_path") or "")
        if output_path:
            results[output_path] = result
    return results


def _failure_category(error: str) -> str:
    lowered = error.lower()
    if "timed out" in lowered or "timeoutexpired" in lowered or "timeout" in lowered:
        return "timeout"
    if "no markdown" in lowered:
        return "no_markdown"
    if "empty" in lowered:
        return "empty_extraction"
    return "scout_failure"


def _result_category(result: dict[str, Any]) -> str:
    if result.get("status") == "empty" or int(result.get("row_count") or 0) == 0 and result.get("status") == "succeeded":
        return "empty_extraction"
    return _failure_category(str(result.get("error") or ""))


def _matches_target(
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    company_name: str | None,
    company_id: int | None,
    surface_id: int | None,
    category: str | None,
) -> bool:
    if result.get("status") not in {"failed", "empty"}:
        return False
    target = item.get("target")
    if not isinstance(target, dict):
        target = {}
    if company_name and _norm(str(target.get("company_name") or "")) != _norm(company_name):
        return False
    if company_id is not None and int(target.get("company_id") or -1) != company_id:
        return False
    if surface_id is not None and int(target.get("surface_id") or -1) != surface_id:
        return False
    if category and _result_category(result) != category:
        return False
    return True


def select_failed_items(
    plan: dict[str, Any],
    summary: dict[str, Any],
    *,
    company_name: str | None,
    company_id: int | None,
    surface_id: int | None,
    category: str | None,
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    result_by_output = _result_by_output(summary)
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        output_path = str(item.get("output_path") or "")
        result = result_by_output.get(output_path)
        if not result:
            continue
        if _matches_target(
            item,
            result,
            company_name=company_name,
            company_id=company_id,
            surface_id=surface_id,
            category=category,
        ):
            selected.append((item, result))
        if len(selected) >= limit:
            break
    return selected


def _repair_output_path(original_output_path: str, repair_output_dir: Path) -> Path:
    original = Path(original_output_path)
    if original.suffix:
        filename = f"{original.stem}.repair{original.suffix}"
    else:
        filename = f"{original.name}.repair.json"
    return repair_output_dir / filename


def _set_flag_value(command: list[str], flag: str, value: str) -> None:
    if flag in command:
        index = command.index(flag)
        if index + 1 < len(command):
            command[index + 1] = value
            return
    command.extend([flag, value])


def _ensure_flag(command: list[str], flag: str) -> None:
    if flag in command:
        return
    if "--output" in command:
        command.insert(command.index("--output"), flag)
    else:
        command.append(flag)


def build_repair_command(
    item: dict[str, Any],
    *,
    repair_output_dir: Path,
    repair_timeout_seconds: float,
    use_js: bool,
) -> tuple[list[str], Path]:
    command = [str(part) for part in item.get("command", [])]
    if not command:
        raise ValueError("plan item missing command")
    output_path = _repair_output_path(str(item.get("output_path") or ""), repair_output_dir)
    _set_flag_value(command, "--timeout-seconds", _number_arg(repair_timeout_seconds))
    _set_flag_value(command, "--output", str(output_path))
    if use_js:
        _ensure_flag(command, "--js")
    return command, output_path


def execute_repair_item(
    item: dict[str, Any],
    original_result: dict[str, Any],
    *,
    repair_output_dir: Path,
    repair_timeout_seconds: float,
    command_timeout_seconds: float,
    use_js: bool,
) -> dict[str, Any]:
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    original_output_path = str(item.get("output_path") or "")
    command, output_path = build_repair_command(
        item,
        repair_output_dir=repair_output_dir,
        repair_timeout_seconds=repair_timeout_seconds,
        use_js=use_js,
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=command_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "target": target,
            "category": _result_category(original_result),
            "original_output_path": original_output_path,
            "output_path": str(output_path),
            "command": command,
            "error": f"repair retry timed out after {command_timeout_seconds:g}s",
            "returncode": None,
            "row_count": 0,
        }

    if completed.returncode != 0:
        return {
            "status": "failed",
            "target": target,
            "category": _result_category(original_result),
            "original_output_path": original_output_path,
            "output_path": str(output_path),
            "command": command,
            "error": _concise_error(completed.stderr or completed.stdout),
            "returncode": completed.returncode,
            "row_count": 0,
        }
    if not output_path.exists():
        return {
            "status": "failed",
            "target": target,
            "category": _result_category(original_result),
            "original_output_path": original_output_path,
            "output_path": str(output_path),
            "command": command,
            "error": "expected repair output file was not created",
            "returncode": completed.returncode,
            "row_count": 0,
        }
    row_count = _row_count(output_path)
    if row_count == 0:
        return {
            "status": "empty",
            "target": target,
            "category": _result_category(original_result),
            "original_output_path": original_output_path,
            "output_path": str(output_path),
            "command": command,
            "error": "repair retry produced no product rows",
            "returncode": completed.returncode,
            "row_count": 0,
        }
    return {
        "status": "succeeded",
        "target": target,
        "category": _result_category(original_result),
        "original_output_path": original_output_path,
        "output_path": str(output_path),
        "command": command,
        "returncode": completed.returncode,
        "row_count": row_count,
    }


def execute_repair(
    *,
    plan: dict[str, Any],
    summary: dict[str, Any],
    company_name: str | None,
    company_id: int | None,
    surface_id: int | None,
    category: str | None,
    limit: int,
    repair_output_dir: Path,
    repair_timeout_seconds: float,
    command_timeout_seconds: float,
    use_js: bool,
) -> dict[str, Any]:
    selected = select_failed_items(
        plan,
        summary,
        company_name=company_name,
        company_id=company_id,
        surface_id=surface_id,
        category=category,
        limit=limit,
    )
    if not selected:
        return {
            "status": "no_matching_repairable_surface",
            "tenant_id": plan.get("tenant_id"),
            "selected": 0,
            "succeeded": 0,
            "failed": 0,
            "results": [],
            "generated_at": _now(),
        }

    repair_output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        execute_repair_item(
            item,
            result,
            repair_output_dir=repair_output_dir,
            repair_timeout_seconds=repair_timeout_seconds,
            command_timeout_seconds=command_timeout_seconds,
            use_js=use_js,
        )
        for item, result in selected
    ]
    succeeded = [result for result in results if result["status"] == "succeeded"]
    empty = [result for result in results if result["status"] == "empty"]
    failed = [result for result in results if result["status"] == "failed"]
    incomplete = empty + failed
    return {
        "status": "succeeded" if succeeded and not incomplete else "partial" if succeeded else "failed",
        "tenant_id": plan.get("tenant_id"),
        "selected": len(selected),
        "succeeded": len(succeeded),
        "empty": len(empty),
        "failed": len(failed),
        "repair_output_dir": str(repair_output_dir),
        "scout_paths": [result["output_path"] for result in succeeded],
        "results": results,
        "generated_at": _now(),
    }


def _row_count(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("records", "rows", "product_events", "changes"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return len(rows)
    return 0


def _concise_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Traceback"):
            continue
        return line[:500]
    return "repair retry failed"


def _number_arg(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry selected failed CI-OS product-surface exports.")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--execution-summary", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--repair-output-dir", required=True, type=Path)
    parser.add_argument("--company-name")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--surface-id", type=int)
    parser.add_argument(
        "--category",
        choices=["timeout", "no_markdown", "empty_extraction", "scout_failure"],
    )
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--repair-timeout-seconds", type=float, default=240)
    parser.add_argument("--command-timeout-seconds", type=float, default=300)
    parser.add_argument("--js", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = execute_repair(
        plan=_json_object(args.plan),
        summary=_json_object(args.execution_summary),
        company_name=args.company_name,
        company_id=args.company_id,
        surface_id=args.surface_id,
        category=args.category,
        limit=max(1, args.limit),
        repair_output_dir=args.repair_output_dir,
        repair_timeout_seconds=args.repair_timeout_seconds,
        command_timeout_seconds=args.command_timeout_seconds,
        use_js=args.js,
    )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if summary["status"] == "no_matching_repairable_surface":
        return 2
    return 0 if summary["succeeded"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
