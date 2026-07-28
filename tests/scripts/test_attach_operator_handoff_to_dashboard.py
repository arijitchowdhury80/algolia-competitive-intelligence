from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "attach_operator_handoff_to_dashboard.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("attach_operator_handoff_to_dashboard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dashboard_payload() -> dict:
    return {
        "schema_version": 17,
        "tenant_id": 1,
        "cadence": "daily",
        "generated_at": "2026-07-11T20:00:00Z",
        "intelligence_spine": {
            "verdict": "watch",
            "top_insight": "Constructor moved first, but demand proof is missing.",
            "can_recommend": False,
            "next_operator_action": "Upload GA4 / Looker demand export for the current and previous periods.",
        },
    }


def _handoff_payload() -> dict:
    return {
        "tenant_slug": "algolia",
        "tenant_id": 1,
        "generated_at": "2026-07-11T20:02:00Z",
        "status": "blocked_on_evidence",
        "argus_readiness": "not_actionable",
        "summary": "Argus is blocked by 1 evidence gap before it can promote this run to action.",
        "next_operator_action": "Upload GA4 / Looker demand export for the current and previous periods.",
        "top_blocker": {
            "work_item_id": "argus-evidence:17:demand",
            "evidence_plane": "demand",
            "severity": "blocks_action",
            "title": "Demand plane missing",
            "why_needed": "Demand evidence is missing, so Argus withheld owner recommendations.",
            "blocks": ["owner recommendations", "priority ranking"],
        },
        "primary_command": {
            "label": "Download demand template",
            "href": "/api/tenants/algolia/argus/demand-imports/template",
            "method": "get",
            "surface": "Demand imports",
        },
        "operator_brief": [
            "Argus withheld action because Demand plane missing is open on the demand plane.",
            "Next step: Upload GA4 / Looker demand export for the current and previous periods.",
        ],
        "demand_collection_plan": {
            "status": "needs_demand_source",
            "topic_count": 1,
            "topics": [
                {
                    "topic": "Shopping Assistant",
                    "related_competitors": ["Constructor"],
                    "evidence_url_count": 3,
                }
            ],
        },
        "demand_plan_template": {
            "status": "generated",
            "format": "csv",
            "filename": "argus-demand-plan-template.csv",
        },
        "demand_plan_amendments": {
            "status": "suggested",
            "candidate_count": 1,
            "candidates": [
                {
                    "topic": "Agent Studio",
                    "capability_key": "agent studio",
                    "current_sessions": "1619",
                    "previous_sessions": "751",
                    "change_pct": "1.1558",
                    "comparison_quality": "comparable_limited",
                }
            ],
        },
        "work_queue": {
            "work_item_count": 1,
            "blocking_count": 1,
            "limiting_count": 0,
            "item_ids": ["argus-evidence:17:demand"],
        },
    }


def test_attach_operator_handoff_payload_adds_public_dashboard_contract() -> None:
    module = _load_module()

    payload = module.attach_operator_handoff_payload(
        dashboard=_dashboard_payload(),
        handoff=_handoff_payload(),
        artifact_path="/tmp/cios/algolia/argus-operator-handoff.json",
    )

    assert payload["operator_handoff"]["status"] == "blocked_on_evidence"
    assert payload["operator_handoff"]["argus_readiness"] == "not_actionable"
    assert payload["operator_handoff"]["summary"].startswith("Argus is blocked")
    assert payload["operator_handoff"]["top_blocker"]["work_item_id"] == "argus-evidence:17:demand"
    assert payload["operator_handoff"]["primary_command"]["label"] == "Download demand template"
    assert payload["operator_handoff"]["demand_collection_plan"] == {
        "status": "needs_demand_source",
        "topic_count": 1,
        "topics": [
            {
                "topic": "Shopping Assistant",
                "related_competitors": ["Constructor"],
                "evidence_url_count": 3,
            }
        ],
    }
    assert payload["operator_handoff"]["demand_plan_template"] == {
        "status": "generated",
        "format": "csv",
        "filename": "argus-demand-plan-template.csv",
    }
    assert payload["operator_handoff"]["demand_plan_amendments"]["candidates"][0]["topic"] == "Agent Studio"
    assert payload["operator_handoff"]["artifact_found"] is True
    assert payload["operator_handoff"]["artifact_path"] == "/tmp/cios/algolia/argus-operator-handoff.json"


def test_attach_operator_handoff_syncs_blocking_handoff_into_intelligence_spine() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["intelligence_spine"]["next_operator_action"] = (
        "Add or repair outward conversation sources: blogs, campaigns, news, case studies, "
        "executive speech, and social surfaces."
    )
    dashboard["intelligence_spine"]["blocked_actions"] = ["confidence"]

    payload = module.attach_operator_handoff_payload(
        dashboard=dashboard,
        handoff=_handoff_payload(),
        artifact_path="/tmp/cios/algolia/argus-operator-handoff.json",
    )

    spine = payload["intelligence_spine"]
    assert spine["next_operator_action"] == "Upload GA4 / Looker demand export for the current and previous periods."
    assert spine["can_recommend"] is False
    assert spine["blocked_actions"] == ["confidence", "owner recommendations", "priority ranking"]
    assert spine["confidence_limits"] == [
        "Argus is blocked by 1 evidence gap before it can promote this run to action."
    ]


def test_attach_operator_handoff_rejects_mismatched_tenant_id() -> None:
    module = _load_module()
    handoff = _handoff_payload()
    handoff["tenant_id"] = 999

    try:
        module.attach_operator_handoff_payload(
            dashboard=_dashboard_payload(),
            handoff=handoff,
            artifact_path="/tmp/cios/algolia/argus-operator-handoff.json",
        )
    except ValueError as exc:
        assert "operator handoff tenant_id 999 does not match dashboard tenant_id 1" in str(exc)
    else:
        raise AssertionError("expected mismatched tenant_id to fail")


def test_attach_operator_handoff_cli_updates_json_and_renders_html(tmp_path) -> None:
    dashboard = tmp_path / "argus-dashboard.json"
    handoff = tmp_path / "argus-operator-handoff.json"
    html = tmp_path / "argus-dashboard.html"
    dashboard.write_text(json.dumps(_dashboard_payload()), encoding="utf-8")
    handoff.write_text(json.dumps(_handoff_payload()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dashboard",
            str(dashboard),
            "--handoff",
            str(handoff),
            "--html",
            str(html),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(dashboard.read_text(encoding="utf-8"))
    assert payload["operator_handoff"]["status"] == "blocked_on_evidence"
    assert payload["operator_handoff"]["argus_readiness"] == "not_actionable"
    rendered = html.read_text(encoding="utf-8")
    assert "Argus operator handoff" in rendered
    assert "Demand plane missing" in rendered
    assert "Suggested demand-plan amendment" in rendered
    assert "Agent Studio" in rendered
    assert "/api/tenants/algolia/argus/demand-imports/template" not in rendered
