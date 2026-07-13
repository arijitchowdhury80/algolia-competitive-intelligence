"""Normalize collector outputs into product-market workflow inputs."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field

from .adapters import (
    conversation_record_to_conversation_theme,
    looker_row_to_demand_signal,
    scout_record_to_product_change_event,
)
from .types import ConversationTheme, DemandSignal, ProductChangeEvent


class ProductMarketInputBatch(BaseModel):
    product_events: list[ProductChangeEvent] = Field(default_factory=list)
    conversation_themes: list[ConversationTheme] = Field(default_factory=list)
    demand_signals: list[DemandSignal] = Field(default_factory=list)


def _company_id(record: Mapping[str, Any]) -> int:
    value = record.get("company_id")
    if value in (None, ""):
        raise ValueError("missing required field: company_id")
    return int(value)


def _company_name(record: Mapping[str, Any]) -> str:
    value = record.get("company_name")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("missing required field: company_name")
    return str(value)


def _company_role(record: Mapping[str, Any]) -> str:
    return str(record.get("company_role") or "competitor")


def build_product_market_input_batch(
    *,
    tenant_id: int,
    scout_records: list[Mapping[str, Any]],
    conversation_records: list[Mapping[str, Any]],
    looker_rows: list[Mapping[str, Any]],
) -> ProductMarketInputBatch:
    """Build a normalized input batch from collector export rows.

    This boundary lets Scout, web scanners, and Looker/GA exporters evolve
    independently while Argus receives stable, evidence-backed objects.
    """

    product_events = [
        scout_record_to_product_change_event(
            tenant_id=tenant_id,
            company_id=_company_id(record),
            company_name=_company_name(record),
            company_role=_company_role(record),
            record=record,
        )
        for record in scout_records
    ]
    conversation_themes = [
        conversation_record_to_conversation_theme(tenant_id=tenant_id, record=record)
        for record in conversation_records
    ]
    demand_signals = [
        looker_row_to_demand_signal(tenant_id=tenant_id, row=row)
        for row in looker_rows
    ]
    return ProductMarketInputBatch(
        product_events=product_events,
        conversation_themes=conversation_themes,
        demand_signals=demand_signals,
    )


__all__ = ["ProductMarketInputBatch", "build_product_market_input_batch"]
