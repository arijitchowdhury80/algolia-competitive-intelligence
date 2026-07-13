"""Business decision read for Argus product-market intelligence.

The synthesizer produces evidence-backed objects. This module turns those
objects into the decision spine a business user needs: direction, priority,
strategic insight, tactical action, confidence basis, and blockers.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field

from .types import ProductMarketResult


PlaneName = Literal["product_reality", "market_conversation", "audience_demand", "learning"]
PlaneStatus = Literal["present", "partial", "missing"]


class DecisionConfidenceBasis(BaseModel):
    plane: PlaneName
    status: PlaneStatus
    evidence_count: int = 0
    summary: str
    evidence_urls: list[str] = Field(default_factory=list)


class StrategicInsight(BaseModel):
    insight_type: str
    summary: str
    involved_companies: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class TacticalAction(BaseModel):
    owner: str
    action: str
    why_now: str
    urgency: str
    confidence: float
    score: int | None = None
    scorecard_verdict: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)


class ArgusDecisionRead(BaseModel):
    status: Literal["actionable", "watch", "quiet"]
    market_direction: str
    priority_reason: str
    strategic_insights: list[StrategicInsight] = Field(default_factory=list)
    tactical_actions: list[TacticalAction] = Field(default_factory=list)
    confidence_basis: list[DecisionConfidenceBasis] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


def build_argus_decision_read(
    *,
    result: ProductMarketResult,
    product_event_count: int,
    conversation_theme_count: int,
    demand_signal_count: int,
    movement_map: Mapping[str, Any] | BaseModel | None = None,
    demand_read: Mapping[str, Any] | BaseModel | None = None,
    product_feature_comparison: Mapping[str, Any] | BaseModel | None = None,
    conversion_diagnostics: Mapping[str, Any] | BaseModel | None = None,
) -> ArgusDecisionRead:
    """Build the operator-facing decision read from deterministic evidence."""

    movement = _as_dict(movement_map)
    demand = _as_dict(demand_read)
    feature_comparison = _as_dict(product_feature_comparison)
    conversion = _as_dict(conversion_diagnostics)

    top_pattern = result.patterns[0] if result.patterns else None
    top_recommendation = result.recommendations[0] if result.recommendations else None

    tactical_actions = [
        TacticalAction(
            owner=str(recommendation.owner),
            action=recommendation.action,
            why_now=recommendation.why_now,
            urgency=str(recommendation.urgency),
            confidence=float(recommendation.confidence),
            score=getattr(recommendation.scorecard, "total_score", None),
            scorecard_verdict=str(getattr(recommendation.scorecard, "verdict", "") or "") or None,
            evidence_urls=_item_evidence_urls(recommendation),
        )
        for recommendation in result.recommendations
    ]
    strategic_insights = [
        StrategicInsight(
            insight_type=str(pattern.pattern_type),
            summary=pattern.summary,
            involved_companies=list(pattern.involved_companies),
            evidence_urls=_item_evidence_urls(pattern),
        )
        for pattern in result.patterns[:5]
    ]

    blockers = _blockers(
        result=result,
        demand_signal_count=demand_signal_count,
        conversion=conversion,
        demand=demand,
    )
    evidence_urls = _dedupe_urls(
        [
            *[url for insight in strategic_insights for url in insight.evidence_urls],
            *[url for action in tactical_actions for url in action.evidence_urls],
            *list(movement.get("evidence_urls") or []),
            *list(demand.get("evidence_urls") or []),
            *_feature_comparison_evidence_urls(feature_comparison),
        ]
    )

    return ArgusDecisionRead(
        status=result.verdict,
        market_direction=_market_direction(result=result, movement=movement),
        priority_reason=_priority_reason(
            result=result,
            top_pattern=top_pattern,
            has_action=bool(top_recommendation),
            demand_signal_count=demand_signal_count,
        ),
        strategic_insights=strategic_insights,
        tactical_actions=tactical_actions,
        confidence_basis=[
            _product_reality_basis(product_event_count, feature_comparison),
            _market_conversation_basis(conversation_theme_count, strategic_insights),
            _audience_demand_basis(demand_signal_count, demand),
        ],
        blockers=blockers,
        evidence_urls=evidence_urls,
    )


def _as_dict(value: Mapping[str, Any] | BaseModel | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def _market_direction(*, result: ProductMarketResult, movement: Mapping[str, Any]) -> str:
    top_pattern = result.patterns[0] if result.patterns else None
    if top_pattern is not None and result.verdict == "actionable":
        companies = _join_human(list(top_pattern.involved_companies[:3]))
        if companies:
            return f"{top_pattern.capability} is heating up around {companies}."
        return f"{top_pattern.capability} is heating up in the current evidence window."
    direction = str(movement.get("direction_summary") or "").strip()
    if direction:
        return direction
    if top_pattern is not None:
        return f"{top_pattern.capability} is the strongest captured movement, but action has not cleared."
    return "No market direction qualified from the current product, conversation, and demand evidence."


def _priority_reason(
    *,
    result: ProductMarketResult,
    top_pattern: Any,
    has_action: bool,
    demand_signal_count: int,
) -> str:
    if top_pattern is None:
        return "Argus has no priority recommendation because no cross-plane product-market pattern qualified."
    if has_action:
        return (
            f"{_join_human(list(top_pattern.involved_companies[:3])) or 'This movement'} is priority "
            f"because {top_pattern.summary} tenant-side demand evidence is present, so Argus can promote "
            "an owner action instead of only watching the market."
        )
    if demand_signal_count == 0:
        return (
            f"Watch {_join_human(list(top_pattern.involved_companies[:3])) or 'this movement'} because "
            f"{top_pattern.summary} Argus withheld owner action until tenant-side demand evidence is present."
        )
    return (
        f"Watch {_join_human(list(top_pattern.involved_companies[:3])) or 'this movement'} because "
        f"{top_pattern.summary} Argus withheld owner action until the scoring and learning gates clear."
    )


def _product_reality_basis(
    product_event_count: int,
    feature_comparison: Mapping[str, Any],
) -> DecisionConfidenceBasis:
    urls = _feature_comparison_evidence_urls(feature_comparison)
    status: PlaneStatus = "present" if product_event_count else "missing"
    summary = (
        f"{product_event_count} product-reality event(s) captured from Scout, changelog, docs, or product surfaces."
        if product_event_count
        else "No product-reality evidence was captured, so Argus cannot prove what shipped."
    )
    return DecisionConfidenceBasis(
        plane="product_reality",
        status=status,
        evidence_count=product_event_count,
        summary=summary,
        evidence_urls=urls,
    )


def _market_conversation_basis(
    conversation_theme_count: int,
    strategic_insights: list[StrategicInsight],
) -> DecisionConfidenceBasis:
    status: PlaneStatus = "present" if conversation_theme_count else "missing"
    summary = (
        f"{conversation_theme_count} market-conversation theme(s) captured from public positioning evidence."
        if conversation_theme_count
        else "No market-conversation evidence was captured, so Argus cannot prove what the market is saying."
    )
    return DecisionConfidenceBasis(
        plane="market_conversation",
        status=status,
        evidence_count=conversation_theme_count,
        summary=summary,
        evidence_urls=_dedupe_urls(url for insight in strategic_insights for url in insight.evidence_urls),
    )


def _audience_demand_basis(
    demand_signal_count: int,
    demand: Mapping[str, Any],
) -> DecisionConfidenceBasis:
    status: PlaneStatus = "present" if demand_signal_count else "missing"
    summary = (
        f"{demand_signal_count} tenant-side demand signal(s) captured from GA / Looker-style evidence."
        if demand_signal_count
        else "No tenant-side demand evidence was captured, so Argus must withhold owner action and priority ranking."
    )
    return DecisionConfidenceBasis(
        plane="audience_demand",
        status=status,
        evidence_count=demand_signal_count,
        summary=summary,
        evidence_urls=_dedupe_urls(str(url) for url in demand.get("evidence_urls") or []),
    )


def _blockers(
    *,
    result: ProductMarketResult,
    demand_signal_count: int,
    conversion: Mapping[str, Any],
    demand: Mapping[str, Any],
) -> list[str]:
    blockers = [str(item).strip() for item in conversion.get("blockers") or [] if str(item).strip()]
    if demand_signal_count == 0:
        blockers.append("No tenant-side demand evidence was captured, so Argus cannot promote owner action.")
    for item in demand.get("confidence_limits") or []:
        text = str(item).strip()
        if text:
            blockers.append(text)
    if result.patterns and not result.recommendations:
        blockers.append("Owner action withheld until all required evidence and learning gates clear.")
    return _dedupe_urls(blockers)


def _item_evidence_urls(item: Any) -> list[str]:
    return _dedupe_urls(
        str(getattr(evidence, "source_url", "") or "")
        for evidence in getattr(item, "evidence", []) or []
        if getattr(evidence, "source_url", None)
    )


def _feature_comparison_evidence_urls(feature_comparison: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    for row in feature_comparison.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        urls.extend(str(url) for url in row.get("evidence_urls") or [] if str(url).strip())
    return _dedupe_urls(urls)


def _dedupe_urls(urls: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        url = str(raw).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _join_human(items: list[str]) -> str:
    cleaned = [item for item in (str(item).strip() for item in items) if item]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


__all__ = [
    "ArgusDecisionRead",
    "DecisionConfidenceBasis",
    "StrategicInsight",
    "TacticalAction",
    "build_argus_decision_read",
]
