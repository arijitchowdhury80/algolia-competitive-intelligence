"""Input adapters for the product-market intelligence spine.

These are deliberately thin. Scout and Looker/GA can evolve independently, but
Argus receives stable value objects with evidence attached.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .types import ConversationTheme, DemandSignal, EvidenceRef, ProductChangeEvent, SourceMethod


def _require(row: Mapping[str, Any], key: str) -> Any:
    value = row.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"missing required field: {key}")
    return value


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ValueError(f"expected datetime-compatible value, got {type(value).__name__}")


def _float(value: Any, key: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"field {key} must be numeric") from exc


def _method(value: Any, default: SourceMethod) -> SourceMethod:
    if value is None:
        return default
    try:
        return SourceMethod(value)
    except ValueError as exc:
        raise ValueError(f"unsupported source method: {value}") from exc


def scout_record_to_product_change_event(
    *,
    tenant_id: int,
    company_id: int,
    company_name: str,
    company_role: str,
    record: Mapping[str, Any],
) -> ProductChangeEvent:
    """Map a Scout product/changelog extraction record into Argus muscle.

    Expected record keys:
    - capability
    - change_type
    - summary
    - source_url
    - captured_at
    - excerpt optional
    - method optional, defaults to scout_changelog
    """

    source_url = str(_require(record, "source_url"))
    captured_at = _dt(_require(record, "captured_at"))
    evidence = EvidenceRef(
        source_url=source_url,
        captured_at=captured_at,
        method=_method(record.get("method"), SourceMethod.SCOUT_CHANGELOG),
        excerpt=record.get("excerpt"),
    )
    return ProductChangeEvent(
        tenant_id=tenant_id,
        company_id=company_id,
        company_name=company_name,
        company_role=company_role,  # type: ignore[arg-type]
        capability=str(_require(record, "capability")),
        change_type=str(_require(record, "change_type")),  # type: ignore[arg-type]
        summary=str(_require(record, "summary")),
        observed_at=captured_at,
        evidence=[evidence],
    )


def looker_row_to_demand_signal(*, tenant_id: int, row: Mapping[str, Any]) -> DemandSignal:
    """Map one GA/Looker export row into a tenant demand signal."""

    source_url = str(_require(row, "source_url"))
    period_start = _dt(_require(row, "period_start"))
    period_end = _dt(_require(row, "period_end"))
    evidence = EvidenceRef(
        source_url=source_url,
        captured_at=period_end,
        method=SourceMethod.LOOKER_EXPORT,
        excerpt=row.get("excerpt"),
    )
    change_pct = row.get("change_pct")
    metadata = {
        key: row[key]
        for key in (
            "source_file",
            "source_row_number",
            "source_fingerprint",
            "argus_capability_key",
            "argus_assessment",
            "argus_suggested_filters",
            "argus_related_competitors",
            "argus_why_collect",
            "argus_evidence_urls",
        )
        if key in row and row[key] not in (None, "")
    }
    return DemandSignal(
        tenant_id=tenant_id,
        topic=str(_require(row, "topic")),
        metric=str(_require(row, "metric")),
        value=_float(_require(row, "value"), "value"),
        change_pct=None if change_pct in (None, "") else _float(change_pct, "change_pct"),
        period_start=period_start,
        period_end=period_end,
        source_label=str(_require(row, "source_label")),
        evidence=[evidence],
        metadata=metadata,
    )


def conversation_record_to_conversation_theme(
    *,
    tenant_id: int,
    record: Mapping[str, Any],
) -> ConversationTheme:
    """Map one market conversation extraction into a conversation theme.

    Expected record keys:
    - theme
    - summary
    - source_url
    - captured_at
    - company_id optional
    - company_name optional
    - intensity optional, defaults to 0.5
    - excerpt optional
    - method optional, defaults to web_scan
    """

    source_url = str(_require(record, "source_url"))
    captured_at = _dt(_require(record, "captured_at"))
    evidence = EvidenceRef(
        source_url=source_url,
        captured_at=captured_at,
        method=_method(record.get("method"), SourceMethod.WEB_SCAN),
        excerpt=record.get("excerpt"),
    )
    company_id = record.get("company_id")
    return ConversationTheme(
        tenant_id=tenant_id,
        company_id=None if company_id in (None, "") else int(company_id),
        company_name=record.get("company_name"),
        theme=str(_require(record, "theme")),
        summary=str(_require(record, "summary")),
        intensity=_float(record.get("intensity", 0.5), "intensity"),
        observed_at=captured_at,
        evidence=[evidence],
    )
