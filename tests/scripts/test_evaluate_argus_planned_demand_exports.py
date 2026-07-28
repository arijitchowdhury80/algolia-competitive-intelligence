"""Tests for planned Argus demand export evaluation."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_argus_planned_demand_exports.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_argus_planned_demand_exports", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_evaluate_argus_planned_demand_exports_passes_only_action_grade_plan_topics(tmp_path) -> None:
    module = _load_module()
    plan = tmp_path / "argus-demand-plan-template.csv"
    data_dir = tmp_path / "data"
    output = tmp_path / "report.json"
    prepared = tmp_path / "prepared.csv"
    _write_csv(
        plan,
        [
            {
                "Argus topic": "Dynamic Search Rules API",
                "Capability key": "dynamic search rules api",
                "Assessment": "competitive_pressure",
                "Suggested filters": "Dynamic Search Rules API | dynamic search rules",
                "Related competitors": "Meilisearch",
            }
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-campaign-metrics_2026-06-30_2026-07-06.csv",
        [
            {"Session manual campaign name": "sem_search_dynamic_search_rules_api", "Sessions": 100},
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-campaign-metrics_2026-07-07_2026-07-13.csv",
        [
            {"Session manual campaign name": "sem_search_dynamic_search_rules_api", "Sessions": 130},
        ],
    )

    code = module.main(["--plan", str(plan), "--data-dir", str(data_dir), "--output", str(output), "--prepared-output", str(prepared)])

    report = json.loads(output.read_text(encoding="utf-8"))
    prepared_rows = list(csv.DictReader(prepared.read_text(encoding="utf-8").splitlines()))
    assert code == 0
    assert report["status"] == "passed"
    assert report["phase4_gate_passed"] is True
    assert report["topics"][0]["status"] == "action_grade"
    assert report["topics"][0]["change_pct"] == 0.3
    assert prepared_rows[0]["topic"] == "Dynamic Search Rules API"
    assert prepared_rows[0]["change_pct"] == "0.3"


def test_evaluate_argus_planned_demand_exports_keeps_off_plan_spikes_out_of_gate(tmp_path) -> None:
    module = _load_module()
    plan = tmp_path / "argus-demand-plan-template.csv"
    data_dir = tmp_path / "data"
    _write_csv(
        plan,
        [
            {
                "Argus topic": "Commerce Studio",
                "Capability key": "commerce studio",
                "Assessment": "competitive_pressure",
                "Suggested filters": "Commerce Studio",
                "Related competitors": "Lucidworks",
            }
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-landing-page-device-sessions_2026-06-30_2026-07-06.csv",
        [
            {"Landing page": "/products/ai/agent-studio", "Device category": "desktop", "Sessions": 10},
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-landing-page-metrics_2026-07-07_2026-07-13.csv",
        [
            {"Landing page": "/products/ai/agent-studio", "Sessions": 250},
        ],
    )

    report = module.build_report(
        plan_path=plan,
        data_dir=data_dir,
        generated_at="2026-07-28T12:00:00Z",
    )

    assert report["status"] == "blocked_no_action_grade_planned_demand"
    assert report["phase4_gate_passed"] is False
    assert report["topics"][0]["status"] == "no_matching_current_rows"
    assert report["off_plan_opportunities"][0]["topic"] == "Agent Studio"
    assert report["off_plan_opportunities"][0]["status"] == "action_grade_limited"
    assert report["off_plan_opportunities"][0]["phase4_gate_evidence"] is False
    assert report["plan_amendment_candidates"][0]["topic"] == "Agent Studio"
    assert report["plan_amendment_candidates"][0]["assessment"] == "demand_plan_amendment"
    assert report["plan_amendment_candidates"][0]["current_sessions"] == 250
    assert report["plan_amendment_candidates"][0]["previous_sessions"] == 10
    assert "Amend the Argus plan only if Product or Conversation evidence" in (
        report["plan_amendment_candidates"][0]["why_collect"]
    )


def test_evaluate_argus_planned_demand_exports_ignores_looker_metadata_url_matches(tmp_path) -> None:
    module = _load_module()
    plan = tmp_path / "argus-demand-plan-template.csv"
    data_dir = tmp_path / "data"
    _write_csv(
        plan,
        [
            {
                "Argus topic": "Studio",
                "Capability key": "studio",
                "Assessment": "watch",
                "Suggested filters": "Studio",
                "Related competitors": "Lucidworks",
            }
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-demand_2026-07-07_2026-07-13.csv",
        [
            {
                "topic": "/search",
                "value": 200,
                "source_url": "https://datastudio.google.com/reporting/example",
            },
        ],
    )

    report = module.build_report(plan_path=plan, data_dir=data_dir, generated_at="2026-07-28T12:00:00Z")

    assert report["phase4_gate_passed"] is False
    assert report["topics"][0]["matched_current_row_count"] == 0


def test_evaluate_argus_planned_demand_exports_writes_amendment_candidates_csv(tmp_path) -> None:
    module = _load_module()
    plan = tmp_path / "argus-demand-plan-template.csv"
    data_dir = tmp_path / "data"
    output = tmp_path / "report.json"
    amendment = tmp_path / "amendment.csv"
    _write_csv(
        plan,
        [
            {
                "Argus topic": "Commerce Studio",
                "Capability key": "commerce studio",
                "Assessment": "watch",
                "Suggested filters": "Commerce Studio",
                "Related competitors": "Lucidworks",
            }
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-landing-page-device-sessions_2026-06-30_2026-07-06.csv",
        [
            {"Landing page": "/products/ai/agent-studio", "Device category": "desktop", "Sessions": 10},
        ],
    )
    _write_csv(
        data_dir / "algolia-looker-landing-page-metrics_2026-07-07_2026-07-13.csv",
        [
            {"Landing page": "/products/ai/agent-studio", "Sessions": 250},
        ],
    )

    code = module.main(
        [
            "--plan",
            str(plan),
            "--data-dir",
            str(data_dir),
            "--output",
            str(output),
            "--amendment-output",
            str(amendment),
        ]
    )

    rows = list(csv.DictReader(amendment.read_text(encoding="utf-8").splitlines()))
    assert code == 2
    assert rows[0]["Argus topic"] == "Agent Studio"
    assert rows[0]["Assessment"] == "demand_plan_amendment"
    assert rows[0]["Engaged sessions"] == "250"
    assert rows[0]["Engaged sessions previous period"] == "10"
    assert "agent studio" in rows[0]["Capability key"]
