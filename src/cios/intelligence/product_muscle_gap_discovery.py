"""Execute product-muscle gap discovery plans.

The daily run publishes `product_muscle_gap_plan` as the machine-readable
answer to "which monitored companies lack product-surface coverage?" This
module turns that plan into validated candidate `product_surfaces`; it does not
fetch Scout evidence or promote candidates to active monitoring by itself.
"""

from __future__ import annotations

from typing import Any, Protocol

from cios.hunter.types import ValidationResult
from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget, SurfaceFamily


DISCOVERY_SOURCE = "product_muscle_gap_plan"
_SURFACE_FAMILIES = set(SurfaceFamily.__args__)


class ProductSurfaceCandidateRepository(Protocol):
    def upsert_candidate_target(
        self,
        target: ProductSurfaceTarget,
        *,
        validation: ValidationResult,
        discovery_source: str,
    ) -> int: ...


class ProductSurfaceCandidateValidator(Protocol):
    def validate(self, tenant_id: int, url: str) -> ValidationResult: ...


def execute_product_muscle_gap_discovery(
    *,
    tenant_id: int,
    gap_plan: dict[str, Any],
    validator: ProductSurfaceCandidateValidator,
    product_surfaces: ProductSurfaceCandidateRepository,
) -> dict[str, Any]:
    candidate_url_count = 0
    heuristic_candidate_url_count = 0
    validated_count = 0
    rejected_count = 0
    duplicate_product_surface_count = 0
    new_candidate_rejected_count = 0
    stored_candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []

    for company in _collection_targets(gap_plan):
        company_name = str(company.get("company_name") or "").strip()
        if not company_name:
            continue
        competitor_id = int(company.get("competitor_id") or 0)
        target_context = _target_context(company)
        for candidate in _candidate_urls(company):
            url = str(candidate.get("url") or "").strip()
            if not url:
                continue
            candidate_url_count += 1
            candidate_source = str(candidate.get("candidate_source") or "candidate_surface_urls")
            if candidate_source == "heuristic_surface_probes":
                heuristic_candidate_url_count += 1
            discovery_reason = str(candidate.get("discovery_reason") or "").strip()
            requested_family = _surface_family(candidate.get("surface_family"))
            validation = validator.validate(tenant_id, url)
            surface_family = _surface_family(validation.source_family) or requested_family or "other"

            if not validation.accepted:
                rejected_count += 1
                if validation.reason == "duplicate_normalized_url":
                    duplicate_product_surface_count += 1
                else:
                    new_candidate_rejected_count += 1
                rejected_candidates.append(
                    {
                        "company_name": company_name,
                        "surface_family": requested_family or surface_family,
                        "url": url,
                        "reason": validation.reason,
                        "http_status": validation.http_status,
                        **_candidate_context(candidate_source, discovery_reason),
                        **target_context,
                    }
                )
                continue

            validated_count += 1
            target = ProductSurfaceTarget(
                tenant_id=tenant_id,
                company_id=competitor_id,
                company_name=company_name,
                company_role="competitor",
                surface_family=surface_family,
                url=validation.url,
            )
            surface_id = product_surfaces.upsert_candidate_target(
                target,
                validation=validation,
                discovery_source=DISCOVERY_SOURCE,
            )
            stored_candidates.append(
                {
                    "surface_id": surface_id,
                    "company_name": company_name,
                    "surface_family": surface_family,
                    "url": validation.url,
                    "http_status": validation.http_status,
                    **_candidate_context(candidate_source, discovery_reason),
                    **target_context,
                }
            )

    return {
        "status": "completed",
        "candidate_url_count": candidate_url_count,
        "heuristic_candidate_url_count": heuristic_candidate_url_count,
        "validated_count": validated_count,
        "rejected_count": rejected_count,
        "duplicate_product_surface_count": duplicate_product_surface_count,
        # Backward-compatible alias for older dashboard sidecar readers.
        "duplicate_source_count": duplicate_product_surface_count,
        "new_candidate_rejected_count": new_candidate_rejected_count,
        "stored_candidate_count": len(stored_candidates),
        "stored_candidates": stored_candidates,
        "rejected_candidates": rejected_candidates,
    }


def _collection_targets(gap_plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(gap_plan, dict):
        return []
    rows = [
        *_dict_rows(gap_plan.get("missing_companies")),
        *_dict_rows(gap_plan.get("feature_unknown_collection_targets")),
        *_dict_rows(gap_plan.get("empty_surface_targets")),
    ]
    return rows


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    return [row for row in rows if isinstance(row, dict)]


def _target_context(company: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    capability_text = str(company.get("capability_text") or "").strip()
    if capability_text:
        context["capability_text"] = capability_text
    if company.get("priority_score") is not None:
        context["priority_score"] = int(company.get("priority_score") or 0)
    reasons = company.get("priority_reasons")
    if isinstance(reasons, list) and reasons:
        context["priority_reasons"] = [str(reason) for reason in reasons if str(reason).strip()]
    failed_surface_family = str(company.get("failed_surface_family") or "").strip()
    if failed_surface_family:
        context["failed_surface_family"] = failed_surface_family
    return context


def _missing_companies(gap_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = gap_plan.get("missing_companies") if isinstance(gap_plan, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _candidate_urls(company: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("candidate_surface_urls", "heuristic_surface_probes"):
        rows = company.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item.setdefault("candidate_source", key)
            candidates.append(item)
    return candidates


def _candidate_context(candidate_source: str, discovery_reason: str) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if candidate_source == "heuristic_surface_probes":
        context["candidate_source"] = candidate_source
    if discovery_reason:
        context["discovery_reason"] = discovery_reason
    return context


def _surface_family(value: Any) -> SurfaceFamily | None:
    text = str(value or "").strip()
    if text in _SURFACE_FAMILIES:
        return text  # type: ignore[return-value]
    return None


__all__ = ["execute_product_muscle_gap_discovery"]
