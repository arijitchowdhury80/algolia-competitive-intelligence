"""Tests for publishing Phase 8 recommendation work artifacts safely."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "publish_pilot_recommendation_work_artifact.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("publish_pilot_recommendation_work_artifact", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _artifact() -> dict:
    return {
        "phase": "phase8_controlled_pilot",
        "artifact_type": "named_team_recommendation_work_artifact",
        "named_team": "Product Marketing",
        "status": "draft_for_named_team_review",
        "phase8_exit_evidence": False,
        "recommendation": {
            "recommendation_id": 2,
            "owner": "PMM",
            "action": "Turn Agent Studio into an evidence-backed market narrative.",
        },
        "work_product": {
            "title": "Agent Studio PMM Narrative Brief",
        },
        "next_required_action": "Product Marketing must use, reject, or amend this artifact.",
    }


def test_publish_work_artifact_writes_public_copies_and_manifest(tmp_path) -> None:
    module = _load_module()
    artifact_json = tmp_path / "argus-pmm-narrative-brief.json"
    artifact_md = tmp_path / "argus-pmm-narrative-brief.md"
    public_dir = tmp_path / "public"
    output = tmp_path / "publish-summary.json"
    artifact_json.write_text(json.dumps(_artifact()), encoding="utf-8")
    artifact_md.write_text("# Agent Studio PMM Narrative Brief\n\nPublic-safe draft.\n", encoding="utf-8")

    summary = module.publish_work_artifact(
        artifact_json=artifact_json,
        artifact_markdown=artifact_md,
        public_dir=public_dir,
        base_url="https://ci.chowmes.com",
        output=output,
    )

    assert summary["status"] == "published"
    assert summary["phase8_exit_evidence"] is False
    assert summary["public_urls"]["json"] == "https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.json"
    assert summary["public_urls"]["markdown"] == "https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md"
    assert (public_dir / "data" / "phase8" / "argus-pmm-narrative-brief.json").is_file()
    assert (public_dir / "data" / "phase8" / "argus-pmm-narrative-brief.md").is_file()
    assert (public_dir / "v2" / "data" / "phase8" / "argus-pmm-narrative-brief.json").is_file()
    assert (public_dir / "v2" / "data" / "phase8" / "argus-phase8-work-artifacts.json").is_file()
    manifest = json.loads(
        (public_dir / "data" / "phase8" / "argus-phase8-work-artifacts.json").read_text(encoding="utf-8")
    )
    assert manifest["items"][0]["recommendation_id"] == 2
    assert manifest["items"][0]["phase8_exit_evidence"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == summary


def test_publish_rejects_private_paths(tmp_path) -> None:
    module = _load_module()
    artifact_json = tmp_path / "argus-pmm-narrative-brief.json"
    artifact_md = tmp_path / "argus-pmm-narrative-brief.md"
    artifact = _artifact()
    artifact["internal_path"] = "/opt/cios/app/out/phase8/private.json"
    artifact_json.write_text(json.dumps(artifact), encoding="utf-8")
    artifact_md.write_text("# Brief\n", encoding="utf-8")

    try:
        module.publish_work_artifact(
            artifact_json=artifact_json,
            artifact_markdown=artifact_md,
            public_dir=tmp_path / "public",
            base_url="https://ci.chowmes.com",
            output=None,
        )
    except ValueError as exc:
        assert "private_path" in str(exc)
    else:
        raise AssertionError("expected private-path validation failure")


def test_publish_requires_draft_non_exit_artifact(tmp_path) -> None:
    module = _load_module()
    artifact_json = tmp_path / "argus-pmm-narrative-brief.json"
    artifact_md = tmp_path / "argus-pmm-narrative-brief.md"
    artifact = _artifact()
    artifact["phase8_exit_evidence"] = True
    artifact_json.write_text(json.dumps(artifact), encoding="utf-8")
    artifact_md.write_text("# Brief\n", encoding="utf-8")

    try:
        module.publish_work_artifact(
            artifact_json=artifact_json,
            artifact_markdown=artifact_md,
            public_dir=tmp_path / "public",
            base_url="https://ci.chowmes.com",
            output=None,
        )
    except ValueError as exc:
        assert "must not be Phase 8 exit evidence" in str(exc)
    else:
        raise AssertionError("expected exit-evidence validation failure")
