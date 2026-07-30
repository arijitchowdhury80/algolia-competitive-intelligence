"""Hermes-callable runner utilities for product-market intelligence."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, Field

from .argus_packet import ArgusIntelligencePacket, build_argus_packet_from_components
from .capabilities import capability_key, demand_capability_key
from .decision_read import build_argus_decision_read
from .demand_quality import (
    DEMAND_CHANGE_FLOOR,
    DEMAND_VALUE_FLOOR,
    DemandQualityConfig,
    demand_quality_config,
    is_rising_demand_signal,
)
from .feature_matrix import (
    ProductFeatureComparisonRead,
    build_product_feature_comparison_read,
    derive_feature_positions_from_product_events,
)
from .inputs import build_product_market_input_batch
from .market_movement import MarketMovementMap, build_market_movement_map
from .product_market import ProductMarketSynthesizer
from .types import ConversationTheme, DemandSignal, EvidenceRef, ProductChangeEvent, ProductMarketResult, SourceMethod
from .workflow import ProductMarketIntelligenceWorkflow, ProductMarketLedger


_DEMAND_FLOOR = DEMAND_CHANGE_FLOOR
_DEMAND_VALUE_FLOOR = DEMAND_VALUE_FLOOR


class ProductMarketRunPayload(BaseModel):
    tenant_id: int | None = None
    own_company_name: str
    demand_quality: DemandQualityConfig = Field(default_factory=DemandQualityConfig)
    scout_records: list[dict[str, Any]] = Field(default_factory=list)
    conversation_records: list[dict[str, Any]] = Field(default_factory=list)
    looker_rows: list[dict[str, Any]] = Field(default_factory=list)
    learning_instructions: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketConversionDiagnostics(BaseModel):
    """Explains how collector artifacts became, or failed to become, insight.

    This is the missing "muscle trace": counts alone say the chain ran, but
    this object explains where product evidence stopped before becoming a
    pattern or recommendation.
    """

    summary: str = "No product-market conversion diagnostics were produced."
    scout_record_count: int = 0
    product_event_count: int = 0
    conversation_record_count: int = 0
    conversation_theme_count: int = 0
    looker_row_count: int = 0
    demand_signal_count: int = 0
    rising_demand_signal_count: int = 0
    feature_position_count: int = 0
    pattern_count: int = 0
    recommendation_count: int = 0
    product_capability_count: int = 0
    conversation_capability_count: int = 0
    demand_capability_count: int = 0
    matched_capability_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    capability_gaps: list[dict[str, Any]] = Field(default_factory=list)


class ProductMarketDemandRead(BaseModel):
    """Operator-readable interpretation of the inward demand plane.

    Raw GA / Looker rows are plumbing. This read explains which audience
    topics are rising, whether product proof and market conversation matched
    them, and which export evidence backs the read.
    """

    summary: str = "No tenant-side demand evidence was captured."
    demand_signal_count: int = 0
    rising_topic_count: int = 0
    matched_product_topic_count: int = 0
    matched_conversation_topic_count: int = 0
    unmatched_demand_topic_count: int = 0
    top_topics: list[dict[str, Any]] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)


class ProductMarketWindowSlice(BaseModel):
    """Evidence density for one historical window."""

    label: str
    days: int
    product_event_count: int = 0
    conversation_theme_count: int = 0
    demand_signal_count: int = 0
    rising_demand_signal_count: int = 0
    capability_count: int = 0
    leading_companies: list[str] = Field(default_factory=list)
    hot_capabilities: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class ProductMarketWindowComparison(BaseModel):
    """7-day versus 30-day memory read for Argus.

    The cockpit failed when it felt momentary. This artifact lets Hermes and
    the dashboard explain whether this week is an acceleration, a continuation,
    or a quiet subset of the broader month.
    """

    summary: str = "No historical evidence windows were available."
    as_of: datetime | None = None
    windows: list[ProductMarketWindowSlice] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)


class NextMonitoringAction(BaseModel):
    """Machine-readable follow-up instruction for the next Hermes sweep.

    This is the run-native learning bridge. It tells Hermes and Argus what to
    collect, recheck, or remember next instead of leaving the UI to imply an
    operating loop from prose.
    """

    owner: str
    plane: str
    priority: str
    instruction: str
    reason: str
    source_families: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class ProductMarketRunSummary(BaseModel):
    tenant_id: int
    verdict: str
    product_event_count: int
    conversation_theme_count: int
    demand_signal_count: int
    feature_position_count: int
    pattern_count: int
    recommendation_count: int
    demand_quality: dict[str, float] = Field(default_factory=lambda: DemandQualityConfig().model_dump())
    learning_instruction_count: int = 0
    learning_instruction_improvement_ids: list[int] = Field(default_factory=list)
    conversion_diagnostics: ProductMarketConversionDiagnostics = Field(
        default_factory=ProductMarketConversionDiagnostics
    )
    intelligence_brief: "ProductMarketIntelligenceBrief" = Field(
        default_factory=lambda: ProductMarketIntelligenceBrief(
            verdict="quiet",
            top_insight="No product-market run has produced an intelligence brief yet.",
            confidence_limits=["No product-market synthesis result was available."],
        )
    )
    argus_packet: ArgusIntelligencePacket | None = None


class ProductMarketIntelligenceBrief(BaseModel):
    """Brain-readable synthesis artifact for Hermes, dashboard, and learning.

    Counts prove that plumbing ran. This brief carries the actual read: what
    Argus learned, what action it promotes or withholds, which proof supports
    it, and where confidence is constrained.
    """

    verdict: str
    top_insight: str
    primary_action: str | None = None
    watchlist: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    demand_read: dict[str, Any] = Field(default_factory=dict)
    product_feature_comparison: dict[str, Any] = Field(default_factory=dict)
    movement_map: dict[str, Any] = Field(default_factory=dict)
    window_comparison: dict[str, Any] = Field(default_factory=dict)
    conversion_diagnostics: dict[str, Any] = Field(default_factory=dict)
    demand_recommendation_trace: dict[str, Any] = Field(default_factory=dict)
    decision_read: dict[str, Any] = Field(default_factory=dict)
    next_monitoring_actions: list[NextMonitoringAction] = Field(default_factory=list)


def load_product_market_payload(path: Path) -> ProductMarketRunPayload:
    return ProductMarketRunPayload.model_validate(json.loads(path.read_text(encoding="utf-8")))


def run_product_market_payload(
    payload: ProductMarketRunPayload,
    *,
    repository: ProductMarketLedger,
) -> ProductMarketRunSummary:
    if payload.tenant_id is None:
        raise ValueError("Product-market payload requires tenant_id before execution")
    batch = build_product_market_input_batch(
        tenant_id=payload.tenant_id,
        scout_records=payload.scout_records,
        conversation_records=payload.conversation_records,
        looker_rows=payload.looker_rows,
    )
    quality = demand_quality_config(payload.demand_quality)
    workflow = ProductMarketIntelligenceWorkflow(repository=repository)
    result: ProductMarketResult = workflow.run(
        tenant_id=payload.tenant_id,
        own_company_name=payload.own_company_name,
        product_events=batch.product_events,
        conversation_themes=batch.conversation_themes,
        demand_signals=batch.demand_signals,
        demand_quality=quality,
        learning_instructions=payload.learning_instructions,
    )
    feature_positions = derive_feature_positions_from_product_events(batch.product_events)
    learning_instruction_improvement_ids = sorted(
        {
            int(improvement_id)
            for instruction in payload.learning_instructions
            for improvement_id in instruction.get("source_improvement_ids", [])
            if improvement_id is not None
        }
    )
    evidence_as_of = _product_market_evidence_as_of(
        product_events=batch.product_events,
        conversation_themes=batch.conversation_themes,
        demand_signals=batch.demand_signals,
    )
    movement_map = build_market_movement_map(
        current_patterns=result.patterns,
        historical_patterns=_load_pattern_history(repository, payload.tenant_id),
        as_of=evidence_as_of,
    )
    conversion_diagnostics = build_product_market_conversion_diagnostics(
        scout_record_count=len(payload.scout_records),
        conversation_record_count=len(payload.conversation_records),
        looker_row_count=len(payload.looker_rows),
        product_events=batch.product_events,
        conversation_themes=batch.conversation_themes,
        demand_signals=batch.demand_signals,
        feature_position_count=len(feature_positions),
        pattern_count=len(result.patterns),
        recommendation_count=len(result.recommendations),
        demand_quality=quality,
    )
    demand_read = build_product_market_demand_read(
        product_events=batch.product_events,
        conversation_themes=batch.conversation_themes,
        demand_signals=batch.demand_signals,
        demand_quality=quality,
    )
    product_feature_comparison = build_product_feature_comparison_read(
        own_company_name=payload.own_company_name,
        product_events=batch.product_events,
        conversation_themes=batch.conversation_themes,
        demand_signals=batch.demand_signals,
        demand_quality=quality,
    )
    window_comparison = build_product_market_window_comparison(
        product_events=batch.product_events,
        conversation_themes=batch.conversation_themes,
        demand_signals=batch.demand_signals,
        demand_quality=quality,
    )
    demand_recommendation_trace = build_demand_recommendation_trace(
        demand_signals=batch.demand_signals,
        patterns=result.patterns,
        recommendations=result.recommendations,
        demand_quality=quality,
    )
    intelligence_brief = build_product_market_intelligence_brief(
        result,
        product_event_count=len(batch.product_events),
        conversation_theme_count=len(batch.conversation_themes),
        demand_signal_count=len(batch.demand_signals),
        learning_instruction_count=len(payload.learning_instructions),
        demand_read=demand_read,
        product_feature_comparison=product_feature_comparison,
        movement_map=movement_map,
        window_comparison=window_comparison,
        conversion_diagnostics=conversion_diagnostics,
        demand_recommendation_trace=demand_recommendation_trace,
    )
    summary = ProductMarketRunSummary(
        tenant_id=payload.tenant_id,
        verdict=result.verdict,
        product_event_count=len(batch.product_events),
        conversation_theme_count=len(batch.conversation_themes),
        demand_signal_count=len(batch.demand_signals),
        feature_position_count=len(feature_positions),
        pattern_count=len(result.patterns),
        recommendation_count=len(result.recommendations),
        demand_quality=quality.model_dump(),
        learning_instruction_count=len(payload.learning_instructions),
        learning_instruction_improvement_ids=learning_instruction_improvement_ids,
        conversion_diagnostics=conversion_diagnostics,
        intelligence_brief=intelligence_brief,
    )
    summary.argus_packet = _build_argus_packet_for_product_market_summary(
        summary,
        own_company_name=payload.own_company_name,
        result=result,
        evidence_as_of=evidence_as_of,
    )
    save_run_intelligence_summary = getattr(repository, "save_run_intelligence_summary", None)
    if callable(save_run_intelligence_summary):
        save_run_intelligence_summary(summary)
    return summary


def run_product_market_ledger_refresh(
    *,
    tenant_id: int,
    own_company_name: str,
    repository: ProductMarketLedger,
    days: int = 30,
    limit: int = 500,
    learning_instructions: list[Mapping[str, Any]] | None = None,
    demand_quality: DemandQualityConfig | Mapping[str, Any] | None = None,
) -> ProductMarketRunSummary:
    """Replay persisted evidence ledgers into a fresh Argus read.

    This is the demand-refresh path: when the inward plane changes, Argus can
    re-synthesize against already stored product and conversation evidence
    without duplicating the source ledgers.
    """

    product_rows = _call_recent_ledger_reader(
        repository,
        "get_recent_product_events",
        tenant_id=tenant_id,
        days=days,
        limit=limit,
    )
    conversation_rows = _call_recent_ledger_reader(
        repository,
        "get_recent_conversation_themes",
        tenant_id=tenant_id,
        days=days,
        limit=limit,
    )
    demand_rows = _call_recent_ledger_reader(
        repository,
        "get_recent_demand_signals",
        tenant_id=tenant_id,
        days=days,
        limit=limit,
    )
    product_events = [_product_event_from_row(row, tenant_id=tenant_id) for row in product_rows]
    conversation_themes = [
        _conversation_theme_from_row(row, tenant_id=tenant_id) for row in conversation_rows
    ]
    demand_signals = [_demand_signal_from_row(row, tenant_id=tenant_id) for row in demand_rows]
    quality = demand_quality_config(demand_quality)

    ProductMarketIntelligenceWorkflow._validate_tenant_scope(
        tenant_id=tenant_id,
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
    )
    result = ProductMarketSynthesizer(
        demand_floor=quality.change_floor,
        demand_value_floor=quality.value_floor,
    ).synthesize(
        tenant_id=tenant_id,
        own_company_name=own_company_name,
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
    )
    result = ProductMarketIntelligenceWorkflow._apply_learning_instructions(
        result,
        list(learning_instructions or []),
    )
    pattern_ids = [repository.save_pattern_observation(pattern) for pattern in result.patterns]
    for idx, recommendation in enumerate(result.recommendations):
        pattern_observation_id = pattern_ids[min(idx, len(pattern_ids) - 1)] if pattern_ids else None
        repository.save_recommendation(
            recommendation,
            pattern_observation_id=pattern_observation_id,
        )

    feature_positions = derive_feature_positions_from_product_events(product_events)
    evidence_as_of = _product_market_evidence_as_of(
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
    )
    movement_map = build_market_movement_map(
        current_patterns=result.patterns,
        historical_patterns=_load_pattern_history(repository, tenant_id),
        as_of=evidence_as_of,
    )
    conversion_diagnostics = build_product_market_conversion_diagnostics(
        scout_record_count=len(product_events),
        conversation_record_count=len(conversation_themes),
        looker_row_count=len(demand_signals),
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
        feature_position_count=len(feature_positions),
        pattern_count=len(result.patterns),
        recommendation_count=len(result.recommendations),
        demand_quality=quality,
    )
    demand_read = build_product_market_demand_read(
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
        demand_quality=quality,
    )
    product_feature_comparison = build_product_feature_comparison_read(
        own_company_name=own_company_name,
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
        demand_quality=quality,
    )
    window_comparison = build_product_market_window_comparison(
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
        demand_quality=quality,
    )
    demand_recommendation_trace = build_demand_recommendation_trace(
        demand_signals=demand_signals,
        patterns=result.patterns,
        recommendations=result.recommendations,
        demand_quality=quality,
    )
    instructions = list(learning_instructions or [])
    intelligence_brief = build_product_market_intelligence_brief(
        result,
        product_event_count=len(product_events),
        conversation_theme_count=len(conversation_themes),
        demand_signal_count=len(demand_signals),
        learning_instruction_count=len(instructions),
        demand_read=demand_read,
        product_feature_comparison=product_feature_comparison,
        movement_map=movement_map,
        window_comparison=window_comparison,
        conversion_diagnostics=conversion_diagnostics,
        demand_recommendation_trace=demand_recommendation_trace,
    )
    summary = ProductMarketRunSummary(
        tenant_id=tenant_id,
        verdict=result.verdict,
        product_event_count=len(product_events),
        conversation_theme_count=len(conversation_themes),
        demand_signal_count=len(demand_signals),
        feature_position_count=len(feature_positions),
        pattern_count=len(result.patterns),
        recommendation_count=len(result.recommendations),
        demand_quality=quality.model_dump(),
        learning_instruction_count=len(instructions),
        learning_instruction_improvement_ids=_learning_instruction_improvement_ids(instructions),
        conversion_diagnostics=conversion_diagnostics,
        intelligence_brief=intelligence_brief,
    )
    summary.argus_packet = _build_argus_packet_for_product_market_summary(
        summary,
        own_company_name=own_company_name,
        result=result,
        evidence_as_of=evidence_as_of,
    )
    save_run_intelligence_summary = getattr(repository, "save_run_intelligence_summary", None)
    if callable(save_run_intelligence_summary):
        save_run_intelligence_summary(summary)
    return summary


def _call_recent_ledger_reader(
    repository: ProductMarketLedger,
    method_name: str,
    *,
    tenant_id: int,
    days: int,
    limit: int,
) -> list[dict[str, Any]]:
    reader = getattr(repository, method_name, None)
    if not callable(reader):
        raise AttributeError(f"repository must implement {method_name} for ledger refresh")
    return [dict(row) for row in reader(tenant_id, days=days, limit=limit)]


def _learning_instruction_improvement_ids(instructions: list[Mapping[str, Any]]) -> list[int]:
    return sorted(
        {
            int(improvement_id)
            for instruction in instructions
            for improvement_id in instruction.get("source_improvement_ids", [])
            if improvement_id is not None
        }
    )


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ValueError(f"expected datetime-compatible value, got {type(value).__name__}")


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    if isinstance(value, list):
        return value
    return []


def _evidence_refs_from_row(
    row: Mapping[str, Any],
    *,
    fallback_captured_at: Any,
    fallback_method: SourceMethod,
) -> list[EvidenceRef]:
    evidence: list[EvidenceRef] = []
    for item in _json_list(row.get("evidence_refs")):
        if not isinstance(item, Mapping):
            continue
        data = dict(item)
        data.setdefault("captured_at", fallback_captured_at)
        data.setdefault("method", fallback_method.value)
        evidence.append(EvidenceRef.model_validate(data))
    return evidence


def _product_event_from_row(row: Mapping[str, Any], *, tenant_id: int) -> ProductChangeEvent:
    competitor_id = _int_or_none(row.get("competitor_id"))
    observed_at = _dt(row["observed_at"])
    return ProductChangeEvent(
        tenant_id=int(row.get("tenant_id") or tenant_id),
        company_id=competitor_id if competitor_id is not None else 0,
        company_name=str(row["company_name"]),
        company_role=str(row.get("company_role") or "competitor"),  # type: ignore[arg-type]
        capability=str(row["capability_text"]),
        change_type=str(row["change_type"]),  # type: ignore[arg-type]
        summary=str(row["summary"]),
        observed_at=observed_at,
        evidence=_evidence_refs_from_row(
            row,
            fallback_captured_at=observed_at,
            fallback_method=SourceMethod.SCOUT_CHANGELOG,
        ),
    )


def _conversation_theme_from_row(row: Mapping[str, Any], *, tenant_id: int) -> ConversationTheme:
    observed_at = _dt(row["observed_at"])
    return ConversationTheme(
        tenant_id=int(row.get("tenant_id") or tenant_id),
        company_id=_int_or_none(row.get("competitor_id")),
        company_name=None if row.get("company_name") in (None, "") else str(row.get("company_name")),
        theme=str(row["theme"]),
        summary=str(row["summary"]),
        intensity=float(row.get("intensity", 0.5)),
        observed_at=observed_at,
        evidence=_evidence_refs_from_row(
            row,
            fallback_captured_at=observed_at,
            fallback_method=SourceMethod.WEB_SCAN,
        ),
    )


def _demand_signal_from_row(row: Mapping[str, Any], *, tenant_id: int) -> DemandSignal:
    period_end = _dt(row["period_end"])
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    return DemandSignal(
        tenant_id=int(row.get("tenant_id") or tenant_id),
        topic=str(row["topic"]),
        metric=str(row["metric"]),
        value=float(row["value"]),
        change_pct=_float_or_none(row.get("change_pct")),
        period_start=_dt(row["period_start"]),
        period_end=period_end,
        source_label=str(row["source_label"]),
        evidence=_evidence_refs_from_row(
            row,
            fallback_captured_at=period_end,
            fallback_method=SourceMethod.LOOKER_EXPORT,
        ),
        metadata=dict(metadata),
    )


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _load_pattern_history(repository: ProductMarketLedger, tenant_id: int) -> list[dict[str, Any]]:
    get_pattern_history = getattr(repository, "get_pattern_history", None)
    if not callable(get_pattern_history):
        return []
    rows = get_pattern_history(tenant_id, days=30, limit=100)
    return [dict(row) for row in rows]


def _capability_key(value: str) -> str:
    return capability_key(value)


def _demand_capability_key(signal: Any) -> str:
    return demand_capability_key(
        getattr(signal, "topic", ""),
        getattr(signal, "metadata", {}),
    )


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    label = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {label}"


def build_product_market_conversion_diagnostics(
    *,
    scout_record_count: int,
    conversation_record_count: int,
    looker_row_count: int,
    product_events: list[Any],
    conversation_themes: list[Any],
    demand_signals: list[Any],
    feature_position_count: int,
    pattern_count: int,
    recommendation_count: int,
    demand_quality: DemandQualityConfig | Mapping[str, Any] | None = None,
) -> ProductMarketConversionDiagnostics:
    quality = demand_quality_config(demand_quality)
    product_caps = {_capability_key(event.capability) for event in product_events if _capability_key(event.capability)}
    conversation_caps = {
        _capability_key(theme.theme) for theme in conversation_themes if _capability_key(theme.theme)
    }
    rising_demand = [
        signal
        for signal in demand_signals
        if is_rising_demand_signal(
            signal,
            change_floor=quality.change_floor,
            value_floor=quality.value_floor,
        )
    ]
    demand_caps = {_demand_capability_key(signal) for signal in rising_demand if _demand_capability_key(signal)}
    matched_caps = product_caps & demand_caps

    capability_gaps: list[dict[str, Any]] = []
    blockers: list[str] = []

    product_without_demand = sorted(product_caps - demand_caps)
    if product_events and not demand_signals:
        blockers.append("No tenant-side demand evidence was captured, so product proof could not become a product-market pattern.")
    if product_without_demand:
        blockers.append(
            f"{_plural(len(product_without_demand), 'product capability', 'product capabilities')} "
            "had product proof but no rising demand signal."
        )
        for capability in product_without_demand[:10]:
            capability_gaps.append(
                {
                    "capability": capability,
                    "has_product_proof": True,
                    "has_market_conversation": capability in conversation_caps,
                    "has_rising_demand": False,
                    "missing_planes": ["rising_demand"],
                }
            )

    demand_without_product = sorted(demand_caps - product_caps)
    if demand_without_product:
        blockers.append(
            f"{_plural(len(demand_without_product), 'rising demand capability', 'rising demand capabilities')} "
            "had demand but no product proof."
        )
        for capability in demand_without_product[:10]:
            capability_gaps.append(
                {
                    "capability": capability,
                    "has_product_proof": False,
                    "has_market_conversation": capability in conversation_caps,
                    "has_rising_demand": True,
                    "missing_planes": ["product_proof"],
                }
            )

    if product_events and not conversation_themes:
        blockers.append("No market-conversation evidence was captured for the product artifacts in this run.")
    if pattern_count == 0 and product_events:
        blockers.append(
            "Product artifacts did not become patterns because each capability was missing at least one required evidence plane."
        )

    summary = (
        f"{_plural(scout_record_count, 'Scout/product record')} converted to "
        f"{_plural(len(product_events), 'product event')} and "
        f"{_plural(feature_position_count, 'feature position')}; "
        f"{_plural(pattern_count, 'product-market pattern')} qualified."
    )

    return ProductMarketConversionDiagnostics(
        summary=summary,
        scout_record_count=scout_record_count,
        product_event_count=len(product_events),
        conversation_record_count=conversation_record_count,
        conversation_theme_count=len(conversation_themes),
        looker_row_count=looker_row_count,
        demand_signal_count=len(demand_signals),
        rising_demand_signal_count=len(rising_demand),
        feature_position_count=feature_position_count,
        pattern_count=pattern_count,
        recommendation_count=recommendation_count,
        product_capability_count=len(product_caps),
        conversation_capability_count=len(conversation_caps),
        demand_capability_count=len(demand_caps),
        matched_capability_count=len(matched_caps),
        blockers=blockers,
        capability_gaps=capability_gaps,
    )


def build_product_market_demand_read(
    *,
    product_events: list[Any],
    conversation_themes: list[Any],
    demand_signals: list[Any],
    demand_quality: DemandQualityConfig | Mapping[str, Any] | None = None,
) -> ProductMarketDemandRead:
    quality = demand_quality_config(demand_quality)
    product_caps = {_capability_key(event.capability) for event in product_events if _capability_key(event.capability)}
    conversation_caps = {
        _capability_key(theme.theme) for theme in conversation_themes if _capability_key(theme.theme)
    }
    source_files = sorted(
        {
            str(getattr(signal, "metadata", {}).get("source_file"))
            for signal in demand_signals
            if getattr(signal, "metadata", {}).get("source_file")
        }
    )
    evidence_urls = _dedupe_urls(
        [evidence.source_url for signal in demand_signals for evidence in getattr(signal, "evidence", [])]
    )

    if not demand_signals:
        return ProductMarketDemandRead(
            source_files=source_files,
            evidence_urls=evidence_urls,
            confidence_limits=["Upload GA / Looker demand evidence before promoting demand-backed recommendations."],
        )

    rising_by_capability: dict[str, list[Any]] = defaultdict(list)
    for signal in demand_signals:
        if not is_rising_demand_signal(
            signal,
            change_floor=quality.change_floor,
            value_floor=quality.value_floor,
        ):
            continue
        key = _demand_capability_key(signal)
        if key:
            rising_by_capability[key].append(signal)

    if not rising_by_capability:
        return ProductMarketDemandRead(
            summary=(
                f"{_plural(len(demand_signals), 'demand signal')} captured, but none crossed "
                "the rising-demand threshold."
            ),
            demand_signal_count=len(demand_signals),
            source_files=source_files,
            evidence_urls=evidence_urls,
            confidence_limits=["Demand evidence exists, but no topic cleared the rising-demand threshold."],
        )

    topic_rows: list[dict[str, Any]] = []
    for key, signals in rising_by_capability.items():
        ranked_signals = sorted(
            signals,
            key=lambda signal: (
                -(signal.change_pct if signal.change_pct is not None else -1.0),
                -float(signal.value),
                str(signal.topic).lower(),
            ),
        )
        top_signal = ranked_signals[0]
        matched_product = key in product_caps
        matched_conversation = key in conversation_caps
        missing_planes = []
        if not matched_product:
            missing_planes.append("product_proof")
        if not matched_conversation:
            missing_planes.append("market_conversation")
        row_evidence_urls = _dedupe_urls(
            [evidence.source_url for signal in ranked_signals for evidence in getattr(signal, "evidence", [])]
        )
        row_source_files = sorted(
            {
                str(getattr(signal, "metadata", {}).get("source_file"))
                for signal in ranked_signals
                if getattr(signal, "metadata", {}).get("source_file")
            }
        )
        row_source_numbers = sorted(
            {
                int(getattr(signal, "metadata", {}).get("source_row_number"))
                for signal in ranked_signals
                if getattr(signal, "metadata", {}).get("source_row_number") not in (None, "")
            }
        )
        topic_rows.append(
            {
                "topic": top_signal.topic,
                "capability_key": key,
                "metric": top_signal.metric,
                "value": top_signal.value,
                "change_pct": top_signal.change_pct,
                "matched_product_proof": matched_product,
                "matched_market_conversation": matched_conversation,
                "missing_planes": missing_planes,
                "signal_count": len(ranked_signals),
                "source_files": row_source_files,
                "source_row_numbers": row_source_numbers,
                "evidence_urls": row_evidence_urls,
            }
        )

    topic_rows.sort(
        key=lambda row: (
            -(float(row["change_pct"]) if row.get("change_pct") is not None else -1.0),
            -float(row["value"]),
            str(row["topic"]).lower(),
        )
    )
    matched_product_count = sum(1 for row in topic_rows if row["matched_product_proof"])
    matched_conversation_count = sum(1 for row in topic_rows if row["matched_market_conversation"])
    unmatched_count = len(topic_rows) - matched_product_count
    ranked_evidence_urls = _dedupe_urls(
        [url for row in topic_rows for url in row.get("evidence_urls", [])]
    )
    confidence_limits = []
    if unmatched_count:
        confidence_limits.append(
            f"{_plural(unmatched_count, 'rising demand topic')} still needs product proof before Argus can turn it into a confident action."
        )
    if matched_product_count and matched_product_count != len(topic_rows):
        confidence_limits.append(
            "Demand is partially matched: Argus should separate proven opportunities from product gaps."
        )

    return ProductMarketDemandRead(
        summary=(
            f"{_plural(len(topic_rows), 'rising demand topic')} found; "
            f"{matched_product_count} matched product proof and {unmatched_count} still "
            f"{'needs' if unmatched_count == 1 else 'need'} product proof."
        ),
        demand_signal_count=len(demand_signals),
        rising_topic_count=len(topic_rows),
        matched_product_topic_count=matched_product_count,
        matched_conversation_topic_count=matched_conversation_count,
        unmatched_demand_topic_count=unmatched_count,
        top_topics=topic_rows[:10],
        source_files=source_files,
        evidence_urls=ranked_evidence_urls,
        confidence_limits=confidence_limits,
    )


def build_demand_recommendation_trace(
    *,
    demand_signals: list[Any],
    patterns: list[Any],
    recommendations: list[Any],
    demand_quality: DemandQualityConfig | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain how inward demand evidence did or did not change action.

    This is the bridge between plumbing and intelligence: it preserves the
    joins from GA / Looker demand rows into qualified patterns,
    recommendation actions, and scorecard dimensions.
    """

    rising_by_capability: dict[str, list[Any]] = defaultdict(list)
    quality = demand_quality_config(demand_quality)
    for signal in demand_signals:
        if not is_rising_demand_signal(
            signal,
            change_floor=quality.change_floor,
            value_floor=quality.value_floor,
        ):
            continue
        key = _demand_capability_key(signal)
        if key:
            rising_by_capability[key].append(signal)

    if not demand_signals:
        return {
            "status": "no_demand_evidence",
            "demand_signal_count": 0,
            "rising_demand_topic_count": 0,
            "matched_demand_topic_count": 0,
            "pattern_count": len(patterns),
            "recommendation_count": len(recommendations),
            "demand_topics": [],
            "evidence_urls": [],
            "confidence_limits": [
                "No tenant-side demand evidence was available, so Argus could not prove audience pull."
            ],
        }

    if not rising_by_capability:
        return {
            "status": "no_rising_demand",
            "demand_signal_count": len(demand_signals),
            "rising_demand_topic_count": 0,
            "matched_demand_topic_count": 0,
            "pattern_count": len(patterns),
            "recommendation_count": len(recommendations),
            "demand_topics": [],
            "evidence_urls": _dedupe_urls(
                [url for signal in demand_signals for url in _item_evidence_urls(signal)]
            ),
            "confidence_limits": [
                "Demand evidence exists, but no topic crossed the rising-demand threshold."
            ],
        }

    topic_rows: list[dict[str, Any]] = []
    all_evidence_urls: list[str] = []
    for key, signals in rising_by_capability.items():
        ranked_signals = sorted(
            signals,
            key=lambda signal: (
                -(signal.change_pct if signal.change_pct is not None else -1.0),
                -float(signal.value),
                str(signal.topic).lower(),
            ),
        )
        top_signal = ranked_signals[0]
        signal_evidence_urls = _dedupe_urls(
            [url for signal in ranked_signals for url in _item_evidence_urls(signal)]
        )
        matching_patterns = [
            pattern for pattern in patterns if _item_matches_demand_key(pattern, key, signal_evidence_urls)
        ]
        matching_recommendations = [
            recommendation
            for recommendation in recommendations
            if _item_matches_demand_key(recommendation, key, signal_evidence_urls)
            or _recommendation_scorecard_matches(recommendation, signal_evidence_urls)
        ]
        scorecard_dimensions = _scorecard_dimensions_for_demand(
            matching_recommendations,
            signal_evidence_urls,
        )
        pattern_evidence_urls = _dedupe_urls(
            [url for pattern in matching_patterns for url in _item_evidence_urls(pattern)]
        )
        recommendation_evidence_urls = _dedupe_urls(
            [
                url
                for recommendation in matching_recommendations
                for url in _item_evidence_urls(recommendation)
            ]
        )
        row_evidence_urls = _dedupe_urls(
            [*signal_evidence_urls, *pattern_evidence_urls, *recommendation_evidence_urls]
        )
        source_files = sorted(
            {
                str(getattr(signal, "metadata", {}).get("source_file"))
                for signal in ranked_signals
                if getattr(signal, "metadata", {}).get("source_file")
            }
        )
        source_row_numbers = sorted(
            {
                int(getattr(signal, "metadata", {}).get("source_row_number"))
                for signal in ranked_signals
                if getattr(signal, "metadata", {}).get("source_row_number") not in (None, "")
            }
        )
        topic_rows.append(
            {
                "topic": top_signal.topic,
                "capability_key": key,
                "metric": top_signal.metric,
                "value": top_signal.value,
                "change_pct": top_signal.change_pct,
                "signal_count": len(ranked_signals),
                "source_files": source_files,
                "source_row_numbers": source_row_numbers,
                "pattern_summaries": [
                    str(getattr(pattern, "summary", ""))
                    for pattern in matching_patterns
                    if str(getattr(pattern, "summary", "")).strip()
                ],
                "recommendation_actions": [
                    str(getattr(recommendation, "action", ""))
                    for recommendation in matching_recommendations
                    if str(getattr(recommendation, "action", "")).strip()
                ],
                "scorecard_dimensions": scorecard_dimensions,
                "evidence_urls": signal_evidence_urls,
                "linked_evidence_urls": row_evidence_urls,
            }
        )
        all_evidence_urls.extend(row_evidence_urls)

    topic_rows.sort(
        key=lambda row: (
            -len(row.get("recommendation_actions") or []),
            -len(row.get("pattern_summaries") or []),
            -(float(row["change_pct"]) if row.get("change_pct") is not None else -1.0),
            -float(row["value"]),
            str(row["topic"]).lower(),
        )
    )
    matched_demand_topic_count = sum(1 for row in topic_rows if row["recommendation_actions"])
    pattern_linked_count = sum(1 for row in topic_rows if row["pattern_summaries"])

    if matched_demand_topic_count:
        status = "linked_to_recommendations"
    elif pattern_linked_count:
        status = "linked_to_patterns"
    else:
        status = "unlinked_demand"

    confidence_limits: list[str] = []
    unlinked_count = len(topic_rows) - matched_demand_topic_count
    if unlinked_count:
        confidence_limits.append(
            f"{_plural(unlinked_count, 'rising demand topic')} did not link to a recommendation."
        )
    if matched_demand_topic_count and matched_demand_topic_count != len(topic_rows):
        confidence_limits.append(
            "Argus linked only part of the demand plane to actions; unmatched demand should stay in watch mode."
        )

    return {
        "status": status,
        "demand_signal_count": len(demand_signals),
        "rising_demand_topic_count": len(topic_rows),
        "matched_demand_topic_count": matched_demand_topic_count,
        "pattern_count": len(patterns),
        "recommendation_count": len(recommendations),
        "demand_topics": topic_rows,
        "evidence_urls": _dedupe_urls(all_evidence_urls),
        "confidence_limits": confidence_limits,
    }


