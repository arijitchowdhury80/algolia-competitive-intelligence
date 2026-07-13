"""Tests for the Hermes-facing Argus demand plan CSV exporter."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_argus_demand_plan_template.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_argus_demand_plan_template", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_argus_demand_plan_template_writes_csv_from_readiness_payload(tmp_path) -> None:
    module = _load_module()
    readiness = tmp_path / "argus-demand-readiness.json"
    output = tmp_path / "argus-demand-plan-template.csv"
    readiness.write_text(
        json.dumps(
            {
                "status": "blocked_missing_demand_source",
                "demand_collection_plan": {
                    "status": "needs_demand_source",
                    "topic_count": 2,
                    "topics": [
                        {
                            "topic": "AI Assistant",
                            "capability_key": "ai assistant",
                            "assessment": "competitive_pressure",
                            "suggested_filter_terms": ["AI Assistant", "assistant"],
                            "related_competitors": ["Constructor", "Doofinder"],
                            "why_collect": "Collect tenant demand before promoting the AI Assistant read.",
                            "evidence_urls": [
                                "https://constructor.com/changelog/ai-assistant",
                                "https://doofinder.com/ai-search",
                            ],
                        },
                        {
                            "topic": "Shopping Assistant",
                            "capability_key": "shopping assistant",
                            "assessment": "watch",
                            "suggested_filter_terms": ["Shopping Assistant"],
                            "related_competitors": ["Bloomreach"],
                            "evidence_urls": ["https://constructor.com/blog/shopping-assistant"],
                        },
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    code = module.main(["--readiness", str(readiness), "--output", str(output)])

    rows = list(csv.DictReader(output.read_text(encoding="utf-8").splitlines()))
    assert code == 0
    assert rows[0]["Argus topic"] == "AI Assistant"
    assert rows[0]["Capability key"] == "ai assistant"
    assert rows[0]["Assessment"] == "competitive_pressure"
    assert rows[0]["Suggested filters"] == "AI Assistant | assistant"
    assert rows[0]["Related competitors"] == "Constructor | Doofinder"
    assert rows[0]["Why collect"] == "Collect tenant demand before promoting the AI Assistant read."
    assert rows[0]["Evidence URLs"] == (
        "https://constructor.com/changelog/ai-assistant | https://doofinder.com/ai-search"
    )
    assert rows[1]["Argus topic"] == "Shopping Assistant"


def test_export_argus_demand_plan_template_writes_operator_guide_json(tmp_path) -> None:
    module = _load_module()
    readiness = tmp_path / "argus-demand-readiness.json"
    output = tmp_path / "argus-demand-plan-template.csv"
    guide_output = tmp_path / "argus-demand-work-order-guide.json"
    readiness.write_text(
        json.dumps(
            {
                "status": "blocked_missing_demand_source",
                "demand_collection_plan": {
                    "status": "needs_demand_source",
                    "topic_count": 1,
                    "topics": [
                        {
                            "topic": "AI Assistant",
                            "capability_key": "ai assistant",
                            "assessment": "competitive_pressure",
                            "suggested_filter_terms": ["AI Assistant", "assistant"],
                            "related_competitors": ["Constructor"],
                            "why_collect": "Internal rationale should not ship in public guide.",
                            "evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    code = module.main(
        [
            "--readiness",
            str(readiness),
            "--output",
            str(output),
            "--guide-output",
            str(guide_output),
            "--tenant",
            "algolia",
        ]
    )

    guide = json.loads(guide_output.read_text(encoding="utf-8"))
    assert code == 0
    assert guide["status"] == "ready"
    assert guide["tenant_slug"] == "algolia"
    assert guide["template_filename"] == "argus-demand-plan-template.csv"
    assert guide["template_href"] == "/api/tenants/algolia/argus/demand-imports/template?planned=1"
    assert guide["topic_count"] == 1
    assert guide["topics"][0]["topic"] == "AI Assistant"
    assert guide["topics"][0]["filter_terms"] == ["AI Assistant", "assistant", "ai assistant"]
    assert guide["topics"][0]["row_status"] == "needs_metrics"
    assert "Internal rationale" not in json.dumps(guide)


def test_export_argus_demand_plan_template_writes_header_for_missing_plan(tmp_path) -> None:
    module = _load_module()
    readiness = tmp_path / "argus-demand-readiness.json"
    output = tmp_path / "argus-demand-plan-template.csv"
    readiness.write_text('{"status":"blocked_missing_demand_source"}', encoding="utf-8")

    code = module.main(["--readiness", str(readiness), "--output", str(output)])

    lines = output.read_text(encoding="utf-8").splitlines()
    assert code == 0
    assert len(lines) == 1
    assert lines[0].startswith("Page title,Page path,Engaged sessions")
