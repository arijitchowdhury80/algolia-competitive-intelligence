"""Contract tests for the Phase 8 named-team disposition request."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_phase8_disposition_request.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_phase8_disposition_request", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _work_artifact() -> dict:
    return {
        "phase": "phase8_controlled_pilot",
        "artifact_type": "named_team_recommendation_work_artifact",
        "status": "draft_for_named_team_review",
        "phase8_exit_evidence": False,
        "named_team": "Product Marketing",
        "recommendation": {
            "recommendation_id": 2,
            "owner": "PMM",
            "urgency": "this_week",
            "confidence": 0.68,
            "action": "Turn Agent Studio into an evidence-backed market narrative.",
        },
        "work_product": {"title": "Agent Studio PMM Narrative Brief"},
    }


def test_builds_non_exit_disposition_request_with_decision_options() -> None:
    module = _load_module()

    payload = module.build_disposition_request(
        _work_artifact(),
        work_artifact_url="https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md",
        manifest_url="https://ci.chowmes.com/data/phase8/argus-phase8-work-artifacts.json",
        generated_at="2026-07-28T20:00:00Z",
    )

    assert payload["artifact_type"] == "named_team_disposition_request"
    assert payload["phase8_exit_evidence"] is False
    assert payload["status"] == "awaiting_named_team_disposition"
    assert payload["recommendation_id"] == 2
    assert payload["work_artifact"]["public_url"].endswith("argus-pmm-narrative-brief.md")
    assert [item["decision"] for item in payload["decision_required"]["options"]] == [
        "used",
        "rejected",
        "amended",
    ]
    assert payload["decision_required"]["options"][0]["requires_learning_proof"] is False
    assert payload["decision_required"]["options"][1]["requires_learning_proof"] is True
    assert "--decision used" in payload["sample_record_command"]
    assert "--work-artifact-url https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md" in payload[
        "sample_record_command"
    ]


def test_rejects_private_or_non_public_work_artifact_url() -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="work_artifact_url must be a public"):
        module.build_disposition_request(
            _work_artifact(),
            work_artifact_url="/opt/cios/app/out/phase8/argus-pmm-narrative-brief.md",
            manifest_url="https://ci.chowmes.com/data/phase8/argus-phase8-work-artifacts.json",
        )


def test_rejects_absolute_review_packet_path() -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="review_packet_path must be a relative"):
        module.build_disposition_request(
            _work_artifact(),
            work_artifact_url="https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md",
            manifest_url="https://ci.chowmes.com/data/phase8/argus-phase8-work-artifacts.json",
            review_packet_path="/opt/cios/app/out/phase8/argus-recommendation-review-packet.json",
        )


def test_rejects_exit_evidence_as_source_artifact() -> None:
    module = _load_module()
    artifact = _work_artifact()
    artifact["phase8_exit_evidence"] = True

    with pytest.raises(ValueError, match="non-exit work artifacts"):
        module.build_disposition_request(
            artifact,
            work_artifact_url="https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md",
            manifest_url="https://ci.chowmes.com/data/phase8/argus-phase8-work-artifacts.json",
        )


def test_cli_writes_json_and_markdown(tmp_path) -> None:
    module = _load_module()
    source = tmp_path / "work-artifact.json"
    output = tmp_path / "request.json"
    markdown = tmp_path / "request.md"
    source.write_text(json.dumps(_work_artifact()), encoding="utf-8")

    rc = module.main(
        [
            "--work-artifact",
            str(source),
            "--work-artifact-url",
            "https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md",
            "--manifest-url",
            "https://ci.chowmes.com/data/phase8/argus-phase8-work-artifacts.json",
            "--output",
            str(output),
            "--markdown-output",
            str(markdown),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["artifact_type"] == "named_team_disposition_request"
    assert "Phase 8 PMM Disposition Request" in markdown.read_text(encoding="utf-8")
