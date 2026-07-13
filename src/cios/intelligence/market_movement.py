"""Derive market movement maps from Argus pattern memory.

This module is deliberately deterministic. It turns current and historical
product-market patterns into a compact object Hermes can remember and the UI
can render without inventing meaning in the browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, Field

from .types import EvidenceRef, PatternObservation


class MarketMovementHeatCell(BaseModel):
    company_name: str
    capability: str
    heat_level: str
    signal_count: int
    recent_count: int
    prior_count: int
    confidence: float
    evidence_urls: list[str] = Field(default_factory=list)


class EntityVelocity(BaseModel):
    company_name: str
    heat_level: str
    signal_count: int
    hot_capabilities: list[str] = Field(default_factory=list)
    summary: str
    evidence_urls: list[str] = Field(default_factory=list)


class MarketMovementMap(BaseModel):
    direction_summary: str
    hot_capabilities: list[str] = Field(default_factory=list)
    heat_cells: list[MarketMovementHeatCell] = Field(default_factory=list)
    entity_velocity: list[EntityVelocity] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _MovementRecord:
    capability: str
    companies: tuple[str, ...]
    summary: str
    confidence: float
    evidence_urls: tuple[str, ...]
    observed_at: datetime


def build_market_movement_map(
    *,
    current_patterns: Iterable[PatternObservation | Mapping[str, Any]],
    historical_patterns: Iterable[PatternObservation | Mapping[str, Any]],
    as_of: datetime | None = None,
) -> MarketMovementMap:
    """Build a movement map from current patterns plus recent memory."""

    now = _normalize_dt(as_of or datetime.now(timezone.utc), fallback=datetime.now(timezone.utc))
    records = _dedupe_records(
        [
            *(_record_from_pattern(pattern, fallback_observed_at=now) for pattern in current_patterns),
            *(_record_from_pattern(pattern, fallback_observed_at=now) for pattern in historical_patterns),
        ]
    )
    if not records:
        return MarketMovementMap(
            direction_summary="No product-market movement map is available for this run.",
            confidence_limits=["No product-market patterns were available to score movement."],
        )

    recent_cutoff = now - timedelta(days=7)
    prior_cutoff = now - timedelta(days=30)
    grouped: dict[tuple[str, str], list[_MovementRecord]] = {}
    for record in records:
        for company in record.companies or ("Market",):
            grouped.setdefault((company, record.capability), []).append(record)

    heat_cells: list[MarketMovementHeatCell] = []
    for (company, capability), cell_records in grouped.items():
        recent = [record for record in cell_records if record.observed_at >= recent_cutoff]
        prior = [
            record
            for record in cell_records
            if prior_cutoff <= record.observed_at < recent_cutoff
        ]
        signal_count = len(cell_records)
        recent_count = len(recent)
        prior_count = len(prior)
        confidence = round(sum(record.confidence for record in cell_records) / signal_count, 3)
        heat_level = _heat_level(recent_count=recent_count, prior_count=prior_count, confidence=confidence)
        heat_cells.append(
            MarketMovementHeatCell(
                company_name=company,
                capability=capability,
                heat_level=heat_level,
                signal_count=signal_count,
                recent_count=recent_count,
                prior_count=prior_count,
                confidence=confidence,
                evidence_urls=_dedupe_urls(url for record in cell_records for url in record.evidence_urls),
            )
        )

    heat_cells.sort(key=lambda cell: (_heat_rank(cell.heat_level), cell.signal_count, cell.confidence), reverse=True)
    hot_capabilities = _hot_capabilities(heat_cells)
    entity_velocity = _entity_velocity(heat_cells)
    evidence_urls = _dedupe_urls(url for record in records for url in record.evidence_urls)
    direction_summary = _direction_summary(hot_capabilities=hot_capabilities, entity_velocity=entity_velocity)

    return MarketMovementMap(
        direction_summary=direction_summary,
        hot_capabilities=hot_capabilities,
        heat_cells=heat_cells,
        entity_velocity=entity_velocity,
        evidence_urls=evidence_urls,
        confidence_limits=[
            "Movement is derived from captured product-market pattern memory; missing sources can still hide market activity."
        ],
    )


def _record_from_pattern(
    pattern: PatternObservation | Mapping[str, Any],
    *,
    fallback_observed_at: datetime,
) -> _MovementRecord:
    if isinstance(pattern, PatternObservation):
        return _MovementRecord(
            capability=pattern.capability,
            companies=tuple(_clean_company(company) for company in pattern.involved_companies if _clean_company(company)),
            summary=pattern.summary,
            confidence=float(pattern.confidence),
            evidence_urls=tuple(_dedupe_urls(item.source_url for item in pattern.evidence)),
            observed_at=fallback_observed_at,
        )

    capability = str(pattern.get("capability_text") or pattern.get("capability") or "").strip()
    if not capability:
        capability = "Unclassified movement"
    companies = tuple(_companies_from_mapping(pattern))
    summary = str(pattern.get("summary") or "").strip() or f"{capability} movement observed."
    confidence = _safe_float(pattern.get("confidence"), default=0.5)
    evidence_refs = pattern.get("evidence_refs") or pattern.get("evidence") or []
    observed_at = _normalize_dt(
        pattern.get("observed_at") or pattern.get("created_at"),
        fallback=fallback_observed_at,
    )
    return _MovementRecord(
        capability=capability,
        companies=companies,
        summary=summary,
        confidence=confidence,
        evidence_urls=tuple(_urls_from_evidence_refs(evidence_refs)),
        observed_at=observed_at,
    )


def _companies_from_mapping(pattern: Mapping[str, Any]) -> list[str]:
    raw = pattern.get("involved_companies") or pattern.get("companies") or []
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, Iterable):
        values = [str(item).strip() for item in raw]
    else:
        values = []
    return [company for company in (_clean_company(value) for value in values) if company]


def _urls_from_evidence_refs(refs: Any) -> list[str]:
    if not isinstance(refs, Iterable) or isinstance(refs, (str, bytes)):
        return []
    urls: list[str] = []
    for ref in refs:
        if isinstance(ref, EvidenceRef):
            urls.append(ref.source_url)
        elif isinstance(ref, Mapping):
            source_url = ref.get("source_url") or ref.get("url")
            if source_url:
                urls.append(str(source_url))
        elif isinstance(ref, str):
            urls.append(ref)
    return _dedupe_urls(urls)


def _dedupe_records(records: list[_MovementRecord]) -> list[_MovementRecord]:
    seen: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
    out: list[_MovementRecord] = []
    for record in records:
        key = (
            record.capability.lower(),
            tuple(sorted(company.lower() for company in record.companies)),
            record.summary.lower(),
            tuple(sorted(record.evidence_urls)),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _heat_level(*, recent_count: int, prior_count: int, confidence: float) -> str:
    if recent_count >= 2:
        return "hot"
    if recent_count == 1 and (prior_count > 0 or confidence >= 0.7):
        return "warm"
    if recent_count == 1:
        return "watch"
    return "cool"


def _heat_rank(level: str) -> int:
    return {"hot": 3, "warm": 2, "watch": 1, "cool": 0}.get(level, 0)


def _hot_capabilities(cells: list[MarketMovementHeatCell]) -> list[str]:
    capability_counts: dict[str, int] = {}
    for cell in cells:
        if cell.heat_level != "hot":
            continue
        capability_counts[cell.capability] = capability_counts.get(cell.capability, 0) + cell.recent_count
    return [
        capability
        for capability, _count in sorted(
            capability_counts.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
    ]


def _entity_velocity(cells: list[MarketMovementHeatCell]) -> list[EntityVelocity]:
    grouped: dict[str, list[MarketMovementHeatCell]] = {}
    for cell in cells:
        grouped.setdefault(cell.company_name, []).append(cell)

    rows: list[EntityVelocity] = []
    for company, company_cells in grouped.items():
        signal_count = sum(cell.signal_count for cell in company_cells)
        hot_capabilities = [cell.capability for cell in company_cells if cell.heat_level == "hot"]
        top_heat = max((_heat_rank(cell.heat_level) for cell in company_cells), default=0)
        heat_level = {3: "hot", 2: "warm", 1: "watch"}.get(top_heat, "cool")
        capability_text = ", ".join(hot_capabilities or [company_cells[0].capability])
        rows.append(
            EntityVelocity(
                company_name=company,
                heat_level=heat_level,
                signal_count=signal_count,
                hot_capabilities=hot_capabilities,
                summary=f"{company} has {signal_count} movement signal(s), led by {capability_text}.",
                evidence_urls=_dedupe_urls(url for cell in company_cells for url in cell.evidence_urls),
            )
        )
    rows.sort(key=lambda row: (_heat_rank(row.heat_level), row.signal_count, row.company_name), reverse=True)
    return rows


def _direction_summary(
    *,
    hot_capabilities: list[str],
    entity_velocity: list[EntityVelocity],
) -> str:
    if hot_capabilities:
        companies = [row.company_name for row in entity_velocity[:3]]
        return f"{hot_capabilities[0]} is heating up across {_join_human(companies)}."
    if entity_velocity:
        leader = entity_velocity[0]
        return f"{leader.company_name} has the strongest captured movement, but no capability is hot yet."
    return "No product-market movement map is available for this run."


def _join_human(items: list[str]) -> str:
    clean = [item for item in items if item]
    if not clean:
        return "the monitored market"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def _normalize_dt(value: Any, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_company(value: Any) -> str:
    return str(value).strip()


def _dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw_url in urls:
        url = str(raw_url).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


__all__ = [
    "EntityVelocity",
    "MarketMovementHeatCell",
    "MarketMovementMap",
    "build_market_movement_map",
]
