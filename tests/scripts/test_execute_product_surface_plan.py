"""Tests for executing product-surface export plans."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "execute_product_surface_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("execute_product_surface_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_execute_product_surface_plan_runs_commands_and_writes_summary(tmp_path) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    summary_path = tmp_path / "summary.json"
    scout_output = tmp_path / "000011-constructor-changelog.json"
    command = [
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps(["
            "{'company_name':'Constructor'}"
            "]))"
        ),
        str(scout_output),
    ]
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "target_count": 1,
                "items": [
                    {
                        "target": {
                            "surface_id": 11,
                            "tenant_id": 1,
                            "company_id": 20,
                            "company_name": "Constructor",
                            "company_role": "competitor",
                            "surface_family": "changelog",
                            "url": "https://constructor.com/changelog",
                        },
                        "output_path": str(scout_output),
                        "command": command,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code = module.main([
        "--plan",
        str(plan_path),
        "--summary-output",
        str(summary_path),
        "--command-timeout-seconds",
        "5",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["succeeded"] == 1
    assert summary["failed"] == 0
    assert summary["empty"] == 0
    assert summary["product_plane_status"] == "ready"
    assert summary["product_row_count"] == 1
    assert summary["scout_paths"] == [str(scout_output)]
    assert summary["empty_scout_paths"] == []
    assert summary["company_row_counts"] == {"Constructor": 1}
    assert summary["surface_family_row_counts"] == {"changelog": 1}
    assert summary["results"][0]["row_count"] == 1
    assert json.loads(scout_output.read_text(encoding="utf-8")) == [
        {"company_name": "Constructor"}
    ]


def test_execute_product_surface_plan_carries_focus_capability_into_results(tmp_path) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    summary_path = tmp_path / "summary.json"
    scout_output = tmp_path / "focused.json"
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "target_count": 1,
                "items": [
                    {
                        "target": {
                            "company_name": "Coveo",
                            "surface_family": "docs",
                        },
                        "focus_capability": "Channel Assistant",
                        "output_path": str(scout_output),
                        "command": [
                            sys.executable,
                            "-c",
                            "import json, sys; open(sys.argv[1], 'w').write(json.dumps([{'company_name':'Coveo'}]))",
                            str(scout_output),
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code = module.main([
        "--plan",
        str(plan_path),
        "--summary-output",
        str(summary_path),
        "--command-timeout-seconds",
        "5",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["results"][0]["focus_capability"] == "Channel Assistant"


def test_execute_product_surface_plan_allows_partial_success_with_failures_recorded(tmp_path) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    summary_path = tmp_path / "summary.json"
    good_output = tmp_path / "good.json"
    bad_output = tmp_path / "bad.json"
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "items": [
                    {
                        "output_path": str(good_output),
                        "target": {
                            "company_name": "Constructor",
                            "surface_family": "changelog",
                        },
                        "command": [
                            sys.executable,
                            "-c",
                            "import json, sys; open(sys.argv[1], 'w').write(json.dumps([{'company_name':'Constructor'}]))",
                            str(good_output),
                        ],
                    },
                    {
                        "output_path": str(bad_output),
                        "command": [sys.executable, "-c", "import sys; print('blocked', file=sys.stderr); sys.exit(1)"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    code = module.main([
        "--plan",
        str(plan_path),
        "--summary-output",
        str(summary_path),
        "--command-timeout-seconds",
        "5",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["succeeded"] == 1
    assert summary["empty"] == 0
    assert summary["failed"] == 1
    assert summary["product_plane_status"] == "degraded"
    assert summary["product_row_count"] == 1
    assert summary["scout_paths"] == [str(good_output)]
    assert summary["company_row_counts"] == {"Constructor": 1}
    assert summary["results"][1]["status"] == "failed"


def test_execute_product_surface_plan_marks_empty_outputs_without_treating_them_as_product_proof(tmp_path) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    summary_path = tmp_path / "summary.json"
    empty_output = tmp_path / "empty.json"
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "items": [
                    {
                        "output_path": str(empty_output),
                        "target": {
                            "company_name": "Coveo",
                            "surface_family": "docs",
                        },
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; open(sys.argv[1], 'w').write('[]')",
                            str(empty_output),
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    code = module.main([
        "--plan",
        str(plan_path),
        "--summary-output",
        str(summary_path),
        "--command-timeout-seconds",
        "5",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["product_plane_status"] == "empty"
    assert summary["succeeded"] == 0
    assert summary["empty"] == 1
    assert summary["failed"] == 0
    assert summary["product_row_count"] == 0
    assert summary["scout_paths"] == []
    assert summary["empty_scout_paths"] == [str(empty_output)]
    assert summary["empty_outputs"] == [
        {
            "output_path": str(empty_output),
            "company_name": "Coveo",
            "surface_family": "docs",
        }
    ]
    assert summary["results"][0]["status"] == "empty"


def test_execute_plan_uses_bounded_parallel_workers(monkeypatch) -> None:
    module = _load_module()
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_execute_item(item, *, timeout_seconds):
        nonlocal active, max_active
        del timeout_seconds
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {
            "status": "succeeded",
            "output_path": item["output_path"],
            "returncode": 0,
        }

    monkeypatch.setattr(module.executor_module, "_execute_item", fake_execute_item)
    plan = {
        "tenant_id": 1,
        "items": [{"output_path": f"/tmp/surface-{index}.json", "command": ["true"]} for index in range(5)],
    }

    summary = module.execute_plan(plan, timeout_seconds=5, max_workers=2)

    assert summary["planned"] == 5
    assert summary["succeeded"] == 5
    assert max_active == 2
    assert summary["scout_paths"] == [f"/tmp/surface-{index}.json" for index in range(5)]


def test_execute_plan_item_timeout_kills_descendant_process_group(tmp_path) -> None:
    module = _load_module()
    orphan_marker = tmp_path / "orphan-wrote-after-timeout.txt"
    child_code = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(0.8); "
        "pathlib.Path(sys.argv[1]).write_text('orphan', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, sys.argv[1]]); "
        "time.sleep(5)"
    )
    plan = {
        "tenant_id": 1,
        "items": [
            {
                "output_path": str(tmp_path / "never-created.json"),
                "command": [sys.executable, "-c", parent_code, str(orphan_marker)],
            }
        ],
    }

    summary = module.execute_plan(plan, timeout_seconds=0.2, max_workers=1)
    time.sleep(1.0)

    assert summary["failed"] == 1
    assert summary["timed_out"] == 1
    assert summary["not_started"] == 0
    assert summary["results"][0]["status"] == "timed_out"
    assert summary["results"][0]["error"] == "timed out after 0.2s"
    assert not orphan_marker.exists()


def test_execute_plan_batch_timeout_records_every_item_and_kills_active_groups(tmp_path) -> None:
    module = _load_module()
    items = []
    for index in range(4):
        marker = tmp_path / f"late-{index}.txt"
        code = (
            "import pathlib, sys, time; "
            "time.sleep(1); "
            "pathlib.Path(sys.argv[1]).write_text('late', encoding='utf-8')"
        )
        items.append(
            {
                "output_path": str(tmp_path / f"output-{index}.json"),
                "command": [sys.executable, "-c", code, str(marker)],
            }
        )

    started = time.monotonic()
    summary = module.execute_plan(
        {"tenant_id": 1, "items": items},
        timeout_seconds=5,
        batch_timeout_seconds=0.2,
        max_workers=2,
    )
    elapsed = time.monotonic() - started
    time.sleep(1.1)

    assert elapsed < 1.0
    assert len(summary["results"]) == 4
    assert summary["batch_timed_out"] is True
    assert summary["timed_out"] == 2
    assert summary["not_started"] == 2
    assert summary["failed"] == 4
    assert [result["status"] for result in summary["results"]] == [
        "timed_out",
        "timed_out",
        "not_started",
        "not_started",
    ]
    assert not list(tmp_path.glob("late-*.txt"))


def test_executor_sigterm_kills_active_item_process_group(tmp_path) -> None:
    plan_path = tmp_path / "plan.json"
    summary_path = tmp_path / "summary.json"
    started_marker = tmp_path / "item-started.txt"
    orphan_marker = tmp_path / "orphan-after-executor-sigterm.txt"
    child_code = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(0.8); "
        "pathlib.Path(sys.argv[1]).write_text('orphan', encoding='utf-8')"
    )
    parent_code = (
        "import pathlib, subprocess, sys, time; "
        "pathlib.Path(sys.argv[1]).write_text('started', encoding='utf-8'); "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, sys.argv[2]]); "
        "time.sleep(5)"
    )
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "items": [
                    {
                        "output_path": str(tmp_path / "never-created.json"),
                        "command": [
                            sys.executable,
                            "-c",
                            parent_code,
                            str(started_marker),
                            str(orphan_marker),
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    executor = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--plan",
            str(plan_path),
            "--summary-output",
            str(summary_path),
            "--command-timeout-seconds",
            "5",
            "--batch-timeout-seconds",
            "4",
        ],
        start_new_session=True,
    )
    deadline = time.monotonic() + 2
    while not started_marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert started_marker.exists()

    os.killpg(executor.pid, signal.SIGTERM)
    executor.wait(timeout=3)
    time.sleep(1.0)

    assert executor.returncode != 0
    assert not orphan_marker.exists()