def _item_matches_demand_key(item: Any, key: str, signal_evidence_urls: list[str]) -> bool:
    label = str(getattr(item, "capability", "") or getattr(item, "action", "") or "")
    if _capability_key(label) == key:
        return True
    return bool(set(_item_evidence_urls(item)) & set(signal_evidence_urls))


def _recommendation_scorecard_matches(recommendation: Any, signal_evidence_urls: list[str]) -> bool:
    signal_urls = set(signal_evidence_urls)
    for dimension in getattr(getattr(recommendation, "scorecard", None), "dimension_scores", []) or []:
        if signal_urls & set(getattr(dimension, "evidence_urls", []) or []):
            return True
    return False


def _scorecard_dimensions_for_demand(
    recommendations: list[Any],
    signal_evidence_urls: list[str],
) -> list[str]:
    signal_urls = set(signal_evidence_urls)
    dimensions: list[str] = []
    for recommendation in recommendations:
        for dimension in getattr(getattr(recommendation, "scorecard", None), "dimension_scores", []) or []:
            if not signal_urls & set(getattr(dimension, "evidence_urls", []) or []):
                continue
            name = str(getattr(dimension, "dimension", "") or "")
            if name and name not in dimensions:
                dimensions.append(name)
    return dimensions


def build_product_market_window_comparison(
    *,
    product_events: list[Any],
    conversation_themes: list[Any],
    demand_signals: list[Any],
    windows: tuple[int, ...] = (7, 30),
    demand_quality: DemandQualityConfig | Mapping[str, Any] | None = None,
) -> ProductMarketWindowComparison:
    """Compare recent evidence density across fixed memory windows."""

    timestamps = [
        timestamp
        for timestamp in [
            *(_evidence_timestamp(event, "observed_at") for event in product_events),
            *(_evidence_timestamp(theme, "observed_at") for theme in conversation_themes),
            *(_evidence_timestamp(signal, "period_end") for signal in demand_signals),
        ]
        if timestamp is not None
    ]
    if not timestamps:
        return ProductMarketWindowComparison(
            confidence_limits=["No product, conversation, or demand evidence exists for historical comparison."]
        )

    as_of = max(timestamps)
    slices = [
        _build_window_slice(
            days=days,
            as_of=as_of,
            product_events=product_events,
            conversation_themes=conversation_themes,
            demand_signals=demand_signals,
            demand_quality=demand_quality,
        )
        for days in windows
    ]
    summary = ". ".join(
        (
            f"Last {window.days} days: "
            f"{_plural(window.product_event_count, 'product event')}, "
            f"{_plural(window.conversation_theme_count, 'conversation theme')}, "
            f"{_plural(window.demand_signal_count, 'demand signal')}"
        )
        for window in slices
    )
    if summary:
        summary = f"{summary}."
    confidence_limits: list[str] = []
    if any(window.demand_signal_count == 0 for window in slices):
        confidence_limits.append("One or more historical windows has no tenant-side demand evidence.")
    if len(slices) >= 2 and slices[0].product_event_count == 0 and slices[-1].product_event_count > 0:
        confidence_limits.append("Recent window is quieter than the broader historical window.")
    return ProductMarketWindowComparison(
        summary=summary,
        as_of=as_of,
        windows=slices,
        confidence_limits=confidence_limits,
    )


