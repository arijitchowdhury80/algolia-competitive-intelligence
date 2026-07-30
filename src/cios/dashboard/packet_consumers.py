"""Dashboard and public-status adapters for Argus intelligence packets."""

from __future__ import annotations

from typing import Any

from cios.intelligence.argus_packet import ArgusIntelligencePacket

from .types import (
    DashboardState,
    IntelligencePlaneSummary,
    IntelligenceSpine,
    MarketFieldAction,
    MarketFieldEdge,
    MarketFieldHotspot,
    MarketFieldNode,
    MarketFieldProofItem,
    MarketFieldState,
    RunHealth,
)


def build_dashboard_state_from_packet(packet: ArgusIntelligencePacket) -> DashboardState:
    """Build the first packet-backed dashboard state slice."""

    return DashboardState(
        tenant_id=packet.tenant.tenant_id,
        cadence=packet.cadence,
        generated_at=packet.run.generated_at,
        run_health=RunHealth(
            run_id=packet.run.run_id,
            generated_at=packet.run.generated_at,
            delivery_status=_consumer_status(packet, "telegram_daily"),
            quality_review_status=packet.quality.quality_review_status,
            source_family_count=packet.source_health.active,
        ),
        intelligence_spine=IntelligenceSpine(
            verdict=packet.status,
            top_insight=packet.executive_read.headline,
            primary_action=packet.recommendations[0].action if packet.recommendations else None,
            confidence_limits=[
                *[unknown.summary for unknown in packet.unknowns],
                *packet.quality.residual_risks,
            ],
            planes=[
                IntelligencePlaneSummary(
                    plane=plane.plane,
                    label=plane.plane.replace("_", " ").title(),
                    status=plane.status,
                    signal_count=plane.signal_count,
                    evidence_count=plane.evidence_count,
                    summary=plane.summary,
                    evidence_refs=[{"proof_ref_id": proof_ref_id} for proof_ref_id in plane.proof_ref_ids],
                )
                for plane in packet.evidence_planes
            ],
            pattern_count=len(packet.market_movements),
            recommendation_count=len(packet.recommendations),
            evidence_need_count=len(packet.unknowns),
            leading_entities=_dedupe(entity for movement in packet.market_movements for entity in movement.entities),
            leading_capabilities=_dedupe(
                capability for movement in packet.market_movements for capability in movement.capabilities
            ),
            evidence_urls=[node.url for node in packet.proof_graph.nodes if node.url],
            blocked_actions=[action.blocked_reason for action in packet.blocked_actions],
            can_recommend=bool(packet.recommendations),
            next_operator_action=packet.recommendations[0].action if packet.recommendations else None,
        ),
        market_field=build_market_field_from_packet(packet),
    )


def build_market_field_from_packet(packet: ArgusIntelligencePacket) -> MarketFieldState:
    nodes: dict[str, MarketFieldNode] = {}
    edges: list[MarketFieldEdge] = []
    hotspots: list[MarketFieldHotspot] = []
    actions: list[MarketFieldAction] = []
    proof: list[MarketFieldProofItem] = []

    for movement in packet.market_movements:
        nodes[movement.movement_id] = MarketFieldNode(
            node_id=movement.movement_id,
            label=movement.label,
            node_type="theme",
            summary=movement.summary,
        )
        for entity in movement.entities:
            entity_id = _node_id("entity", entity)
            nodes.setdefault(entity_id, MarketFieldNode(node_id=entity_id, label=entity, node_type="competitor"))
            edges.append(
                MarketFieldEdge(
                    source_node_id=entity_id,
                    target_node_id=movement.movement_id,
                    edge_type="drives_movement",
                    strength=movement.materiality,
                    summary=movement.summary,
                )
            )
        hotspots.append(
            MarketFieldHotspot(
                hotspot_id=movement.movement_id,
                label=movement.label,
                argus_read=movement.summary,
                movement=movement.direction,
                confidence_label=movement.materiality,
                proof_status="present" if movement.proof_ref_ids else "missing",
                time_window=movement.time_window,
                connected_node_ids=[movement.movement_id],
                unknowns=[
                    unknown.summary
                    for unknown in packet.unknowns
                    if movement.movement_id in unknown.limits_ref_ids
                ],
            )
        )

    for recommendation in packet.recommendations:
        node_id = recommendation.recommendation_id
        nodes[node_id] = MarketFieldNode(
            node_id=node_id,
            label=recommendation.owner,
            node_type="recommendation",
            summary=recommendation.action,
        )
        for movement_id in recommendation.movement_ref_ids:
            edges.append(
                MarketFieldEdge(
                    source_node_id=movement_id,
                    target_node_id=node_id,
                    edge_type="supports_recommendation",
                    strength="strong",
                    summary=recommendation.why_now,
                )
            )
        actions.append(
            MarketFieldAction(
                owner=recommendation.owner,
                priority=f"P{recommendation.priority_rank}",
                action=recommendation.action,
                why_now=recommendation.why_now,
                evidence_basis=recommendation.proof_ref_ids,
                confidence_label=str(recommendation.confidence),
            )
        )

    for plane in packet.evidence_planes:
        proof.append(
            MarketFieldProofItem(
                plane=plane.plane,
                summary=plane.summary,
                source_count=plane.evidence_count,
            )
        )

    return MarketFieldState(
        selected_hotspot_id=hotspots[0].hotspot_id if hotspots else None,
        nodes=list(nodes.values()),
        edges=edges,
        hotspots=hotspots,
        actions=actions,
        proof=proof,
    )


def build_public_status_from_packet(packet: ArgusIntelligencePacket) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "run_id": packet.run.run_id,
        "status": packet.status,
        "generated_at": _iso_z(packet.run.generated_at),
        "freshness_status": packet.quality.freshness_status,
        "current_recommendation_count": len(packet.recommendations),
        "consumer_state": packet.consumer_state.model_dump(mode="json"),
        "known_failures": packet.quality.known_failures,
    }


def build_latest_json_from_packet(packet: ArgusIntelligencePacket) -> dict[str, Any]:
    freshness = packet.quality.freshness_status
    if packet.status == "stale" and freshness == "current":
        freshness = "stale"
    return {
        "packet_id": packet.packet_id,
        "run_id": packet.run.run_id,
        "status": packet.status,
        "generated_at": _iso_z(packet.run.generated_at),
        "freshness_status": freshness,
    }


def _consumer_status(packet: ArgusIntelligencePacket, name: str) -> str | None:
    state = getattr(packet.consumer_state, name, None)
    return state.status if state is not None else None


def _node_id(prefix: str, value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return f"{prefix}-{cleaned or 'unknown'}"


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _iso_z(value) -> str:
    text = value.isoformat()
    return text.replace("+00:00", "Z")


__all__ = [
    "build_dashboard_state_from_packet",
    "build_latest_json_from_packet",
    "build_market_field_from_packet",
    "build_public_status_from_packet",
]
