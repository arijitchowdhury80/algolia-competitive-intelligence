"""Tests for explicit Argus demand-plan amendments."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "amend_argus_demand_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("amend_argus_demand_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_amend_argus_demand_plan_appends_accepted_candidate_and_template(tmp_path) -> None:
    module = _load_module()
    readiness = tmp_path / "argus-demand-readiness.json"
    amendments = tmp_path / "argus-demand-plan-amendment-candidates.csv"
    output = tmp_path / "argus-demand-readiness-amended.json"
    template = tmp_path / "argus-demand-plan-template-amended.csv"
    readiness.write_text(
        json.dumps(
            {
                "status": "processed_no_action_grade_demand",
                "demand_collection_plan": {
                    "status": "ready_to_collect",
                    "topic_count": 1,
                    "topics": [
                        {
                            "topic": "Commerce Studio",
                            "capability_key": "commerce studio",
                            "assessment": "watch",
                            "suggested_filter_terms": ["Commerce Studio"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    amendments.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n"
        ",,250,10,2026-07-07T00:00:00+00:00,2026-07-13T23:59:59+00:00,https://datastudio.google.com/,Agent Studio,agent studio,demand_plan_amendment,Agent Studio | agentic ai,,Collect Agent Studio,https://algolia.com/products/ai/agent-studio\n",
        encoding="utf-8",
    )

    code = module.main(
        [
            "--readiness",
            str(readiness),
            "--amendments",
            str(amendments),
            "--output",
            str(output),
            "--template-output",
            str(template),
            "--accepted-by",
            "codex",
            "--reason",
            "Validated off-plan demand should be tracked.",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(template.read_text(encoding="utf-8").splitlines()))
    plan = payload["demand_collection_plan"]
    assert code == 0
    assert payload["status"] == "manual_plan_amended"
    assert payload["next_hermes_action"] == "import_amended_planned_demand"
    assert plan["topic_count"] == 2
    assert plan["topics"][1]["topic"] == "Agent Studio"
    assert plan["topics"][1]["suggested_filter_terms"] == ["Agent Studio", "agentic ai"]
    assert plan["amendment_policy"]["accepted_by"] == "codex"
    assert plan["amendment_policy"]["added_topic_count"] == 1
    assert rows[1]["Argus topic"] == "Agent Studio"
    assert rows[1]["Capability key"] == "agent studio"


def test_amend_argus_demand_plan_skips_existing_candidate(tmp_path) -> None:
    module = _load_module()
    readiness = {
        "demand_collection_plan": {
            "topics": [{"topic": "Agent Studio", "capability_key": "agent studio"}],
        }
    }
    rows = [{"Argus topic": "Agent Studio", "Capability key": "agent studio"}]

    payload = module.amend_readiness(readiness, rows, accepted_by="codex", reason="Already tracked.")

    plan = payload["demand_collection_plan"]
    assert plan["topic_count"] == 1
    assert plan["amendment_policy"]["status"] == "no_new_topics"
    assert plan["amendment_policy"]["skipped_topics"] == [
        {"topic": "Agent Studio", "reason": "already_planned"}
    ]
