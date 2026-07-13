"""Tests for executing product-surface export plans."""

from __future__ import annotations

import importlib.util
import json
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

    monkeypatch.setattr(module, "_execute_item", fake_execute_item)
    plan = {
        "tenant_id": 1,
        "items": [{"output_path": f"/tmp/surface-{index}.json", "command": ["true"]} for index in range(5)],
    }

    summary = module.execute_plan(plan, timeout_seconds=5, max_workers=2)

    assert summary["planned"] == 5
    assert summary["succeeded"] == 5
    assert max_active == 2
    assert summary["scout_paths"] == [f"/tmp/surface-{index}.json" for index in range(5)]
