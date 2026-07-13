"""Tests for first-run product-surface extraction control."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cios.admin.product_surface_extraction import ProductSurfaceExtractionControl


def test_product_surface_extraction_control_plans_executes_and_returns_scout_paths(
    monkeypatch,
    tmp_path,
) -> None:
    app_dir = tmp_path / "app"
    scripts = app_dir / "scripts"
    scripts.mkdir(parents=True)
    work_root = tmp_path / "work"
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        if "plan_product_surface_exports.py" in command[1]:
            plan_path = Path(command[command.index("--plan-output") + 1])
            output_dir = Path(command[command.index("--output-dir") + 1])
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "000044-klevu-docs.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "target_count": 1,
                        "items": [
                            {
                                "target": {
                                    "company_id": 9,
                                    "company_name": "Klevu",
                                    "company_role": "competitor",
                                    "surface_family": "docs",
                                    "surface_id": 44,
                                },
                                "output_path": str(output_path),
                                "command": [sys.executable, "export_product_surface_with_scout.py"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if "execute_product_surface_plan.py" in command[1]:
            summary_path = Path(command[command.index("--summary-output") + 1])
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "planned": 1,
                        "succeeded": 1,
                        "empty": 0,
                        "failed": 0,
                        "product_plane_status": "ready",
                        "product_row_count": 2,
                        "scout_paths": [
                            str(work_root / "algolia" / "surface-exports" / "000044-klevu-docs.json")
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("cios.admin.product_surface_extraction.subprocess.run", fake_run)
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_PROVIDER", "gemini/gemini-2.5-flash")

    result = ProductSurfaceExtractionControl(
        app_dir=app_dir,
        work_root=work_root,
        python_bin=sys.executable,
    ).run(
        tenant_slug="algolia",
        tenant_id=1,
        company_name="Klevu",
        focus_capability="Channel Assistant",
        timeout_seconds=160,
        command_timeout_seconds=220,
        max_workers=2,
        limit=1,
    )

    assert result["status"] == "ready"
    assert result["succeeded"] == 1
    assert result["product_row_count"] == 2
    assert result["scout_paths"] == [
        str(work_root / "algolia" / "surface-exports" / "000044-klevu-docs.json")
    ]
    plan_command = commands[0]
    assert plan_command[plan_command.index("--company-name") + 1] == "Klevu"
    assert plan_command[plan_command.index("--focus-capability") + 1] == "Channel Assistant"
    assert plan_command[plan_command.index("--limit") + 1] == "1"
    assert plan_command[plan_command.index("--provider") + 1] == "gemini/gemini-2.5-flash"
    assert plan_command[plan_command.index("--scout-bin") + 1] == str(scripts / "scout_http_shim")
    execute_command = commands[1]
    assert execute_command[execute_command.index("--command-timeout-seconds") + 1] == "220"
    assert execute_command[execute_command.index("--max-workers") + 1] == "2"
