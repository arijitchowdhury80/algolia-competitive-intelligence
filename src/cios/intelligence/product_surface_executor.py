"""Execute a bounded product-surface plan with complete terminal accounting."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from cios.platform.process_supervisor import PROCESS_GROUPS


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


def _terminal_result(item: dict[str, Any], *, status: str, error: str) -> dict[str, Any]:
    return {
        "status": status,
        "output_path": str(Path(item["output_path"])),
        "error": error,
        "returncode": None,
        **_target(item),
    }


def _wait_for_command(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float,
    cancel_event: threading.Event | None,
) -> tuple[str, str, str, str | None]:
    started = time.monotonic()
    while True:
        if cancel_event is not None and cancel_event.is_set():
            PROCESS_GROUPS.terminate(process)
            stdout, stderr = process.communicate()
            return "timed_out", stdout, stderr, "batch deadline elapsed while item was running"
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            PROCESS_GROUPS.terminate(process)
            stdout, stderr = process.communicate()
            return "failed", stdout, stderr, f"timed out after {timeout_seconds:g}s"
        try:
            stdout, stderr = process.communicate(timeout=min(0.1, remaining))
            return "completed", stdout, stderr, None
        except subprocess.TimeoutExpired:
            continue


def _run_item_command(
    item: dict[str, Any],
    *,
    timeout_seconds: float,
    cancel_event: threading.Event | None,
) -> tuple[str, str, str, str | None, int | None]:
    if cancel_event is not None and cancel_event.is_set():
        return "not_started", "", "", "batch deadline elapsed before item started", None
    process = subprocess.Popen(
        list(item["command"]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    PROCESS_GROUPS.register(process)
    try:
        status, stdout, stderr, error = _wait_for_command(
            process,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        return status, stdout, stderr, error, process.returncode
    finally:
        PROCESS_GROUPS.unregister(process)


def _execute_item(
    item: dict[str, Any],
    *,
    timeout_seconds: float,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    status, stdout, stderr, error, returncode = _run_item_command(
        item,
        timeout_seconds=timeout_seconds,
        cancel_event=cancel_event,
    )
    if status != "completed":
        result = _terminal_result(item, status=status, error=str(error or status))
        result["returncode"] = returncode
        return result
    output_path = Path(item["output_path"])
    if returncode != 0:
        result = _terminal_result(item, status="failed", error=stderr.strip() or stdout.strip())
        result["returncode"] = returncode
        return result
    if not output_path.exists():
        return _terminal_result(item, status="failed", error="expected output file was not created")
    try:
        row_count = _row_count(output_path)
    except ValueError as exc:
        return _terminal_result(item, status="failed", error=str(exc))
    return {
        "status": "empty" if row_count == 0 else "succeeded",
        "output_path": str(output_path),
        "returncode": returncode,
        "row_count": row_count,
        **_target(item),
    }


def _execute_with_batch_deadline(
    items: list[dict[str, Any]],
    *,
    timeout_seconds: float,
    batch_timeout_seconds: float,
    worker_count: int,
) -> tuple[list[dict[str, Any]], bool]:
    cancel_event = threading.Event()
    ordered: list[dict[str, Any] | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _execute_item,
                item,
                timeout_seconds=timeout_seconds,
                cancel_event=cancel_event,
            ): index
            for index, item in enumerate(items)
        }
        _, pending = wait(futures, timeout=batch_timeout_seconds)
        if pending:
            cancel_event.set()
            for future in pending:
                future.cancel()
        wait(futures)
        for future, index in futures.items():
            ordered[index] = (
                _terminal_result(
                    items[index],
                    status="not_started",
                    error="batch deadline elapsed before item started",
                )
                if future.cancelled()
                else future.result()
            )
    return [result for result in ordered if result is not None], bool(pending)


def _execute_without_batch_deadline(
    items: list[dict[str, Any]],
    *,
    timeout_seconds: float,
    worker_count: int,
) -> list[dict[str, Any]]:
    if worker_count == 1 or len(items) <= 1:
        return [_execute_item(item, timeout_seconds=timeout_seconds) for item in items]
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(
            executor.map(
                lambda item: _execute_item(item, timeout_seconds=timeout_seconds),
                items,
            )
        )


def execute_plan(
    plan: dict[str, Any],
    *,
    timeout_seconds: float,
    batch_timeout_seconds: float | None = None,
    max_workers: int = 1,
) -> dict[str, Any]:
    items = list(plan.get("items", []))
    worker_count = max(1, int(max_workers))
    if batch_timeout_seconds is not None and batch_timeout_seconds <= 0:
        raise ValueError("batch timeout must be greater than zero")
    if batch_timeout_seconds is None:
        results = _execute_without_batch_deadline(
            items,
            timeout_seconds=timeout_seconds,
            worker_count=worker_count,
        )
        batch_timed_out = False
    else:
        results, batch_timed_out = _execute_with_batch_deadline(
            items,
            timeout_seconds=timeout_seconds,
            batch_timeout_seconds=batch_timeout_seconds,
            worker_count=worker_count,
        )
    return _summarize(
        plan,
        results,
        worker_count=worker_count,
        batch_timed_out=batch_timed_out,
        batch_timeout_seconds=batch_timeout_seconds,
    )


def _summarize(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    worker_count: int,
    batch_timed_out: bool,
    batch_timeout_seconds: float | None,
) -> dict[str, Any]:
    by_status = {
        status: [result for result in results if result["status"] == status]
        for status in ("succeeded", "empty", "failed", "timed_out", "not_started")
    }
    failed_count = sum(len(by_status[status]) for status in ("failed", "timed_out", "not_started"))
    return {
        "tenant_id": plan.get("tenant_id"),
        "planned": len(list(plan.get("items", []))),
        "succeeded": len(by_status["succeeded"]),
        "empty": len(by_status["empty"]),
        "failed": failed_count,
        "timed_out": len(by_status["timed_out"]),
        "not_started": len(by_status["not_started"]),
        "batch_timed_out": batch_timed_out,
        "batch_timeout_seconds": batch_timeout_seconds,
        "max_workers": worker_count,
        "product_plane_status": _product_plane_status(
            planned=len(results),
            succeeded=len(by_status["succeeded"]),
            empty=len(by_status["empty"]),
            failed=failed_count,
        ),
        "product_row_count": sum(int(result.get("row_count") or 0) for result in by_status["succeeded"]),
        "scout_paths": [result["output_path"] for result in by_status["succeeded"]],
        "empty_scout_paths": [result["output_path"] for result in by_status["empty"]],
        "empty_outputs": [_empty_output_summary(result) for result in by_status["empty"]],
        "company_row_counts": _row_counts_by(results, "company_name"),
        "surface_family_row_counts": _row_counts_by(results, "surface_family"),
        "results": results,
    }


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
        if label and row_count > 0:
            counts[label] = counts.get(label, 0) + row_count
    return dict(sorted(counts.items()))
