"""Demand-signal quality gates for Argus product-market intelligence."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field


DEMAND_CHANGE_FLOOR = 0.05
DEMAND_VALUE_FLOOR = 50.0


class DemandQualityConfig(BaseModel):
    """Runtime thresholds for treating demand as action-grade."""

    change_floor: float = Field(default=DEMAND_CHANGE_FLOOR, ge=0.0)
    value_floor: float = Field(default=DEMAND_VALUE_FLOOR, ge=0.0)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def demand_quality_config(value: DemandQualityConfig | Mapping[str, Any] | None = None) -> DemandQualityConfig:
    if value is None:
        return DemandQualityConfig()
    if isinstance(value, DemandQualityConfig):
        return value
    return DemandQualityConfig.model_validate(dict(value))


def is_rising_demand_signal(
    signal: Any,
    *,
    change_floor: float = DEMAND_CHANGE_FLOOR,
    value_floor: float = DEMAND_VALUE_FLOOR,
) -> bool:
    """Return whether a demand row is strong enough to back an Argus action."""

    change_pct = _number(getattr(signal, "change_pct", None))
    value = _number(getattr(signal, "value", None))
    return change_pct is not None and change_pct >= change_floor and value is not None and value >= value_floor
