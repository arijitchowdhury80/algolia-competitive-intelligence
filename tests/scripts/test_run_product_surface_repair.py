"""Tests for bounded product-surface repair retries."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_product_surface_repair.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_product_surface_repair", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_plan_and_summary(tmp_path: Path) -> tuple[Path, Path]:
    coveo_output = tmp_path / "exports" / "000030-coveo-docs.json"
    constructor_output = tmp_path / "exports" / "000011-constructor-changelog.json"
    plan_path = tmp_path / "product-surface-plan.json"
    summary_path = tmp_path / "product-surface-execution-summary.json"
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "items": [
                    {
                        "target": {
                            "surface_id": 30,
                            "tenant_id": 1,
                            "company_id": 3,
                            "company_name": "Coveo",
                            "company_role": "competitor",
                            "surface_family": "docs",
                            "url": "https://www.coveo.com/en/docs",
                        },
                        "output_path": str(coveo_output),
                        "command": [
                            sys.executable,
                            "scripts/export_product_surface_with_scout.py",
                            "--tenant-id",
                            "1",
                            "--company-id",
                            "3",
                            "--company-name",
                            "Coveo",
                            "--company-role",
                            "competitor",
                            "--surface-family",
                            "docs",
                            "--url",
                            "https://www.coveo.com/en/docs",
                            "--scout-bin",
                            "scout",
                            "--provider",
                            "gemini/gemini-2.5-flash",
                            "--timeout-seconds",
                            "120",
                            "--output",
                            str(coveo_output),
                        ],
                    },
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
                        "output_path": str(constructor_output),
                        "command": [
                            sys.executable,
                            "scripts/export_product_surface_with_scout.py",
                            "--tenant-id",
                            "1",
                            "--company-id",
                            "20",
                            "--company-name",
                            "Constructor",
                            "--company-role",
                            "competitor",
                            "--surface-family",
                            "changelog",
                            "--url",
                            "https://constructor.com/changelog",
                            "--scout-bin",
                            "scout",
                            "--provider",
                            "gemini/gemini-2.5-flash",
                            "--timeout-seconds",
                            "120",
                            "--output",
                            str(constructor_output),
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "results": [
                    {
                        "status": "failed",
                        "output_path": str(coveo_output),
                        "error": "Scout product surface scrape returned no markdown",
                        "returncode": 1,
                    },
                    {
                        "status": "succeeded",
                        "output_path": str(constructor_output),
                        "returncode": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return plan_path, summary_path


def test_repair_retries_only_matching_failed_surface_with_js_and_higher_timeout(
    monkeypatch,
    tmp_path,
) -> None:
    module = _load_module()
    plan_path, summary_path = _write_plan_and_summary(tmp_path)
    repair_dir = tmp_path / "repairs"
    repair_summary = tmp_path / "repair-summary.json"
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        output_path = Path(command[command.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps([{"company_name": "Coveo"}]), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--plan",
            str(plan_path),
            "--execution-summary",
            str(summary_path),
            "--company-name",
            "Coveo",
            "--category",
            "no_markdown",
            "--repair-output-dir",
            str(repair_dir),
            "--summary-output",
            str(repair_summary),
            "--repair-timeout-seconds",
            "240",
            "--command-timeout-seconds",
            "260",
            "--js",
        ]
    )

    payload = json.loads(repair_summary.read_text(encoding="utf-8"))
    assert code == 0
    assert len(commands) == 1
    command = commands[0]
    assert "--js" in command
    assert command[command.index("--timeout-seconds") + 1] == "240"
    assert Path(command[command.index("--output") + 1]) == repair_dir / "000030-coveo-docs.repair.json"
    assert payload["selected"] == 1
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0
    assert payload["results"][0]["target"]["company_name"] == "Coveo"
    assert payload["results"][0]["original_output_path"].endswith("000030-coveo-docs.json")
    assert payload["results"][0]["row_count"] == 1


def test_repair_summarizes_failed_retry_without_traceback(monkeypatch, tmp_path) -> None:
    module = _load_module()
    plan_path, summary_path = _write_plan_and_summary(tmp_path)
    repair_summary = tmp_path / "repair-summary.json"

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "Traceback...\nScout scrape blocked")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--plan",
            str(plan_path),
            "--execution-summary",
            str(summary_path),
            "--company-name",
            "Coveo",
            "--repair-output-dir",
            str(tmp_path / "repairs"),
            "--summary-output",
            str(repair_summary),
            "--repair-timeout-seconds",
            "240",
            "--command-timeout-seconds",
            "260",
        ]
    )

    payload = json.loads(repair_summary.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["selected"] == 1
    assert payload["succeeded"] == 0
    assert payload["failed"] == 1
    assert payload["results"][0]["error"] == "Scout scrape blocked"
    assert "Traceback" not in payload["results"][0]["error"]


def test_repair_exits_without_running_when_no_matching_repairable_surface(monkeypatch, tmp_path) -> None:
    module = _load_module()
    plan_path, summary_path = _write_plan_and_summary(tmp_path)
    repair_summary = tmp_path / "repair-summary.json"

    def fake_run(command, **kwargs):
        raise AssertionError(f"repair should not execute: {command}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--plan",
            str(plan_path),
            "--execution-summary",
            str(summary_path),
            "--company-name",
            "Constructor",
            "--repair-output-dir",
            str(tmp_path / "repairs"),
            "--summary-output",
            str(repair_summary),
        ]
    )

    payload = json.loads(repair_summary.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["status"] == "no_matching_repairable_surface"
    assert payload["selected"] == 0


def test_repair_retries_empty_successful_surface_outputs(monkeypatch, tmp_path) -> None:
    module = _load_module()
    plan_path, summary_path = _write_plan_and_summary(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    coveo_result = summary["results"][0]
    coveo_result["status"] = "empty"
    coveo_result["error"] = "Scout export completed but produced zero product rows"
    coveo_result["returncode"] = 0
    coveo_result["row_count"] = 0
    summary["product_plane_status"] = "empty"
    summary["empty"] = 1
    summary["empty_outputs"] = [
        {
            "output_path": coveo_result["output_path"],
            "company_name": "Coveo",
            "surface_family": "docs",
        }
    ]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    repair_dir = tmp_path / "repairs"
    repair_summary = tmp_path / "repair-summary.json"
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        output_path = Path(command[command.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"product_events": [{"company_name": "Coveo"}]}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--plan",
            str(plan_path),
            "--execution-summary",
            str(summary_path),
            "--company-name",
            "Coveo",
            "--category",
            "empty_extraction",
            "--repair-output-dir",
            str(repair_dir),
            "--summary-output",
            str(repair_summary),
            "--repair-timeout-seconds",
            "240",
            "--command-timeout-seconds",
            "260",
            "--js",
        ]
    )

    payload = json.loads(repair_summary.read_text(encoding="utf-8"))
    assert code == 0
    assert len(commands) == 1
    assert payload["status"] == "succeeded"
    assert payload["selected"] == 1
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0
    assert payload["results"][0]["category"] == "empty_extraction"
    assert payload["results"][0]["target"]["company_name"] == "Coveo"
    assert payload["results"][0]["row_count"] == 1


def test_repair_does_not_promote_zero_row_retry_output_as_success(monkeypatch, tmp_path) -> None:
    module = _load_module()
    plan_path, summary_path = _write_plan_and_summary(tmp_path)
    repair_summary = tmp_path / "repair-summary.json"

    def fake_run(command, **kwargs):
        output_path = Path(command[command.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps([]), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--plan",
            str(plan_path),
            "--execution-summary",
            str(summary_path),
            "--company-name",
            "Coveo",
            "--category",
            "no_markdown",
            "--repair-output-dir",
            str(tmp_path / "repairs"),
            "--summary-output",
            str(repair_summary),
            "--repair-timeout-seconds",
            "240",
            "--command-timeout-seconds",
            "260",
        ]
    )

    payload = json.loads(repair_summary.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["status"] == "failed"
    assert payload["selected"] == 1
    assert payload["succeeded"] == 0
    assert payload["empty"] == 1
    assert payload["failed"] == 0
    assert payload["scout_paths"] == []
    assert payload["results"][0]["status"] == "empty"
    assert payload["results"][0]["row_count"] == 0
    assert payload["results"][0]["error"] == "repair retry produced no product rows"
