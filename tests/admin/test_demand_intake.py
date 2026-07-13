from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from cios.admin.demand_intake import DemandIntakeControl, DemandIntakeHistoryStore


def test_demand_intake_history_reads_latest_attempt(tmp_path: Path) -> None:
    run_root = tmp_path / "algolia" / "demand-intake-runs"
    latest = run_root / "20260712T091500Z"
    older = run_root / "20260712T090000Z"
    latest.mkdir(parents=True)
    older.mkdir(parents=True)
    latest.joinpath("demand-intake-summary.json").write_text(
        json.dumps(
            {
                "status": "demand_imported_and_argus_refreshed",
                "exit_code": 0,
                "tenant": "algolia",
                "mode": "queued_manual_export",
                "next_hermes_action": "continue_product_market_synthesis",
                "readiness": {"status": "queued_manual_exports"},
                "demand_import": {
                    "status": "refreshed",
                    "prepare": {"normalized_row_count": 3, "ready_count": 1},
                    "demand_ledger": {"demand_signal_count": 3},
                    "argus_read": {"top_insight": "Demand now backs the product read."},
                },
            }
        ),
        encoding="utf-8",
    )
    older.joinpath("demand-intake-summary.json").write_text(
        json.dumps(
            {
                "status": "blocked_missing_demand_source",
                "exit_code": 2,
                "tenant": "algolia",
                "mode": "blocked",
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "readiness": {"status": "blocked_missing_demand_source"},
                "demand_import": None,
            }
        ),
        encoding="utf-8",
    )

    status = DemandIntakeHistoryStore(work_root=tmp_path).status("algolia", limit=5)

    assert status["attempt_count"] == 2
    assert status["latest"]["status"] == "demand_imported_and_argus_refreshed"
    assert status["latest"]["mode"] == "queued_manual_export"
    assert status["latest"]["normalized_row_count"] == 3
    assert status["latest"]["demand_signal_count"] == 3
    assert status["latest"]["argus_top_insight"] == "Demand now backs the product read."
    assert status["attempts"][1]["status"] == "blocked_missing_demand_source"


def test_demand_intake_history_sorts_mixed_generated_at_and_run_id_formats(tmp_path: Path) -> None:
    run_root = tmp_path / "algolia" / "demand-intake-runs"
    older_compact = run_root / "20260712T084701Z"
    newer_iso = run_root / "20260712T135043Z"
    older_compact.mkdir(parents=True)
    newer_iso.mkdir(parents=True)
    older_compact.joinpath("demand-intake-summary.json").write_text(
        json.dumps(
            {
                "status": "blocked_missing_demand_source",
                "exit_code": 2,
                "tenant": "algolia",
                "mode": "blocked",
            }
        ),
        encoding="utf-8",
    )
    newer_iso.joinpath("demand-intake-summary.json").write_text(
        json.dumps(
            {
                "status": "newer_blocked_missing_demand_source",
                "exit_code": 2,
                "tenant": "algolia",
                "mode": "blocked",
                "generated_at": "2026-07-12T13:50:43.000000Z",
            }
        ),
        encoding="utf-8",
    )

    status = DemandIntakeHistoryStore(work_root=tmp_path).status("algolia", limit=5)

    assert status["latest"]["status"] == "newer_blocked_missing_demand_source"
    assert status["attempts"][0]["run_id"] == "20260712T135043Z"
    assert status["attempts"][1]["run_id"] == "20260712T084701Z"


def test_demand_intake_control_runs_script_and_returns_structured_blocked_result(
    tmp_path: Path, monkeypatch
) -> None:
    app_dir = tmp_path / "app"
    script = app_dir / "scripts" / "run_argus_demand_intake.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    work_root = tmp_path / "work"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True)
        output.write_text(
            json.dumps(
                {
                    "status": "blocked_missing_demand_source",
                    "exit_code": 2,
                    "tenant": "algolia",
                    "mode": "blocked",
                    "next_hermes_action": "configure_ga4_or_upload_demand_export",
                    "readiness": {"status": "blocked_missing_demand_source"},
                    "ga4_export": None,
                    "demand_import": None,
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=2, stdout="", stderr="")

    import cios.admin.demand_intake as demand_intake

    monkeypatch.setattr(demand_intake.subprocess, "run", fake_run)

    result = DemandIntakeControl(
        app_dir=app_dir,
        work_root=work_root,
        python_bin="/python",
    ).run(
        tenant_slug="algolia",
        tenant_id=1,
        own_company_name="Algolia",
        command_timeout_seconds=180,
    )

    assert result["status"] == "blocked_missing_demand_source"
    assert result["command_status"] == "blocked"
    assert result["returncode"] == 2
    assert result["summary_path"].endswith("demand-intake-summary.json")
    assert calls[0][:2] == ["/python", str(script)]
    assert "--tenant-id" in calls[0]
    assert calls[0][calls[0].index("--tenant-id") + 1] == "1"
    assert "--own-company-name" in calls[0]
    assert calls[0][calls[0].index("--own-company-name") + 1] == "Algolia"
