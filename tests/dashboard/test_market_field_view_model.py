from cios.dashboard.types import (
    MarketFieldAction,
    MarketFieldEdge,
    MarketFieldHotspot,
    MarketFieldNode,
    MarketFieldProofItem,
    MarketFieldState,
)


def test_market_field_state_distinguishes_unknown_from_absence() -> None:
    state = MarketFieldState(
        selected_hotspot_id="ai-commerce",
        nodes=[
            MarketFieldNode(
                node_id="unknown-ai-agent",
                label="Unknown boundary",
                node_type="unknown_boundary",
                status="confidence_limit",
                summary="Competitor capability cells are unresolved.",
            )
        ],
        edges=[],
        hotspots=[
            MarketFieldHotspot(
                hotspot_id="ai-commerce",
                label="AI commerce ownership",
                movement="rising",
                confidence_label="medium-high",
                proof_status="partial",
                unknowns=["Competitor capability cells are unresolved."],
            )
        ],
        actions=[],
        proof=[],
        time_windows=["today", "7d", "30d", "custom"],
    )

    assert state.nodes[0].node_type == "unknown_boundary"
    assert state.nodes[0].status == "confidence_limit"
    assert "absence" not in state.nodes[0].summary.lower()
    assert state.hotspots[0].unknowns == ["Competitor capability cells are unresolved."]


def test_market_field_state_carries_actions_and_proof_chain() -> None:
    state = MarketFieldState(
        selected_hotspot_id="ai-commerce",
        nodes=[
            MarketFieldNode(node_id="constructor", label="Constructor", node_type="competitor"),
            MarketFieldNode(node_id="demand-agentic", label="Audience demand", node_type="audience_demand"),
        ],
        edges=[
            MarketFieldEdge(
                source_node_id="constructor",
                target_node_id="demand-agentic",
                edge_type="overlaps_demand",
                strength="medium",
            )
        ],
        hotspots=[
            MarketFieldHotspot(
                hotspot_id="ai-commerce",
                label="AI commerce ownership",
                argus_read="AI commerce ownership is becoming the active competitive frame.",
                movement="rising",
                confidence_label="medium-high",
                proof_status="partial",
            )
        ],
        actions=[
            MarketFieldAction(
                owner="PMM",
                priority="P1",
                action="Sharpen AI commerce positioning.",
                why_now="Competitor narrative is moving faster than Algolia's visible story.",
                confidence_label="medium-high",
            )
        ],
        proof=[
            MarketFieldProofItem(
                plane="audience_demand",
                summary="Audience response overlaps the agentic shopping topic.",
                source_count=3,
            )
        ],
        time_windows=["today", "7d", "30d", "custom"],
    )

    assert state.selected_hotspot.label == "AI commerce ownership"
    assert state.actions[0].owner == "PMM"
    assert state.proof[0].plane == "audience_demand"
