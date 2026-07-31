"""Canonical Argus intelligence packet contract.

The packet is the run-bound source of truth that dashboard, Telegram, public
status, Evidence Lab, Admin, and Market Field consumers must adapt from. This
module deliberately contains no DB, network, or Hermes-core behavior.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


PacketStatus = Literal["actionable", "watch", "quiet_verified", "degraded", "blocked", "failed", "stale"]
ConsumerStatus = Literal["rendered", "sent", "published", "skipped", "failed", "blocked", "stale", "not_applicable"]


class TenantIdentity(BaseModel):
    tenant_id: int
    slug: str
    display_name: str


class RunIdentity(BaseModel):
    run_id: str
    generated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    hermes_job_id: str | None = None
    hermes_profile: str | None = None
    package_commit: str
    package_release_id: str | None = None
    package_sha256: str | None = None
    produced_by_user: str = "unknown"
    source: Literal["hermes_cron", "manual_forced", "local_test", "unknown"] = "unknown"


class TimeWindow(BaseModel):
    label: str
    start_at: datetime
    end_at: datetime
    comparison_start_at: datetime | None = None
    comparison_end_at: datetime | None = None
    grain: Literal["daily", "weekly", "monthly", "custom"]
    movement_basis: str


class ExecutiveRead(BaseModel):
    headline: str
    plain_read: str
    why_it_matters_to_algolia: str
    market_belief_implied: str
    what_may_happen_next: str
    decision_posture: Literal["act", "watch", "wait_for_proof", "quiet", "investigate", "blocked"]
    primary_movement_id: str | None = None
    primary_recommendation_id: str | None = None
    proof_ref_ids: list[str] = Field(default_factory=list)
    confidence_ref_ids: list[str] = Field(default_factory=list)


class EvidencePlane(BaseModel):
    plane: str
    status: Literal["present", "partial", "missing", "stale", "failed", "not_required"]
    summary: str
    signal_count: int = 0
    evidence_count: int = 0
    coverage: dict[str, Any] = Field(default_factory=dict)
    proof_ref_ids: list[str] = Field(default_factory=list)
    confidence_impact: str


class MarketMovement(BaseModel):
    movement_id: str
    label: str
    summary: str
    movement_type: str = "mixed"
    direction: str = "unknown"
    velocity: str = "unknown"
    materiality: str = "unknown"
    time_window: str
    entities: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    evidence_plane_refs: list[str] = Field(default_factory=list)
    proof_ref_ids: list[str] = Field(default_factory=list)
    contradiction_ref_ids: list[str] = Field(default_factory=list)
    unknown_ref_ids: list[str] = Field(default_factory=list)
    recommendation_ref_ids: list[str] = Field(default_factory=list)
    field_graph_ref_id: str


class AttentionState(BaseModel):
    now: list[str] = Field(default_factory=list)
    monitor: list[str] = Field(default_factory=list)
    quiet: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class ScorecardDimension(BaseModel):
    dimension: str
    score: int | float = 0
    proof_ref_ids: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class RecommendationScorecard(BaseModel):
    total_score: int | float
    verdict: str
    dimensions: list[ScorecardDimension] = Field(default_factory=list)
    dimension_scores: list[ScorecardDimension] = Field(default_factory=list)


class PacketRecommendation(BaseModel):
    recommendation_id: str
    owner: str
    action: str
    why_now: str
    expected_outcome: str
    urgency: str
    confidence: float
    priority_rank: int = 1
    status: str = "open"
    movement_ref_ids: list[str] = Field(default_factory=list)
    proof_ref_ids: list[str] = Field(default_factory=list)
    scorecard: RecommendationScorecard
    next_review_at: datetime | None = None


class BlockedAction(BaseModel):
    blocked_action_id: str
    owner: str
    proposed_action: str
    blocked_reason: str
    needed_evidence: list[str] = Field(default_factory=list)
    next_monitoring_action_ref_ids: list[str] = Field(default_factory=list)
    movement_ref_ids: list[str] = Field(default_factory=list)


class ProofNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    url: str | None = None


class ProofEdge(BaseModel):
    source_node_id: str
    target_node_id: str
    edge_type: str


class ProofGraph(BaseModel):
    nodes: list[ProofNode] = Field(default_factory=list)
    edges: list[ProofEdge] = Field(default_factory=list)
    root_claim_ids: list[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    contradiction_id: str
    summary: str
    weakens_ref_ids: list[str] = Field(default_factory=list)
    proof_ref_ids: list[str] = Field(default_factory=list)


class UnknownBoundary(BaseModel):
    unknown_id: str
    summary: str
    limits_ref_ids: list[str] = Field(default_factory=list)
    needed_evidence: list[str] = Field(default_factory=list)


class SourceHealthSummary(BaseModel):
    active: int = 0
    checked: int = 0
    failed: int = 0
    stale: int = 0
    confidence_impact: str = "not recorded"


class NextMonitoringAction(BaseModel):
    action_id: str
    summary: str
    owner: str = "Argus"
    evidence_needed: list[str] = Field(default_factory=list)


class ConsumerRunState(BaseModel):
    status: ConsumerStatus
    run_id: str
    packet_id: str | None = None
    artifact_url: str | None = None
    artifact_path: str | None = None
    delivery_id: int | None = None
    rendered_at: datetime | None = None
    error: str | None = None


class ConsumerState(BaseModel):
    telegram_daily: ConsumerRunState | None = None
    telegram_weekly: ConsumerRunState | None = None
    dashboard: ConsumerRunState | None = None
    market_field: ConsumerRunState | None = None
    evidence_lab: ConsumerRunState | None = None
    admin: ConsumerRunState | None = None
    public_status: ConsumerRunState | None = None

    def items(self) -> list[tuple[str, ConsumerRunState]]:
        return [
            (name, state)
            for name in (
                "telegram_daily",
                "telegram_weekly",
                "dashboard",
                "market_field",
                "evidence_lab",
                "admin",
                "public_status",
            )
            if (state := getattr(self, name)) is not None
        ]


class PacketQuality(BaseModel):
    quality_review_status: str
    freshness_status: str
    redaction_status: str
    source_coverage_status: str
    run_identity_status: str
    consumer_parity_status: str
    known_failures: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)


class RejectedRead(BaseModel):
    read_id: str
    reason: str
    proof_ref_ids: list[str] = Field(default_factory=list)


class PacketLineage(BaseModel):
    upstream_objects: list[str] = Field(default_factory=list)
    source_artifacts: list[str] = Field(default_factory=list)
    rejected_reads: list[RejectedRead] = Field(default_factory=list)


class ArgusIntelligencePacket(BaseModel):
    schema_version: int = 1
    packet_id: str
    tenant: TenantIdentity
    run: RunIdentity
    cadence: Literal["daily", "weekly", "monthly", "custom"]
    time_window: TimeWindow
    status: PacketStatus
    executive_read: ExecutiveRead
    market_movements: list[MarketMovement] = Field(default_factory=list)
    attention_state: AttentionState = Field(default_factory=AttentionState)
    recommendations: list[PacketRecommendation] = Field(default_factory=list)
    blocked_actions: list[BlockedAction] = Field(default_factory=list)
    evidence_planes: list[EvidencePlane] = Field(default_factory=list)
    proof_graph: ProofGraph
    contradictions: list[Contradiction] = Field(default_factory=list)
    unknowns: list[UnknownBoundary] = Field(default_factory=list)
    source_health: SourceHealthSummary
    next_monitoring_actions: list[NextMonitoringAction] = Field(default_factory=list)
    consumer_state: ConsumerState = Field(default_factory=ConsumerState)
    quality: PacketQuality
    lineage: PacketLineage = Field(default_factory=PacketLineage)

    @model_validator(mode="after")
    def _enforce_packet_invariants(self) -> "ArgusIntelligencePacket":
        if self.status == "actionable":
            if not self.recommendations:
                raise ValueError("actionable packet requires at least one recommendation")
            for recommendation in self.recommendations:
                if not recommendation.proof_ref_ids:
                    raise ValueError("promoted recommendation requires proof_ref_ids")
                if not recommendation.movement_ref_ids:
                    raise ValueError("promoted recommendation requires movement_ref_ids")
        if self.status == "quiet_verified" and self.source_health.checked < self.source_health.active:
            raise ValueError("quiet_verified requires checked source coverage")
        for _, state in self.consumer_state.items():
            if state.run_id != self.run.run_id:
                raise ValueError("consumer run_id drift from packet run_id")
            if state.packet_id is not None and state.packet_id != self.packet_id:
                raise ValueError("consumer packet_id drift from packet packet_id")
        return self


def build_argus_packet_from_components(
    *,
    tenant: dict[str, Any],
    run: dict[str, Any],
    cadence: str,
    time_window: dict[str, Any],
    intelligence_brief: dict[str, Any],
    decision_read: dict[str, Any],
    movement_map: dict[str, Any],
    recommendations: list[dict[str, Any]],
    source_health: dict[str, Any],
    consumer_state: dict[str, Any],
) -> ArgusIntelligencePacket:
    """Adapt existing product-market objects into the canonical packet."""

    run_id = str(run["run_id"])
    packet_id = f"packet-{run_id}"
    proof_nodes = _proof_nodes_from_urls(
        [
            *list(intelligence_brief.get("evidence_urls") or []),
            *list(decision_read.get("evidence_urls") or []),
            *list(movement_map.get("evidence_urls") or []),
            *[
                str(ref.get("source_url"))
                for recommendation in recommendations
                for ref in recommendation.get("evidence_refs", [])
                if ref.get("source_url")
            ],
        ]
    )
    market_movements = _market_movements_from_movement_map(movement_map, time_window=time_window)
    recommendation_packets = _recommendations_from_rows(
        recommendations,
        movement_ref_ids=[movement.movement_id for movement in market_movements],
        proof_ref_ids=[node.node_id for node in proof_nodes],
    )
    blocked_actions = _blocked_actions_from_decision_read(
        decision_read,
        movement_ref_ids=[movement.movement_id for movement in market_movements],
    )
    evidence_planes = _evidence_planes_from_decision_read(decision_read)
    if not evidence_planes:
        evidence_planes = [
            EvidencePlane(
                plane="source_health",
                status="present",
                summary=source_health.get("confidence_impact") or "Source health was recorded.",
                signal_count=int(source_health.get("checked") or 0),
                evidence_count=0,
                coverage=source_health,
                proof_ref_ids=[],
                confidence_impact=source_health.get("confidence_impact") or "not recorded",
            )
        ]

    packet_status = _packet_status_from_components(
        decision_read.get("status") or intelligence_brief.get("verdict") or "watch",
        source_health=source_health,
    )

    return ArgusIntelligencePacket.model_validate(
        {
            "schema_version": 1,
            "packet_id": packet_id,
            "tenant": tenant,
            "run": run,
            "cadence": cadence,
            "time_window": time_window,
            "status": packet_status,
            "executive_read": {
                "headline": intelligence_brief.get("top_insight") or decision_read.get("market_direction") or "No Argus read produced.",
                "plain_read": intelligence_brief.get("top_insight") or decision_read.get("priority_reason") or "No Argus read produced.",
                "why_it_matters_to_algolia": decision_read.get("priority_reason") or "Argus has not recorded a business implication.",
                "market_belief_implied": decision_read.get("market_direction") or "Market belief was not recorded.",
                "what_may_happen_next": "; ".join(intelligence_brief.get("next_questions") or [])
                or "Argus will monitor the next evidence window.",
                "decision_posture": "act" if recommendation_packets else ("watch" if blocked_actions else "investigate"),
                "primary_movement_id": market_movements[0].movement_id if market_movements else None,
                "primary_recommendation_id": recommendation_packets[0].recommendation_id if recommendation_packets else None,
                "proof_ref_ids": [node.node_id for node in proof_nodes],
                "confidence_ref_ids": [plane.plane for plane in evidence_planes],
            },
            "market_movements": [movement.model_dump(mode="json") for movement in market_movements],
            "attention_state": {
                "now": [market_movements[0].movement_id] if market_movements else [],
                "monitor": [],
                "quiet": [],
                "blocked": [action.blocked_action_id for action in blocked_actions],
            },
            "recommendations": [recommendation.model_dump(mode="json") for recommendation in recommendation_packets],
            "blocked_actions": [blocked_action.model_dump(mode="json") for blocked_action in blocked_actions],
            "evidence_planes": [plane.model_dump(mode="json") for plane in evidence_planes],
            "proof_graph": {
                "root_claim_ids": [proof_nodes[0].node_id] if proof_nodes else [],
                "nodes": [node.model_dump(mode="json") for node in proof_nodes],
                "edges": [],
            },
            "contradictions": [],
            "unknowns": [],
            "source_health": source_health,
            "next_monitoring_actions": _next_monitoring_actions_from_brief(
                intelligence_brief.get("next_monitoring_actions") or []
            ),
            "consumer_state": _consumer_state_with_packet_id(consumer_state, run_id=run_id, packet_id=packet_id),
            "quality": {
                "quality_review_status": "not_reviewed",
                "freshness_status": "current",
                "redaction_status": "not_reviewed",
                "source_coverage_status": "passed" if int(source_health.get("checked") or 0) else "unknown",
                "run_identity_status": "passed",
                "consumer_parity_status": "passed",
                "known_failures": [],
                "residual_risks": list(intelligence_brief.get("confidence_limits") or []),
            },
            "lineage": {
                "upstream_objects": ["ProductMarketIntelligenceBrief", "ArgusDecisionRead", "MarketMovementMap"],
                "source_artifacts": [],
            },
        }
    )


def _safe_id(prefix: str, value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return f"{prefix}-{cleaned or 'unknown'}"


def _packet_status_from_components(raw_status: str, *, source_health: dict[str, Any]) -> str:
    status = str(raw_status or "watch")
    if status == "quiet":
        return "quiet_verified"
    if status == "actionable" and int(source_health.get("failed") or 0) > 0:
        return "degraded"
    return status


def _proof_nodes_from_urls(urls: list[str]) -> list[ProofNode]:
    nodes: list[ProofNode] = []
    seen: set[str] = set()
    for url in urls:
        text = str(url).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        nodes.append(ProofNode(node_id=_safe_id("proof", text), node_type="source_event", label=text, url=text))
    return nodes


def _movement_direction(heat_level: str) -> str:
    return {"hot": "rising", "warm": "rising", "cool": "cooling"}.get(heat_level, "unknown")


def _movement_velocity(heat_level: str) -> str:
    return {"hot": "high", "warm": "medium", "cool": "low"}.get(heat_level, "unknown")


def _market_movements_from_movement_map(movement_map: dict[str, Any], *, time_window: dict[str, Any]) -> list[MarketMovement]:
    movements: list[MarketMovement] = []
    cells_by_capability: dict[str, list[dict[str, Any]]] = {}
    for raw_cell in movement_map.get("heat_cells") or []:
        if not isinstance(raw_cell, dict):
            continue
        capability = str(raw_cell.get("capability") or "Market movement").strip() or "Market movement"
        cells_by_capability.setdefault(capability, []).append(raw_cell)

    for capability, cells in cells_by_capability.items():
        movement_id = _safe_id("movement", capability)
        proof_urls = _dedupe_text(
            str(url)
            for cell in cells
            for url in cell.get("evidence_urls") or []
        )
        heat_level = _top_heat_level(cells)
        movements.append(
            MarketMovement(
                movement_id=movement_id,
                label=capability,
                summary=_movement_summary(movement_map, capability),
                movement_type="mixed",
                direction=_movement_direction(heat_level),
                velocity=_movement_velocity(heat_level),
                materiality="high" if heat_level == "hot" else "medium",
                time_window=str(time_window.get("label") or "today"),
                entities=sorted(
                    _dedupe_text(
                        str(cell.get("company_name") or "")
                        for cell in cells
                        if cell.get("company_name")
                    )
                ),
                capabilities=[capability],
                themes=[capability],
                evidence_plane_refs=[],
                proof_ref_ids=[_safe_id("proof", url) for url in proof_urls],
                recommendation_ref_ids=[],
                field_graph_ref_id=_safe_id("field", capability),
            )
        )
    return movements


def _recommendations_from_rows(
    recommendations: list[dict[str, Any]], *, movement_ref_ids: list[str], proof_ref_ids: list[str]
) -> list[PacketRecommendation]:
    packets: list[PacketRecommendation] = []
    for index, recommendation in enumerate(recommendations, start=1):
        rec_id = f"argus-recommendation-{recommendation.get('id') or index}"
        scorecard = recommendation.get("scorecard") or {}
        dimensions = scorecard.get("dimensions") or scorecard.get("dimension_scores") or []
        packets.append(
            PacketRecommendation(
                recommendation_id=rec_id,
                owner=str(recommendation.get("owner") or "Operator"),
                action=str(recommendation.get("action") or ""),
                why_now=str(recommendation.get("why_now") or ""),
                expected_outcome=str(recommendation.get("expected_outcome") or "Move the selected market read forward."),
                urgency=str(recommendation.get("urgency") or "monitor"),
                confidence=float(recommendation.get("confidence") or 0),
                priority_rank=index,
                status=str(recommendation.get("status") or "open"),
                movement_ref_ids=movement_ref_ids,
                proof_ref_ids=proof_ref_ids,
                scorecard={
                    "total_score": scorecard.get("total_score") or 0,
                    "verdict": scorecard.get("verdict") or "not_scored",
                    "dimensions": dimensions,
                },
            )
        )
    return packets


def _blocked_actions_from_decision_read(decision_read: dict[str, Any], *, movement_ref_ids: list[str]) -> list[BlockedAction]:
    blocked: list[BlockedAction] = []
    for index, reason in enumerate(decision_read.get("blockers") or [], start=1):
        blocked.append(
            BlockedAction(
                blocked_action_id=f"blocked-action-{index}",
                owner="Operator",
                proposed_action="Promote the current Argus read.",
                blocked_reason=str(reason),
                needed_evidence=_needed_evidence_from_blocker(str(reason)),
                movement_ref_ids=movement_ref_ids,
            )
        )
    return blocked


def _movement_summary(movement_map: dict[str, Any], capability: str) -> str:
    summary = str(movement_map.get("direction_summary") or "").strip()
    if summary and capability.lower() in summary.lower():
        return summary
    return f"{capability} is the selected market movement."


def _top_heat_level(cells: list[dict[str, Any]]) -> str:
    ranked = sorted(
        (str(cell.get("heat_level") or "") for cell in cells),
        key=lambda level: {"hot": 3, "warm": 2, "watch": 1, "cool": 0}.get(level, 0),
        reverse=True,
    )
    return ranked[0] if ranked else "unknown"


def _dedupe_text(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        text = str(raw).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _needed_evidence_from_blocker(reason: str) -> list[str]:
    lowered = reason.lower()
    if "tenant-side demand" in lowered or "rising demand" in lowered:
        return ["Fresh Audience Demand evidence for the selected movement."]
    if "learning" in lowered or "gate" in lowered:
        return ["Learning-gate evidence showing the read is safe to promote."]
    return ["Additional source evidence that resolves this blocker."]


def _evidence_planes_from_decision_read(decision_read: dict[str, Any]) -> list[EvidencePlane]:
    planes: list[EvidencePlane] = []
    for basis in decision_read.get("confidence_basis") or []:
        plane = str(basis.get("plane") or "unknown")
        urls = [str(url) for url in basis.get("evidence_urls") or []]
        planes.append(
            EvidencePlane(
                plane=plane,
                status=basis.get("status") or "partial",
                summary=str(basis.get("summary") or ""),
                signal_count=int(basis.get("evidence_count") or 0),
                evidence_count=int(basis.get("evidence_count") or 0),
                coverage={},
                proof_ref_ids=[_safe_id("proof", url) for url in urls],
                confidence_impact=str(basis.get("summary") or ""),
            )
        )
    return planes


def _next_monitoring_actions_from_brief(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, action in enumerate(actions, start=1):
        action_id = action.get("action_id") or _safe_id("monitor", action.get("instruction") or action.get("summary") or str(index))
        evidence_needed = action.get("evidence_needed")
        if evidence_needed is None:
            evidence_needed = action.get("source_families") or action.get("evidence_urls") or []
        normalized.append(
            {
                "action_id": str(action_id),
                "summary": str(action.get("summary") or action.get("instruction") or action.get("reason") or "Recheck evidence."),
                "owner": str(action.get("owner") or "Argus"),
                "evidence_needed": [str(item) for item in evidence_needed],
            }
        )
    return normalized


def _consumer_state_with_packet_id(
    consumer_state: dict[str, Any], *, run_id: str, packet_id: str
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for name, state in consumer_state.items():
        normalized[name] = {**state, "run_id": state.get("run_id") or run_id, "packet_id": state.get("packet_id") or packet_id}
    return normalized


__all__ = [
    "ArgusIntelligencePacket",
    "AttentionState",
    "BlockedAction",
    "ConsumerRunState",
    "ConsumerState",
    "Contradiction",
    "EvidencePlane",
    "ExecutiveRead",
    "MarketMovement",
    "NextMonitoringAction",
    "PacketLineage",
    "PacketQuality",
    "PacketRecommendation",
    "ProofGraph",
    "ProofNode",
    "RunIdentity",
    "SourceHealthSummary",
    "TenantIdentity",
    "TimeWindow",
    "UnknownBoundary",
    "build_argus_packet_from_components",
]