def _build_window_slice(
    *,
    days: int,
    as_of: datetime,
    product_events: list[Any],
    conversation_themes: list[Any],
    demand_signals: list[Any],
    demand_quality: DemandQualityConfig | Mapping[str, Any] | None = None,
) -> ProductMarketWindowSlice:
    cutoff = as_of - timedelta(days=days)
    products = [
        event
        for event in product_events
        if (timestamp := _evidence_timestamp(event, "observed_at")) is not None and timestamp >= cutoff
    ]
    conversations = [
        theme
        for theme in conversation_themes
        if (timestamp := _evidence_timestamp(theme, "observed_at")) is not None and timestamp >= cutoff
    ]
    demand = [
        signal
        for signal in demand_signals
        if (timestamp := _evidence_timestamp(signal, "period_end")) is not None and timestamp >= cutoff
    ]

    company_counts: dict[str, int] = defaultdict(int)
    capability_counts: dict[str, int] = defaultdict(int)
    capability_labels: dict[str, str] = {}
    evidence_urls: list[str] = []

    for event in products:
        company = str(getattr(event, "company_name", "") or "").strip()
        if company:
            company_counts[company] += 1
        label = str(getattr(event, "capability", "") or "").strip()
        key = _capability_key(label)
        if key:
            capability_counts[key] += 1
            capability_labels.setdefault(key, label or key)
        evidence_urls.extend(_item_evidence_urls(event))

    for theme in conversations:
        company = str(getattr(theme, "company_name", "") or "").strip()
        if company:
            company_counts[company] += 1
        label = str(getattr(theme, "theme", "") or "").strip()
        key = _capability_key(label)
        if key:
            capability_counts[key] += 1
            capability_labels.setdefault(key, label or key)
        evidence_urls.extend(_item_evidence_urls(theme))

    rising_demand_count = 0
    quality = demand_quality_config(demand_quality)
    for signal in demand:
        label = str(getattr(signal, "topic", "") or "").strip()
        key = _capability_key(label)
        if is_rising_demand_signal(
            signal,
            change_floor=quality.change_floor,
            value_floor=quality.value_floor,
        ):
            rising_demand_count += 1
            if key:
                capability_counts[key] += 1
                capability_labels.setdefault(key, label or key)
        evidence_urls.extend(_item_evidence_urls(signal))

    leading_companies = [
        company
        for company, _count in sorted(
            company_counts.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )[:10]
    ]
    hot_capabilities = [
        capability_labels.get(capability, capability)
        for capability, _count in sorted(
            capability_counts.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )[:10]
    ]

    return ProductMarketWindowSlice(
        label=f"last_{days}_days",
        days=days,
        product_event_count=len(products),
        conversation_theme_count=len(conversations),
        demand_signal_count=len(demand),
        rising_demand_signal_count=rising_demand_count,
        capability_count=len(capability_counts),
        leading_companies=leading_companies,
        hot_capabilities=hot_capabilities,
        evidence_urls=_dedupe_urls(evidence_urls),
    )


