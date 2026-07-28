"""Contract tests for the Phase 5 recommendation review packet exporter."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_argus_recommendation_review_packet.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_argus_recommendation_review_packet", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dashboard_payload() -> dict:
    return {
        "product_market_run": {
            "recommendation_count": 1,
            "pattern_count": 3,
            "demand_signal_count": 101,
            "intelligence_brief": {
                "top_insight": "Algolia has product proof for Agent Studio and rising audience demand.",
                "primary_action": "Turn Agent Studio into an evidence-backed market narrative.",
                "confidence_limits": [
                    "One or more historical windows has no tenant-side demand evidence.",
                ],
                "demand_recommendation_trace": {
                    "status": "linked_to_recommendations",
                    "pattern_count": 3,
                    "recommendation_count": 1,
                    "demand_signal_count": 101,
                    "rising_demand_topic_count": 1,
                    "matched_demand_topic_count": 1,
                    "evidence_urls": [
                        "https://datastudio.google.com/",
                        "file:///tmp/private.csv",
                    ],
                    "demand_topics": [
                        {
                            "topic": "Agent Studio",
                            "value": 1619,
                            "metric": "sessions",
                            "change_pct": 1.1558,
                            "source_files": ["argus-planned-demand-prepared-amended.csv"],
                            "linked_evidence_urls": [
                                "https://www.algolia.com/products/ai-search/",
                                "/opt/cios/private.json",
                            ],
                            "scorecard_dimensions": ["audience_demand", "evidence_breadth"],
                            "recommendation_actions": [
                                "Turn Agent Studio into an evidence-backed market narrative.",
                            ],
                        }
                    ],
                },
            },
        }
    }


def test_export_packet_builds_phase5_review_contract(tmp_path) -> None:
    module = _load_module()
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(json.dumps(_dashboard_payload()), encoding="utf-8")

    packet = module.build_review_packet(dashboard, reviewed_by="codex", decision="awaiting_human_acceptance")

    assert packet["phase"] == "phase5_argus_intelligence"
    assert packet["gate_status"] == "awaiting_human_acceptance"
    assert packet["recommendation"]["action"] == "Turn Agent Studio into an evidence-backed market narrative."
    assert packet["recommendation"]["top_insight"].startswith("Algolia has product proof")
    assert packet["evidence_summary"]["demand_signal_count"] == 101
    assert packet["evidence_summary"]["pattern_count"] == 3
    assert packet["demand_topics"][0]["topic"] == "Agent Studio"
    assert packet["acceptance_rubric"][0]["dimension"] == "accuracy"
    assert packet["learning_effect"]["status"] == "pending_acceptance_or_challenge"
    assert "file:///tmp/private.csv" not in json.dumps(packet)
    assert "/opt/cios/private.json" not in json.dumps(packet)


def test_export_packet_writes_json_and_markdown(tmp_path) -> None:
    module = _load_module()
    dashboard = tmp_path / "dashboard.json"
    json_output = tmp_path / "packet.json"
    markdown_output = tmp_path / "packet.md"
    dashboard.write_text(json.dumps(_dashboard_payload()), encoding="utf-8")

    payload = module.export_review_packet(
        dashboard,
        output=json_output,
        markdown_output=markdown_output,
        reviewed_by="codex",
        decision="accepted",
    )

    saved = json.loads(json_output.read_text(encoding="utf-8"))
    markdown = markdown_output.read_text(encoding="utf-8")
    assert saved == payload
    assert saved["gate_status"] == "accepted"
    assert "Phase 5 Argus Recommendation Review" in markdown
    assert "Turn Agent Studio into an evidence-backed market narrative." in markdown
    assert "Learning Effect" in markdown


def test_export_packet_falls_back_to_current_open_recommendation_when_primary_action_is_empty(tmp_path) -> None:
    module = _load_module()
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "product_market_run": {
                    "recommendation_count": 0,
                    "pattern_count": 4,
                    "demand_signal_count": 101,
                    "intelligence_brief": {
                        "top_insight": "Historical spine is stale and still says to watch.",
                        "primary_action": None,
                        "confidence_limits": ["Recommendation count was stale in the run summary."],
                    },
                },
                "argus_recommendations": [
                    {
                        "recommendation_id": 2,
                        "owner": "PMM",
                        "action": "Turn Agent Studio into an evidence-backed market narrative before the demand window cools.",
                        "why_now": "Product reality and audience demand align, but the captured conversation does not yet explain the capability.",
                        "urgency": "this_week",
                        "confidence": 0.68,
                        "status": "open",
                        "scorecard": {
                            "total_score": 66,
                            "verdict": "actionable",
                            "summary": "Own product proof and audience demand align.",
                        },
                        "evidence_refs": [
                            {
                                "source_url": "https://www.algolia.com/products/ai-search/",
                                "excerpt": "Agent Studio Create, test, and deploy AI agents, quickly.",
                            },
                            {
                                "source_url": "https://datastudio.google.com/",
                                "excerpt": "Current sessions: 1619.0; previous sessions: 751.0.",
                            },
                            {
                                "source_url": "file:///tmp/private.csv",
                                "excerpt": "This local path must not leak.",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    packet = module.build_review_packet(dashboard, reviewed_by="codex")

    assert packet["recommendation"]["action"].startswith("Turn Agent Studio")
    assert packet["recommendation"]["recommendation_id"] == 2
    assert packet["recommendation"]["owner"] == "PMM"
    assert packet["recommendation"]["trace_status"] == "current_open_recommendation"
    assert packet["recommendation"]["top_insight"].startswith("Product reality and audience demand align")
    assert packet["evidence_summary"]["recommendation_count"] == 1
    assert packet["evidence_summary"]["evidence_urls"] == [
        "https://www.algolia.com/products/ai-search/",
        "https://datastudio.google.com/",
    ]
    assert "/tmp/private.csv" not in json.dumps(packet)
