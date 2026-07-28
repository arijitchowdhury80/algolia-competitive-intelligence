"""Contract tests for Phase 8 pilot recommendation disposition evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "record_pilot_recommendation_disposition.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("record_pilot_recommendation_disposition", SCRIPT_PATH)
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
            "trace_status": "current_open_recommendation",
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
        "confidence_limits": ["Demand plan coverage is partial."],
    }


def test_pending_disposition_is_a_handoff_not_phase8_exit() -> None:
    module = _load_module()

    payload = module.build_disposition(
        review_packet=_review_packet(),
        decision="pending",
        named_team="Product Marketing",
        decided_by="arijit",
        use_case="",
        reason="Awaiting PMM use or rejection.",
        generated_at="2026-07-28T15:00:00Z",
    )

    assert payload["phase"] == "phase8_controlled_pilot"
    assert payload["decision"] == "pending"
    assert payload["phase8_exit_evidence"] is False
    assert payload["next_required_action"].startswith("Record a named-team use")
    assert payload["recommendation"]["recommendation_id"] == 2


def test_used_disposition_requires_named_team_and_concrete_use() -> None:
    module = _load_module()

    payload = module.build_disposition(
        review_packet=_review_packet(),
        decision="used",
        named_team="Product Marketing",
        decided_by="arijit",
        use_case="Draft PMM narrative brief for Agent Studio launch-defense messaging.",
        reason="The read connects shipped proof to rising demand and a clear narrative gap.",
        work_artifact_url="https://ci.chowmes.com/data/argus-latest-run-status.json",
        generated_at="2026-07-28T15:05:00Z",
    )

    assert payload["decision"] == "used"
    assert payload["phase8_exit_evidence"] is True
    assert payload["recommendation_status_to_set"] == "done"
    assert payload["learning_required"] is False
    assert payload["disposition"]["named_team"] == "Product Marketing"
    assert payload["disposition"]["use_case"].startswith("Draft PMM narrative")
    assert payload["evidence_summary"]["evidence_urls"] == [
        "https://www.algolia.com/products/ai-search/",
        "https://datastudio.google.com/",
    ]
    assert "/tmp/private.csv" not in json.dumps(payload)


def test_rejected_or_amended_disposition_requires_learning_proof_ids() -> None:
    module = _load_module()

    rejected = module.build_disposition(
        review_packet=_review_packet(),
        decision="rejected",
        named_team="Product Marketing",
        decided_by="arijit",
        use_case="Rejected for PMM planning.",
        reason="The demand comparison is too narrow for GTM use.",
        learning_event_id=11,
        improvement_id=12,
        generated_at="2026-07-28T15:10:00Z",
    )

    assert rejected["phase8_exit_evidence"] is True
    assert rejected["recommendation_status_to_set"] == "dismissed"
    assert rejected["learning_required"] is True
    assert rejected["learning_proof"] == {"learning_event_id": 11, "improvement_id": 12}


def test_rejected_or_amended_without_learning_ids_is_not_exit_evidence() -> None:
    module = _load_module()

    amended = module.build_disposition(
        review_packet=_review_packet(),
        decision="amended",
        named_team="Product Marketing",
        decided_by="arijit",
        use_case="Use only after the narrative gap is narrowed to launch pages.",
        reason="The recommendation is directionally right, but owner language should be sharper.",
        generated_at="2026-07-28T15:15:00Z",
    )

    assert amended["phase8_exit_evidence"] is False
    assert amended["learning_required"] is True
    assert amended["next_required_action"].startswith("Record the amendment")


def test_cli_writes_json_and_markdown(tmp_path) -> None:
    module = _load_module()
    review = tmp_path / "review.json"
    output = tmp_path / "disposition.json"
    markdown = tmp_path / "disposition.md"
    review.write_text(json.dumps(_review_packet()), encoding="utf-8")

    rc = module.main(
        [
            "--review-packet",
            str(review),
            "--decision",
            "pending",
            "--named-team",
            "Product Marketing",
            "--decided-by",
            "arijit",
            "--reason",
            "Awaiting pilot-window disposition.",
            "--output",
            str(output),
            "--markdown-output",
            str(markdown),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["decision"] == "pending"
    assert "Phase 8 Pilot Recommendation Disposition" in markdown.read_text(encoding="utf-8")
