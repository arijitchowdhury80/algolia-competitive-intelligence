"""Normalize Scout extraction output from product surfaces.

Scout is responsible for acquiring and extracting structured facts from pages.
This module turns Scout's response shape into the stable product-market rows
that Argus can validate, store, and synthesize.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field, model_validator


SurfaceFamily = Literal[
    "changelog",
    "docs",
    "release_notes",
    "product_page",
    "pricing",
    "api_docs",
    "integration",
    "other",
]


class ScoutSurfaceExtractionError(ValueError):
    """Raised when a Scout extraction response cannot be normalized."""


class ProductSurfaceTarget(BaseModel):
    """One product-reality source that Scout should inspect."""

    surface_id: int | None = None
    tenant_id: int
    company_id: int
    company_name: str = Field(min_length=1)
    company_role: Literal["own", "competitor", "partner"] = "competitor"
    surface_family: SurfaceFamily
    url: str = Field(min_length=1)

    @model_validator(mode="after")
    def _require_url(self) -> "ProductSurfaceTarget":
        if not self.url.strip():
            raise ValueError("ProductSurfaceTarget requires url")
        return self


def scout_extract_response_to_product_records(
    response: Mapping[str, Any],
    target: ProductSurfaceTarget,
) -> list[dict[str, Any]]:
    """Convert one Scout extract response into product-market input rows."""

    if response.get("success") is False:
        error = response.get("error") or "Scout extraction failed"
        raise ScoutSurfaceExtractionError(str(error))

    changes = _changes(response)
    if not changes:
        return []

    captured_at = _captured_at(response)
    source_url = str(response.get("url") or target.url)
    method = _method_for_surface(target.surface_family)
    records: list[dict[str, Any]] = []
    for change in changes:
        records.append(
            {
                "company_id": target.company_id,
                "company_name": target.company_name,
                "company_role": target.company_role,
                "capability": _required(change, "capability"),
                "change_type": _required(change, "change_type"),
                "summary": _required(change, "summary"),
                "source_url": str(change.get("source_url") or source_url),
                "captured_at": str(change.get("captured_at") or captured_at),
                "excerpt": change.get("excerpt"),
                "method": method,
                "surface_family": target.surface_family,
            }
        )
    return records


def _changes(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = response.get("data")
    if not isinstance(data, Mapping):
        return []
    raw_changes = data.get("changes")
    if raw_changes is None:
        return []
    if not isinstance(raw_changes, list):
        raise ScoutSurfaceExtractionError("Scout response data.changes must be a list")
    return [_mapping(change, "change") for change in raw_changes]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScoutSurfaceExtractionError(f"Scout {label} must be an object")
    return value


def _captured_at(response: Mapping[str, Any]) -> str:
    metadata = response.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("crawled_at"):
        return str(metadata["crawled_at"])
    if response.get("captured_at"):
        return str(response["captured_at"])
    raise ScoutSurfaceExtractionError("Scout response requires metadata.crawled_at")


def _required(change: Mapping[str, Any], key: str) -> str:
    value = change.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ScoutSurfaceExtractionError(f"Scout change missing required field: {key}")
    return str(value)


def _method_for_surface(surface_family: SurfaceFamily) -> str:
    if surface_family in {"changelog", "release_notes"}:
        return "scout_changelog"
    if surface_family in {"docs", "api_docs", "integration"}:
        return "scout_docs"
    return "scout_product_page"


__all__ = [
    "ProductSurfaceTarget",
    "ScoutSurfaceExtractionError",
    "scout_extract_response_to_product_records",
]
