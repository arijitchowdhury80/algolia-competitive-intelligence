"""Derive product muscle matrix positions from product evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, Field

from .capabilities import capability_key, demand_capability_key
from .demand_quality import DemandQualityConfig, demand_quality_config, is_rising_demand_signal
from .product_market import _dedupe_evidence
from .types import ConversationTheme, DemandSignal, EvidenceRef, FeaturePosition, ProductChangeEvent


AssessmentKind = Literal[
    "own_product_gap",
    "own_narrative_gap",
    "competitive_parity",
    "demand_without_product_proof",
    "conversation_without_product_proof",
    "competitive_pressure",
    "watch",
]


class ProductFeatureComparisonRow(BaseModel):
    """One capability-level product comparison read for Argus."""

    capability: str
    capability_key: str
    assessment: AssessmentKind
    own_company_name: str
    own_status: Literal["unknown", "proven", "claimed", "gap", "disproven"]
    competitors_with_product_proof: list[str] = Field(default_factory=list)
    competitors_with_conversation: list[str] = Field(default_factory=list)
    has_rising_demand: bool = False
    demand_signal_count: int = 0
    top_demand_change_pct: float | None = None
    recommended_action: str
    evidence_urls: list[str] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)


class ProductFeatureComparisonRead(BaseModel):
    """Backend feature comparison read combining product, conversation, demand."""

    summary: str
    row_count: int = 0
    product_gap_count: int = 0
    narrative_gap_count: int = 0
    demand_backed_count: int = 0
    rows: list[ProductFeatureComparisonRow] = Field(default_factory=list)


def _position_status(event: ProductChangeEvent) -> str:
    if event.change_type == "deprecation":
        return "disproven"
    return "proven"


def derive_feature_positions_from_product_events(
    product_events: list[ProductChangeEvent],
) -> list[FeaturePosition]:
    """Collapse product events into current company/capability positions."""

    grouped: dict[tuple[int, str, str, str], list[ProductChangeEvent]] = defaultdict(list)
    for event in product_events:
        key = (
            event.tenant_id,
            event.capability.strip().lower(),
            event.company_role,
            event.company_name.strip().lower(),
        )
        grouped[key].append(event)

    positions: list[FeaturePosition] = []
    for events in grouped.values():
        ranked = sorted(events, key=lambda event: event.observed_at, reverse=True)
        latest = ranked[0]
        evidence: list[EvidenceRef] = _dedupe_evidence(e for event in ranked for e in event.evidence)
        positions.append(
            FeaturePosition(
                tenant_id=latest.tenant_id,
                company_id=latest.company_id,
                company_name=latest.company_name,
                company_role=latest.company_role,
                capability=latest.capability,
                position_status=_position_status(latest),  # type: ignore[arg-type]
                summary=latest.summary,
                last_seen_at=latest.observed_at,
                confidence=0.72 if latest.change_type != "deprecation" else 0.68,
                evidence=evidence,
            )
        )

    return positions


def build_product_feature_comparison_read(
    *,
    own_company_name: str,
    product_events: list[ProductChangeEvent],
    conversation_themes: list[ConversationTheme],
    demand_signals: list[DemandSignal],
    demand_quality: DemandQualityConfig | dict[str, Any] | None = None,
) -> ProductFeatureComparisonRead:
    """Build Argus's product-feature comparison read.

    This turns the product muscle matrix into an intelligence object by fusing
    product proof with market conversation and tenant-side demand. A missing
    own product cell becomes an "own product gap" only when competitor proof
    and rising demand justify that stronger claim.
    """

    own_norm = _norm(own_company_name)
    positions_by_cap: dict[str, list[FeaturePosition]] = defaultdict(list)
    conversation_by_cap: dict[str, list[ConversationTheme]] = defaultdict(list)
    rising_demand_by_cap: dict[str, list[DemandSignal]] = defaultdict(list)
    labels: dict[str, str] = {}
    quality = demand_quality_config(demand_quality)

    for position in derive_feature_positions_from_product_events(product_events):
        key = _capability_key(position.capability)
        if not key:
            continue
        positions_by_cap[key].append(position)
        labels.setdefault(key, position.capability)

    for theme in conversation_themes:
        key = _capability_key(theme.theme)
        if not key:
            continue
        conversation_by_cap[key].append(theme)
        labels.setdefault(key, theme.theme)

    for signal in demand_signals:
        if not is_rising_demand_signal(
            signal,
            change_floor=quality.change_floor,
            value_floor=quality.value_floor,
        ):
            continue
        key = demand_capability_key(signal.topic, signal.metadata)
        if not key:
            continue
        rising_demand_by_cap[key].append(signal)
        labels[key] = signal.topic

    rows = [
        _comparison_row(
            capability_key=key,
            capability=labels.get(key, key),
            own_company_name=own_company_name,
            own_norm=own_norm,
            positions=positions_by_cap.get(key, []),
            conversations=conversation_by_cap.get(key, []),
            demands=rising_demand_by_cap.get(key, []),
        )
        for key in sorted(set(positions_by_cap) | set(conversation_by_cap) | set(rising_demand_by_cap))
    ]
    rows.sort(key=_row_sort_key)

    product_gap_count = sum(1 for row in rows if row.assessment == "own_product_gap")
    narrative_gap_count = sum(1 for row in rows if row.assessment == "own_narrative_gap")
    demand_backed_count = sum(1 for row in rows if row.has_rising_demand)
    summary = (
        f"{_plural(len(rows), 'capability')} compared; "
        f"{product_gap_count} product {_gap_label(product_gap_count)}, "
        f"{narrative_gap_count} narrative {_gap_label(narrative_gap_count)}, "
        f"{demand_backed_count} demand-backed {_row_label(demand_backed_count)}."
    )
    if not rows:
        summary = "No product-feature comparison could be built from the current evidence set."

    return ProductFeatureComparisonRead(
        summary=summary,
        row_count=len(rows),
        product_gap_count=product_gap_count,
        narrative_gap_count=narrative_gap_count,
        demand_backed_count=demand_backed_count,
        rows=rows,
    )


def _comparison_row(
    *,
    capability_key: str,
    capability: str,
    own_company_name: str,
    own_norm: str,
    positions: list[FeaturePosition],
    conversations: list[ConversationTheme],
    demands: list[DemandSignal],
) -> ProductFeatureComparisonRow:
    own_positions = [
        position
        for position in positions
        if position.company_role == "own" or _norm(position.company_name) == own_norm
    ]
    competitor_positions = [
        position
        for position in positions
        if position.company_role == "competitor" and _norm(position.company_name) != own_norm
    ]
    own_conversations = [
        theme
        for theme in conversations
        if theme.company_name and _norm(theme.company_name) == own_norm
    ]
    competitor_conversations = [
        theme
        for theme in conversations
        if not theme.company_name or _norm(theme.company_name) != own_norm
    ]

    own_status = _own_status(own_positions, bool(competitor_positions), bool(demands))
    competitors_with_product = sorted({position.company_name for position in competitor_positions})
    competitors_with_conversation = sorted(
        {theme.company_name or "market" for theme in competitor_conversations}
    )
    evidence_urls = _dedupe_urls(
        [
            *[url for position in positions for url in _evidence_urls(position)],
            *[url for theme in conversations for url in _evidence_urls(theme)],
            *[url for signal in demands for url in _evidence_urls(signal)],
        ]
    )
    assessment = _assessment(
        own_status=own_status,
        has_own_conversation=bool(own_conversations),
        competitor_product_count=len(competitor_positions),
        competitor_conversation_count=len(competitor_conversations),
        demand_count=len(demands),
    )
    confidence_limits = _confidence_limits(
        assessment=assessment,
        own_company_name=own_company_name,
        capability=capability,
        has_rising_demand=bool(demands),
    )
    top_change = max((float(signal.change_pct or 0) for signal in demands), default=None)
    return ProductFeatureComparisonRow(
        capability=capability,
        capability_key=capability_key,
        assessment=assessment,
        own_company_name=own_company_name,
        own_status=own_status,
        competitors_with_product_proof=competitors_with_product,
        competitors_with_conversation=competitors_with_conversation,
        has_rising_demand=bool(demands),
        demand_signal_count=len(demands),
        top_demand_change_pct=top_change,
        recommended_action=_recommended_action(
            assessment=assessment,
            own_company_name=own_company_name,
            capability=capability,
        ),
        evidence_urls=evidence_urls,
        confidence_limits=confidence_limits,
    )


def _own_status(
    own_positions: list[FeaturePosition],
    has_competitor_product: bool,
    has_rising_demand: bool,
) -> Literal["unknown", "proven", "claimed", "gap", "disproven"]:
    if any(position.position_status == "proven" for position in own_positions):
        return "proven"
    if any(position.position_status == "disproven" for position in own_positions):
        return "disproven"
    if any(position.position_status == "claimed" for position in own_positions):
        return "claimed"
    if has_competitor_product and has_rising_demand:
        return "gap"
    return "unknown"


def _assessment(
    *,
    own_status: str,
    has_own_conversation: bool,
    competitor_product_count: int,
    competitor_conversation_count: int,
    demand_count: int,
) -> AssessmentKind:
    if competitor_product_count and demand_count and own_status in {"gap", "unknown", "disproven"}:
        return "own_product_gap"
    if competitor_product_count and demand_count and own_status == "proven" and not has_own_conversation:
        return "own_narrative_gap"
    if competitor_product_count and demand_count and own_status == "proven":
        return "competitive_parity"
    if demand_count and not competitor_product_count and own_status not in {"proven", "claimed"}:
        return "demand_without_product_proof"
    if competitor_conversation_count and not competitor_product_count:
        return "conversation_without_product_proof"
    if competitor_product_count and competitor_conversation_count:
        return "competitive_pressure"
    return "watch"


def _recommended_action(*, assessment: str, own_company_name: str, capability: str) -> str:
    if assessment == "own_product_gap":
        return (
            f"Audit whether {own_company_name} has provable {capability}; "
            "if yes, add public product evidence, and if no, open a product gap review."
        )
    if assessment == "own_narrative_gap":
        return f"Create an {own_company_name} narrative for {capability} using existing product proof."
    if assessment == "competitive_parity":
        return f"Use {own_company_name}'s product proof to defend parity on {capability}."
    if assessment == "demand_without_product_proof":
        return f"Find product proof or roadmap context for rising demand around {capability}."
    if assessment == "conversation_without_product_proof":
        return f"Verify whether public conversation around {capability} maps to shipped product evidence."
    return f"Watch {capability} until tenant demand or {own_company_name} response evidence changes."


def _confidence_limits(
    *,
    assessment: str,
    own_company_name: str,
    capability: str,
    has_rising_demand: bool,
) -> list[str]:
    limits: list[str] = []
    if assessment == "own_product_gap":
        limits.append(
            f"Gap means no captured product proof for {own_company_name} on {capability}, not confirmed absence."
        )
    if not has_rising_demand:
        limits.append("No rising tenant-demand signal crossed the action threshold for this capability.")
    return limits


def _row_sort_key(row: ProductFeatureComparisonRow) -> tuple[int, float, str]:
    priority = {
        "own_product_gap": 0,
        "own_narrative_gap": 1,
        "demand_without_product_proof": 2,
        "competitive_pressure": 3,
        "competitive_parity": 4,
        "conversation_without_product_proof": 5,
        "watch": 6,
    }.get(row.assessment, 9)
    return (priority, -(row.top_demand_change_pct or 0.0), row.capability_key)


def _capability_key(value: str) -> str:
    return capability_key(value)


def _evidence_urls(item: Any) -> list[str]:
    return [
        evidence.source_url
        for evidence in getattr(item, "evidence", [])
        if getattr(evidence, "source_url", None)
    ]


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _plural(count: int, singular: str) -> str:
    if count == 1:
        label = singular
    elif singular.endswith("y"):
        label = f"{singular[:-1]}ies"
    else:
        label = f"{singular}s"
    return f"{count} {label}"


def _gap_label(count: int) -> str:
    return "gap" if count == 1 else "gaps"


def _row_label(count: int) -> str:
    return "row" if count == 1 else "rows"


__all__ = [
    "ProductFeatureComparisonRead",
    "ProductFeatureComparisonRow",
    "build_product_feature_comparison_read",
    "derive_feature_positions_from_product_events",
]
