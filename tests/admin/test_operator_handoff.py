"""Tests for reading the Hermes-produced Argus operator handoff artifact."""

from __future__ import annotations

import json

from cios.admin.operator_handoff import ArgusOperatorHandoffStore


def test_operator_handoff_store_reads_tenant_artifact_from_output_dir(tmp_path) -> None:
    artifact = tmp_path / "argus-operator-handoff.json"
    artifact.write_text(
        json.dumps(
            {
                "tenant_slug": "algolia",
                "tenant_id": 1,
                "generated_at": "2026-07-11T20:02:00Z",
                "status": "blocked_on_evidence",
                "argus_readiness": "not_actionable",
                "summary": "Argus is blocked by 1 evidence gap before it can promote this run to action.",
                "next_operator_action": "Upload GA4 / Looker demand export for the current and previous periods.",
                "top_blocker": {"work_item_id": "argus-evidence:88:demand", "evidence_plane": "demand"},
                "primary_command": {
                    "label": "Download demand template",
                    "href": "/api/tenants/algolia/argus/demand-imports/template",
                    "method": "get",
                },
                "secondary_command": None,
                "operator_brief": ["Argus withheld action because the demand plane is missing."],
                "artifact_refs": {"work_queue": "/tmp/work-queue.json", "dashboard": "/tmp/dashboard.json"},
                "work_queue": {"work_item_count": 1, "blocking_count": 1, "limiting_count": 0},
            }
        ),
        encoding="utf-8",
    )

    status = ArgusOperatorHandoffStore(out_dir=tmp_path).status("algolia")

    assert status.tenant_slug == "algolia"
    assert status.status == "blocked_on_evidence"
    assert status.argus_readiness == "not_actionable"
    assert status.top_blocker["work_item_id"] == "argus-evidence:88:demand"
    assert status.artifact_found is True
    assert status.artifact_path == str(artifact)


def test_operator_handoff_store_returns_not_recorded_when_artifact_missing(tmp_path) -> None:
    status = ArgusOperatorHandoffStore(out_dir=tmp_path).status("algolia")

    assert status.tenant_slug == "algolia"
    assert status.status == "not_recorded"
    assert status.argus_readiness == "unknown"
    assert status.artifact_found is False
    assert status.artifact_path == str(tmp_path / "argus-operator-handoff.json")
    assert status.next_operator_action == "Run the Hermes daily sweep or rebuild the Argus operator handoff."
    assert status.primary_command.label == "Open Argus run console"