def _evidence_timestamp(item: Any, field_name: str) -> datetime | None:
    value = getattr(item, field_name, None)
    if value in (None, ""):
        return None
    try:
        return _dt(value)
    except (TypeError, ValueError):
        return None


def _product_market_evidence_as_of(
    *,
    product_events: list[Any],
    conversation_themes: list[Any],
    demand_signals: list[Any],
) -> datetime | None:
    timestamps = [
        timestamp
        for timestamp in [
            *(_evidence_timestamp(event, "observed_at") for event in product_events),
            *(_evidence_timestamp(theme, "observed_at") for theme in conversation_themes),
            *(_evidence_timestamp(signal, "period_end") for signal in demand_signals),
        ]
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None


def _item_evidence_urls(item: Any) -> list[str]:
    return [
        str(getattr(evidence, "source_url", "") or "")
        for evidence in getattr(item, "evidence", [])
        if getattr(evidence, "source_url", None)
    ]


def _build_argus_packet_for_product_market_summary(
    summary: ProductMarketRunSummary,
    *,
    own_company_name: str,
    result: ProductMarketResult,
    evidence_as_of: datetime | None,
) -> ArgusIntelligencePacket:
    generated_at = evidence_as_of or datetime.now(timezone.utc)
    run_stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"product-market-local-tenant-{summary.tenant_id}-{run_stamp}"
    total_checked = (
        summary.product_event_count
        + summary.conversation_theme_count
        + summary.demand_signal_count
    )
    return build_argus_packet_from_components(
        tenant={
            "tenant_id": summary.tenant_id,
            "slug": _tenant_slug(own_company_name),
            "display_name": own_company_name,
        },
        run={
            "run_id": run_id,
            "generated_at": generated_at,
            "started_at": generated_at,
            "completed_at": generated_at,
            "hermes_profile": "argus",
            "package_commit": "local",
            "package_release_id": f"local-{run_stamp}",
            "produced_by_user": "cios",
            "source": "local_test",
        },
        cadence="daily",
        time_window={
            "label": "today",
            "start_at": generated_at - timedelta(days=1),
            "end_at": generated_at,
            "grain": "daily",
            "movement_basis": "local product-market evidence window",
        },
        intelligence_brief=summary.intelligence_brief.model_dump(mode="json"),
        decision_read=summary.intelligence_brief.decision_read,
        movement_map=summary.intelligence_brief.movement_map,
        recommendations=_packet_recommendation_rows(result.recommendations),
        source_health={
            "active": total_checked,
            "checked": total_checked,
            "failed": 0,
            "stale": 0,
            "confidence_impact": "local product-market evidence was converted into a canonical packet",
        },
        consumer_state=_packet_consumer_state(run_id=run_id),
    )


def _tenant_slug(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "tenant"


def _packet_consumer_state(*, run_id: str) -> dict[str, dict[str, Any]]:
    return {
        "telegram_daily": {"status": "skipped", "run_id": run_id},
        "telegram_weekly": {"status": "not_applicable", "run_id": run_id},
        "dashboard": {"status": "rendered", "run_id": run_id},
        "market_field": {"status": "rendered", "run_id": run_id},
        "evidence_lab": {"status": "rendered", "run_id": run_id},
        "admin": {"status": "rendered", "run_id": run_id},
        "public_status": {"status": "rendered", "run_id": run_id},
    }


def _packet_recommendation_rows(recommendations: list[Recommendation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, recommendation in enumerate(recommendations, start=1):
        rows.append(
            {
                "id": index,
                "owner": recommendation.owner,
                "action": recommendation.action,
                "why_now": recommendation.why_now,
                "expected_outcome": recommendation.scorecard.summary,
                "urgency": recommendation.urgency,
                "confidence": recommendation.confidence,
                "status": "open",
                "scorecard": recommendation.scorecard.model_dump(mode="json"),
                "evidence_refs": [
                    evidence.model_dump(mode="json") for evidence in recommendation.evidence
                ],
            }
        )
    return rows


def build_product_market_intelligence_brief(
    result: ProductMarketResult,
    *,
    product_event_count: int,
    conversation_theme_count: int,
    demand_signal_count: int,
    learning_instruction_count: int = 0,
    demand_read: ProductMarketDemandRead | dict[str, Any] | None = None,
    product_feature_comparison: ProductFeatureComparisonRead | dict[str, Any] | None = None,
    movement_map: MarketMovementMap | dict[str, Any] | None = None,
    window_comparison: ProductMarketWindowComparison | dict[str, Any] | None = None,
    conversion_diagnostics: ProductMarketConversionDiagnostics | dict[str, Any] | None = None,
    demand_recommendation_trace: dict[str, Any] | None = None,
    decision_read: dict[str, Any] | None = None,
) -> ProductMarketIntelligenceBrief:
    """Convert a deterministic synthesis result into an operator-facing read."""

    top_pattern = result.patterns[0] if result.patterns else None
    top_recommendation = result.recommendations[0] if result.recommendations else None
    top_insight = (
        top_pattern.summary
        if top_pattern is not None
        else "No cross-plane product-market pattern qualified for action in this run."
    )
    primary_action = top_recommendation.action if top_recommendation is not None else None
    evidence_source = top_recommendation.evidence if top_recommendation is not None else (
        top_pattern.evidence if top_pattern is not None else []
    )
    evidence_urls = _dedupe_urls([item.source_url for item in evidence_source])

    if top_recommendation is not None:
        watchlist = [pattern.summary for pattern in result.patterns[1:4]]
    else:
        watchlist = [pattern.summary for pattern in result.patterns[:4]]

    confidence_limits: list[str] = []
    if product_event_count == 0:
        confidence_limits.append("No product-reality evidence was captured in this run.")
    if conversation_theme_count == 0:
        confidence_limits.append("No market-conversation evidence was captured in this run.")
    if demand_signal_count == 0:
        confidence_limits.append("No tenant-side demand evidence was captured in this run.")
    if result.verdict == "quiet":
        confidence_limits.append(
            "Quiet means no cross-plane product-market pattern qualified; it does not mean the market was silent."
        )
    conversion_dict = _conversion_diagnostics_dict(conversion_diagnostics)
    conversion_summary = str(conversion_dict.get("summary") or "").strip()
    if conversion_summary:
        confidence_limits.append(conversion_summary)
    if result.patterns and not result.recommendations:
        confidence_limits.append(
            "Recommendation withheld because the evidence or approved learning gates did not clear action threshold."
        )
    if learning_instruction_count:
        confidence_limits.append(f"{learning_instruction_count} approved learning instruction(s) shaped this run.")
    demand_dict = _demand_read_dict(demand_read)
    for item in demand_dict.get("confidence_limits") or []:
        text = str(item).strip()
        if text:
            confidence_limits.append(text)
    feature_comparison_dict = _product_feature_comparison_dict(product_feature_comparison)
    feature_summary = str(feature_comparison_dict.get("summary") or "").strip()
    if feature_summary:
        confidence_limits.append(feature_summary)
    window_dict = _window_comparison_dict(window_comparison)
    for item in window_dict.get("confidence_limits") or []:
        text = str(item).strip()
        if text:
            confidence_limits.append(text)
    if not confidence_limits:
        confidence_limits.append("Confidence is bounded by the Scout, conversation, and demand exports in this run.")
    movement_dict = _movement_map_dict(movement_map)
    decision_read_dict = dict(
        decision_read
        or build_argus_decision_read(
            result=result,
            product_event_count=product_event_count,
            conversation_theme_count=conversation_theme_count,
            demand_signal_count=demand_signal_count,
            movement_map=movement_dict,
            demand_read=demand_dict,
            product_feature_comparison=feature_comparison_dict,
            conversion_diagnostics=conversion_dict,
        ).model_dump(mode="json")
    )

    next_questions = [
        "Which unscanned competitors or product surfaces could overturn this read?",
        "What new release, narrative, or demand evidence would change the recommendation?",
    ]
    if result.verdict == "quiet":
        next_questions = [
            "Were all required product, conversation, and demand sources checked before accepting a quiet read?",
            "Which missing source would most change the next sweep?",
        ]
    next_monitoring_actions = build_next_monitoring_actions(
        result=result,
        demand_signal_count=demand_signal_count,
        demand_read=demand_dict,
        conversion_diagnostics=conversion_dict,
        decision_read=decision_read_dict,
    )

    return ProductMarketIntelligenceBrief(
        verdict=result.verdict,
        top_insight=top_insight,
        primary_action=primary_action,
        watchlist=watchlist,
        evidence_urls=evidence_urls,
        confidence_limits=confidence_limits,
        next_questions=next_questions,
        demand_read=demand_dict,
        product_feature_comparison=feature_comparison_dict,
        movement_map=movement_dict,
        window_comparison=window_dict,
        conversion_diagnostics=conversion_dict,
        demand_recommendation_trace=dict(demand_recommendation_trace or {}),
        decision_read=decision_read_dict,
        next_monitoring_actions=next_monitoring_actions,
    )


def build_next_monitoring_actions(
    *,
    result: ProductMarketResult,
    demand_signal_count: int,
    demand_read: dict[str, Any] | None = None,
    conversion_diagnostics: dict[str, Any] | None = None,
    decision_read: dict[str, Any] | None = None,
) -> list[NextMonitoringAction]:
    """Derive the next Hermes monitoring agenda from this Argus run.

    Recommendations say what the business should do. These actions say what
    Hermes and Argus should collect or learn next so the next read gets
    stronger.
    """

    demand = dict(demand_read or {})
    conversion = dict(conversion_diagnostics or {})
    decision = dict(decision_read or {})
    actions: list[NextMonitoringAction] = []

    top_pattern = result.patterns[0] if result.patterns else None
    top_recommendation = result.recommendations[0] if result.recommendations else None

    if top_pattern is not None and demand_signal_count == 0:
        capability = str(top_pattern.capability)
        actions.append(
            NextMonitoringAction(
                owner="Hermes",
                plane="audience_demand",
                priority="critical",
                instruction=(
                    f"Collect GA / Looker demand evidence for {capability} before promoting "
                    "this market movement into a recommendation."
                ),
                reason=(
                    "Argus found a product-market pattern, but recommendations require tenant-side "
                    "demand evidence."
                ),
                source_families=["ga4_api_export", "ga_looker_manual_export"],
                evidence_urls=_dedupe_urls(
                    [url for pattern in result.patterns for url in _item_evidence_urls(pattern)]
                ),
            )
        )

    for topic in demand.get("top_topics") or []:
        if not isinstance(topic, Mapping):
            continue
        topic_label = str(topic.get("topic") or topic.get("capability_key") or "").strip()
        if not topic_label:
            continue
        missing_planes = [str(item) for item in topic.get("missing_planes") or []]
        evidence_urls = _dedupe_urls([str(url) for url in topic.get("evidence_urls") or []])
        if "product_proof" in missing_planes:
            actions.append(
                NextMonitoringAction(
                    owner="Hermes",
                    plane="product_reality",
                    priority="high",
                    instruction=(
                        f"Collect Scout changelog, docs, release-note, or product-page proof for {topic_label}."
                    ),
                    reason=(
                        "Tenant-side demand is rising, but Argus cannot compare the product muscle without "
                        "source-backed product proof."
                    ),
                    source_families=["scout_changelog", "scout_docs", "scout_product_page"],
                    evidence_urls=evidence_urls,
                )
            )
        if "market_conversation" in missing_planes:
            actions.append(
                NextMonitoringAction(
                    owner="Hermes",
                    plane="market_conversation",
                    priority="high",
                    instruction=(
                        f"Scan public positioning, launch, blog, case-study, and executive-speech sources "
                        f"for {topic_label}."
                    ),
                    reason=(
                        "Demand is rising, but Argus needs public conversation evidence before it can "
                        "explain whether the market is moving with the product evidence."
                    ),
                    source_families=["web_scan"],
                    evidence_urls=evidence_urls,
                )
            )

    if top_recommendation is not None:
        capability = str(top_pattern.capability if top_pattern is not None else top_recommendation.action)
        companies = _join_human(list(top_pattern.involved_companies[:4]) if top_pattern is not None else [])
        subject = f"{companies} around {capability}" if companies else capability
        recommendation_evidence = _item_evidence_urls(top_recommendation)
        actions.append(
            NextMonitoringAction(
                owner="Hermes",
                plane="source_coverage",
                priority="medium",
                instruction=(
                    f"Recheck product, conversation, and demand source coverage for {subject} in the next sweep."
                ),
                reason=(
                    "An owner action cleared the scorecard, so Hermes should verify the pattern persists "
                    "instead of treating one run as permanent truth."
                ),
                source_families=["scout_changelog", "scout_docs", "web_scan", "ga4_api_export"],
                evidence_urls=recommendation_evidence,
            )
        )
        actions.append(
            NextMonitoringAction(
                owner="Argus",
                plane="learning",
                priority="medium",
                instruction=(
                    f"Track whether the scorecard for {subject} stays above threshold and record a learning "
                    "if the recommendation is challenged."
                ),
                reason=(
                    "Actionable reads must feed the learning loop so future ranking reflects evidence quality, "
                    "not just today's strongest-looking signal."
                ),
                source_families=["learning_events", "improvement_queue"],
                evidence_urls=recommendation_evidence,
            )
        )

    for gap in conversion.get("capability_gaps") or []:
        if not isinstance(gap, Mapping):
            continue
        capability = str(gap.get("capability") or "").strip()
        if not capability:
            continue
        missing_planes = [str(item) for item in gap.get("missing_planes") or []]
        if "rising_demand" in missing_planes and not any(action.plane == "audience_demand" for action in actions):
            actions.append(
                NextMonitoringAction(
                    owner="Hermes",
                    plane="audience_demand",
                    priority="high",
                    instruction=f"Collect GA / Looker demand evidence for {capability}.",
                    reason="Product proof exists, but no rising demand signal joined to the capability.",
                    source_families=["ga4_api_export", "ga_looker_manual_export"],
                    evidence_urls=[],
                )
            )

    if not actions and decision.get("status") == "quiet":
        actions.append(
            NextMonitoringAction(
                owner="Hermes",
                plane="source_coverage",
                priority="medium",
                instruction="Verify required product, conversation, and demand sources before accepting the quiet read.",
                reason="Quiet means no pattern qualified; it is not evidence that the market was silent.",
                source_families=["scout_changelog", "scout_docs", "web_scan", "ga4_api_export"],
                evidence_urls=[],
            )
        )

    return _dedupe_monitoring_actions(actions)


def _dedupe_monitoring_actions(actions: list[NextMonitoringAction]) -> list[NextMonitoringAction]:
    seen: set[tuple[str, str, str]] = set()
    out: list[NextMonitoringAction] = []
    for action in actions:
        key = (action.owner, action.plane, action.instruction)
        if key in seen:
            continue
        seen.add(key)
        out.append(action)
    return out[:8]


def _join_human(items: list[str]) -> str:
    cleaned = [item for item in (str(item).strip() for item in items) if item]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _demand_read_dict(
    demand_read: ProductMarketDemandRead | dict[str, Any] | None,
) -> dict[str, Any]:
    if demand_read is None:
        return {}
    if isinstance(demand_read, ProductMarketDemandRead):
        return demand_read.model_dump(mode="json")
    return dict(demand_read)


def _conversion_diagnostics_dict(
    conversion_diagnostics: ProductMarketConversionDiagnostics | dict[str, Any] | None,
) -> dict[str, Any]:
    if conversion_diagnostics is None:
        return {}
    if isinstance(conversion_diagnostics, ProductMarketConversionDiagnostics):
        return conversion_diagnostics.model_dump(mode="json")
    return dict(conversion_diagnostics)


def _product_feature_comparison_dict(
    product_feature_comparison: ProductFeatureComparisonRead | dict[str, Any] | None,
) -> dict[str, Any]:
    if product_feature_comparison is None:
        return {}
    if isinstance(product_feature_comparison, ProductFeatureComparisonRead):
        return product_feature_comparison.model_dump(mode="json")
    return dict(product_feature_comparison)


def _movement_map_dict(movement_map: MarketMovementMap | dict[str, Any] | None) -> dict[str, Any]:
    if movement_map is None:
        return {}
    if isinstance(movement_map, MarketMovementMap):
        return movement_map.model_dump(mode="json")
    return dict(movement_map)


def _window_comparison_dict(
    window_comparison: ProductMarketWindowComparison | dict[str, Any] | None,
) -> dict[str, Any]:
    if window_comparison is None:
        return {}
    if isinstance(window_comparison, ProductMarketWindowComparison):
        return window_comparison.model_dump(mode="json")
    return dict(window_comparison)


__all__ = [
    "ProductMarketRunPayload",
    "ProductMarketIntelligenceBrief",
    "NextMonitoringAction",
    "ProductMarketConversionDiagnostics",
    "ProductMarketDemandRead",
    "ProductMarketWindowComparison",
    "ProductMarketWindowSlice",
    "ProductMarketRunSummary",
    "build_product_market_intelligence_brief",
    "build_next_monitoring_actions",
    "build_product_market_conversion_diagnostics",
    "build_product_market_demand_read",
    "build_product_market_window_comparison",
    "build_demand_recommendation_trace",
    "load_product_market_payload",
    "run_product_market_ledger_refresh",
    "run_product_market_payload",
]
