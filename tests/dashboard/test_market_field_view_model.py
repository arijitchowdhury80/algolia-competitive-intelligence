from cios.dashboard.state_builder import DashboardStateBuilder
from cios.dashboard.types import (
    MarketFieldAction,
    MarketFieldEdge,
    MarketFieldHotspot,
    MarketFieldNode,
    MarketFieldProofItem,
    MarketFieldState,
)
from tests.dashboard.conftest import (
    FakeCoverageRepository,
    FakeProductMarketRepository,
    FakeRunRepository,
    FakeSignalsRepository,
    FakeThesesRepository,
    argus_recommendation_row,
    demand_signal_row,
    feature_position_row,
    full_coverage,
    product_market_pattern_row,
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


def test_builder_compiles_market_field_from_patterns_recommendations_and_unknowns() -> None:
    product_market = FakeProductMarketRepository(
        patterns={
            1: [
                product_market_pattern_row(
                    id=10,
                    pattern_type="theme",
                    capability_text="AI commerce ownership",
                    summary="Constructor and Coveo are concentrating around AI commerce.",
                    involved_companies=["Constructor", "Coveo"],
                    confidence=0.72,
                )
            ]
        },
        recommendations={
            1: [
                argus_recommendation_row(
                    id=20,
                    pattern_observation_id=10,
                    owner="PMM",
                    action="Sharpen AI commerce positioning.",
                    why_now="Competitor narrative is moving faster than Algolia's visible story.",
                )
            ]
        },
        feature_positions={
            1: [
                feature_position_row(
                    company_name="Constructor",
                    capability_text="AI shopping agents",
                    position_status="unknown",
                    summary="Product proof is unresolved for this competitor capability.",
                )
            ]
        },
        demand_signals={
            1: [
                demand_signal_row(
                    topic="agentic shopping",
                    change_pct=0.31,
                    metadata={"summary": "Audience demand is rising for agentic shopping pages."},
                )
            ]
        },
    )
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({1: []}),
        theses=FakeThesesRepository({1: []}),
        coverage=FakeCoverageRepository({1: full_coverage()}),
        runs=FakeRunRepository({}),
        product_market=product_market,
    )

    state = builder.build(tenant_id=1, cadence="daily")

    field = state.market_field
    assert field.selected_hotspot.label == "AI commerce ownership"
    assert any(node.node_type == "audience_demand" for node in field.nodes)
    assert any(node.node_type == "unknown_boundary" for node in field.nodes)
    assert field.actions[0].owner == "PMM"
    assert "absence" not in " ".join(node.summary or "" for node in field.nodes).lower()
