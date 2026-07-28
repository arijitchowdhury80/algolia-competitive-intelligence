from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_market_field_story.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_market_field_story", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _agent_studio_payload() -> dict:
    return {
        "selected_hotspot_id": "hotspot-agent-studio",
        "nodes": [
            {"node_id": "hotspot-agent-studio", "label": "Agent Studio", "node_type": "theme"},
            {"node_id": "product-agent-studio", "label": "Product reality", "node_type": "product_reality"},
            {"node_id": "market-agent-studio", "label": "Market conversation", "node_type": "market_conversation"},
            {"node_id": "demand-agent-studio", "label": "Audience Demand", "node_type": "audience_demand"},
            {"node_id": "action-agent-studio", "label": "Product Marketing action", "node_type": "argus_action"},
            {
                "node_id": "unknown-google-agent-studio",
                "label": "Google Vertex AI Search: Agent Studio",
                "node_type": "unknown_boundary",
                "status": "confidence_limit",
            },
        ],
        "edges": [
            {"source_node_id": "product-agent-studio", "target_node_id": "hotspot-agent-studio", "edge_type": "supports_story"},
            {"source_node_id": "market-agent-studio", "target_node_id": "hotspot-agent-studio", "edge_type": "supports_story"},
            {"source_node_id": "hotspot-agent-studio", "target_node_id": "action-agent-studio", "edge_type": "requires_action"},
            {"source_node_id": "hotspot-agent-studio", "target_node_id": "unknown-google-agent-studio", "edge_type": "limits_confidence"},
        ],
        "hotspots": [
            {
                "hotspot_id": "hotspot-agent-studio",
                "label": "Agent Studio",
                "argus_read": "Agent Studio has shipped product proof and Audience Demand.",
                "connected_node_ids": [
                    "hotspot-agent-studio",
                    "product-agent-studio",
                    "market-agent-studio",
                    "demand-agent-studio",
                    "action-agent-studio",
                    "unknown-google-agent-studio",
                ],
                "unknowns": ["Google Vertex AI Search parity is unresolved."],
            }
        ],
        "actions": [
            {
                "owner": "Product Marketing",
                "priority": "P1",
                "action": "Turn Agent Studio into an evidence-backed market narrative.",
                "why_now": "The demand window is cooling.",
            }
        ],
        "proof": [
            {"plane": "product_reality", "summary": "Algolia has shipped Agent Studio product proof.", "source_count": 1},
            {"plane": "market_conversation", "summary": "Competitor AI-search framing is visible.", "source_count": 1},
            {"plane": "audience_demand", "summary": "Looker Studio GA4 export engaged sessions.", "source_count": 1},
            {"plane": "argus_recommendation", "summary": "Product Marketing action.", "source_count": 2},
        ],
    }


def test_validate_story_payload_accepts_agent_studio_story_graph() -> None:
    module = _load_module()

    result = module.validate_story_payload(_agent_studio_payload(), expected_hotspot="Agent Studio")

    assert result["status"] == "passed"
    assert result["selected_hotspot"] == "Agent Studio"
    assert result["required_node_types"] == [
        "product_reality",
        "market_conversation",
        "audience_demand",
        "argus_action",
        "unknown_boundary",
    ]
    assert result["required_proof_planes"] == [
        "product_reality",
        "market_conversation",
        "audience_demand",
        "argus_recommendation",
    ]


def test_validate_story_payload_rejects_missing_audience_demand_plane() -> None:
    module = _load_module()
    payload = _agent_studio_payload()
    payload["nodes"] = [node for node in payload["nodes"] if node["node_type"] != "audience_demand"]

    with pytest.raises(AssertionError, match="audience_demand"):
        module.validate_story_payload(payload, expected_hotspot="Agent Studio")
