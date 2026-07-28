"""Tests for Phase 8 named-team recommendation work artifact export."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_pilot_recommendation_work_artifact.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_pilot_recommendation_work_artifact", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _review_packet() -> dict:
    return {
        "phase": "phase5_argus_intelligence",
        "gate_status": "awaiting_human_acceptance",
        "recommendation": {
            "recommendation_id": 2,
            "owner": "PMM",
            "urgency": "this_week",
            "confidence": 0.68,
            "action": "Turn Agent Studio into an evidence-backed market narrative before the demand window cools.",
            "top_insight": (
                "Product reality and audience demand align, but the captured conversation does not yet explain "
                "the capability."
            ),
            "scorecard": {
                "summary": "Own product proof and audience demand align while the market narrative is missing.",
                "verdict": "actionable",
                "total_score": 66,
            },
        },
        "evidence_summary": {
            "recommendation_count": 1,
            "pattern_count": 4,
            "demand_signal_count": 101,
            "evidence_urls": [
                "https://www.algolia.com/products/ai-search/",
                "https://datastudio.google.com/",
                "file:///tmp/private.csv",
            ],
        },
        "demand_topics": [
            {
                "topic": "Agent Studio",
                "value": 1619,
                "metric": "sessions",
                "change_pct": 1.1558,
                "scorecard_dimensions": ["audience_demand", "evidence_breadth"],
                "linked_evidence_urls": ["/opt/cios/private.json", "https://www.algolia.com/products/ai-search/"],
            }
        ],
        "confidence_limits": [
            "No material news was promoted today.",
            "One or more historical demand windows has limited tenant-side evidence.",
        ],
    }


def test_builds_pmm_work_artifact_without_phase8_exit_evidence() -> None:
    module = _load_module()

    artifact = module.build_work_artifact(_review_packet(), generated_by="codex")

    assert artifact["phase"] == "phase8_controlled_pilot"
    assert artifact["artifact_type"] == "named_team_recommendation_work_artifact"
    assert artifact["named_team"] == "Product Marketing"
    assert artifact["status"] == "draft_for_named_team_review"
    assert artifact["phase8_exit_evidence"] is False
    assert artifact["recommendation"]["recommendation_id"] == 2
    assert artifact["work_product"]["title"] == "Agent Studio PMM Narrative Brief"
    assert "Agent Studio" in artifact["work_product"]["positioning_thesis"]
    assert artifact["work_product"]["brief_sections"]["audience_demand_signal"].startswith("Agent Studio")
    assert artifact["work_product"]["recommended_next_moves"][0].startswith("Draft a sourced PMM narrative")
    assert artifact["next_required_action"].startswith("Product Marketing must use, reject, or amend")
    assert "file:///tmp/private.csv" not in json.dumps(artifact)
    assert "/opt/cios/private.json" not in json.dumps(artifact)


def test_export_writes_json_and_markdown(tmp_path) -> None:
    module = _load_module()
    review_packet = tmp_path / "review-packet.json"
    json_output = tmp_path / "work-artifact.json"
    markdown_output = tmp_path / "work-artifact.md"
    review_packet.write_text(json.dumps(_review_packet()), encoding="utf-8")

    payload = module.export_work_artifact(
        review_packet,
        output=json_output,
        markdown_output=markdown_output,
        generated_by="codex",
    )

    saved = json.loads(json_output.read_text(encoding="utf-8"))
    markdown = markdown_output.read_text(encoding="utf-8")
    assert saved == payload
    assert "Agent Studio PMM Narrative Brief" in markdown
    assert "Phase 8 exit evidence: `false`" in markdown
    assert "Product Marketing must use, reject, or amend" in markdown


def test_requires_current_recommendation_id() -> None:
    module = _load_module()
    packet = _review_packet()
    packet["recommendation"]["recommendation_id"] = None

    try:
        module.build_work_artifact(packet, generated_by="codex")
    except ValueError as exc:
        assert "recommendation_id is required" in str(exc)
    else:
        raise AssertionError("expected recommendation id validation failure")
