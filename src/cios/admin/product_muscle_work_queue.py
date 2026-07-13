"""Build operator work items for missing product-muscle coverage."""

from __future__ import annotations

import re
from urllib.parse import urlencode

from cios.admin.types import (
    CompetitorAdminRecord,
    EvidenceLedgerState,
    FeatureComparisonState,
    ProductMuscleWorkItem,
    RegistryState,
)

_MAX_TARGETED_CAPABILITY_ITEMS_PER_COMPANY = 3


_PRODUCT_CATEGORY_HINTS = (
    "commerce",
    "discovery",
    "merchandising",
    "platform",
    "product",
    "recommendation",
    "search",
)
_NON_PRODUCT_CATEGORY_HINTS = (
    "analyst",
    "community",
    "event",
    "media",
    "newsletter",
    "publication",
    "research",
    "source",
)


def build_product_muscle_work_queue(
    *,
    tenant_slug: str,
    registry: RegistryState,
    feature_comparison: FeatureComparisonState,
    evidence_ledger: EvidenceLedgerState,
    product_surface_execution_trace: dict[tuple[str, str], dict] | None = None,
) -> list[ProductMuscleWorkItem]:
    """Return product-reality tasks Hermes/Argus needs before trusting matrix reads."""
    known_cells_by_company = _known_feature_cells_by_company(feature_comparison)
    product_events_by_company = _product_events_by_company(evidence_ledger)
    surface_trace = product_surface_execution_trace or {}
    items: list[ProductMuscleWorkItem] = []

    for competitor in sorted(registry.competitors, key=lambda item: (item.priority, item.competitor_name.lower())):
        if competitor.status != "active":
            continue
        active_surfaces = [surface for surface in competitor.product_surfaces if surface.status == "active"]
        failed_surfaces = [surface for surface in competitor.product_surfaces if surface.status == "failed"]
        paused_surfaces = [surface for surface in competitor.product_surfaces if surface.status == "paused"]
        retired_surfaces = [surface for surface in competitor.product_surfaces if surface.status == "retired"]
        candidate_surfaces = [surface for surface in competitor.product_surfaces if surface.status == "candidate"]
        key = (_norm(competitor.competitor_name), "competitor")
        known_cell_count = known_cells_by_company.get(key, 0)
        product_event_count = product_events_by_company.get(key, 0)
        if not _is_product_muscle_relevant(
            competitor,
            known_cell_count=known_cell_count,
            product_event_count=product_event_count,
        ):
            continue
        observed_state = {
            "company_name": competitor.competitor_name,
            "configured_product_surface_count": len(competitor.product_surfaces),
            "active_product_surface_count": len(active_surfaces),
            "candidate_product_surface_count": len(candidate_surfaces),
            "failed_product_surface_count": len(failed_surfaces),
            "paused_product_surface_count": len(paused_surfaces),
            "retired_product_surface_count": len(retired_surfaces),
            "known_capability_cell_count": known_cell_count,
            "product_event_count": product_event_count,
        }
        observed_state.update(_latest_surface_export_state(surface_trace.get(key)))

        if not active_surfaces:
            items.append(
                ProductMuscleWorkItem(
                    work_item_id=f"product-muscle:competitor:{competitor.competitor_id}:missing-surfaces",
                    company_id=competitor.competitor_id,
                    company_name=competitor.competitor_name,
                    company_role="competitor",
                    severity="blocks_feature_matrix",
                    title=f"{competitor.competitor_name} has no active product surfaces",
                    why_needed=(
                        f"Argus cannot compare {competitor.competitor_name}'s shipped product reality "
                        "because no active changelog, docs, release notes, API docs, pricing, integration, "
                        "or product page surface is configured."
                    ),
                    blocks=[
                        "feature comparison",
                        "product gap scoring",
                        "product-backed recommendations",
                    ],
                    next_step=(
                        "Add a changelog, docs, release notes, API docs, pricing, integration, "
                        "or product page source."
                    ),
                    primary_action_label="Add product surface",
                    primary_action_href=f"/admin?tenant={tenant_slug}#add-product-surface",
                    primary_action_method="get",
                    secondary_action_label="Refresh Argus from evidence ledger",
                    secondary_action_href=f"/admin/{tenant_slug}/argus/ledger-refresh",
                    secondary_action_method="post",
                    observed_state=observed_state,
                )
            )
            continue

        if known_cell_count > 0 or product_event_count > 0:
            for item in _planned_unknown_capability_items(
                tenant_slug=tenant_slug,
                competitor=competitor,
                company_key=key,
                feature_comparison=feature_comparison,
                observed_state=observed_state,
            ):
                items.append(item)

        if known_cell_count == 0 and product_event_count == 0:
            next_step = _product_surface_next_step(observed_state)
            action = _product_surface_action(
                tenant_slug=tenant_slug,
                company_name=competitor.competitor_name,
                observed_state=observed_state,
            )
            items.append(
                ProductMuscleWorkItem(
                    work_item_id=f"product-muscle:competitor:{competitor.competitor_id}:no-feature-evidence",
                    company_id=competitor.competitor_id,
                    company_name=competitor.competitor_name,
                    company_role="competitor",
                    severity="limits_confidence",
                    title=f"{competitor.competitor_name} has product surfaces but no feature evidence",
                    why_needed=(
                        f"Argus has active product-surface URLs for {competitor.competitor_name}, but "
                        "Scout extraction has not produced feature evidence or product events for the "
                        "current product muscle ledger."
                    ),
                    blocks=["feature confidence", "competitor product read", "quiet-day trust"],
                    next_step=next_step
                    or (
                        "Run Scout product-surface extraction for the active surfaces, then refresh "
                        "Argus from the evidence ledger."
                    ),
                    primary_action_label=action["primary_label"],
                    primary_action_href=action["primary_href"],
                    primary_action_method=action["primary_method"],
                    secondary_action_label=action["secondary_label"],
                    secondary_action_href=action["secondary_href"],
                    secondary_action_method=action["secondary_method"],
                    observed_state=observed_state,
                )
            )

    return items


def _planned_unknown_capability_items(
    *,
    tenant_slug: str,
    competitor: CompetitorAdminRecord,
    company_key: tuple[str, str],
    feature_comparison: FeatureComparisonState,
    observed_state: dict[str, object],
) -> list[ProductMuscleWorkItem]:
    items: list[ProductMuscleWorkItem] = []
    for row in feature_comparison.rows:
        if not row.planned_by_argus:
            continue
        cell = _row_cell_for_company(row, company_key)
        if cell is None or cell.position_status != "unknown":
            continue
        capability = row.capability_text
        capability_state = {
            **observed_state,
            "capability_text": capability,
            "matrix_cell_status": cell.position_status,
            "matrix_cell_summary": cell.summary,
            "planned_by_argus": True,
        }
        items.append(
            ProductMuscleWorkItem(
                work_item_id=(
                    f"product-muscle:competitor:{competitor.competitor_id}:"
                    f"capability:{_slug(capability)}"
                ),
                company_id=competitor.competitor_id,
                company_name=competitor.competitor_name,
                company_role="competitor",
                capability_text=capability,
                severity="limits_confidence",
                title=f"{competitor.competitor_name} has no product proof for {capability}",
                why_needed=(
                    f"Argus explicitly planned {capability} as a capability to investigate, but "
                    f"the product muscle matrix still has no product proof for "
                    f"{competitor.competitor_name}."
                ),
                blocks=["capability comparison", "feature gap scoring", "demand-backed recommendations"],
                next_step=(
                    f"Run product-surface extraction for {competitor.competitor_name}, then refresh "
                    f"Argus from the evidence ledger to resolve the {capability} matrix cell."
                ),
                primary_action_label="Run surface extraction",
                primary_action_href=(
                    f"/admin/{tenant_slug}/argus/product-surface-extraction?"
                    f"{urlencode({'company_name': competitor.competitor_name, 'focus_capability': capability})}"
                ),
                primary_action_method="post",
                secondary_action_label="Refresh Argus from evidence ledger",
                secondary_action_href=f"/admin/{tenant_slug}/argus/ledger-refresh",
                secondary_action_method="post",
                observed_state=capability_state,
            )
        )
        if len(items) >= _MAX_TARGETED_CAPABILITY_ITEMS_PER_COMPANY:
            break
    return items


def _row_cell_for_company(row, company_key: tuple[str, str]):
    for cell in row.cells:
        if (_norm(cell.company_name), cell.company_role) == company_key:
            return cell
    return None


def _is_product_muscle_relevant(
    competitor: CompetitorAdminRecord,
    *,
    known_cell_count: int,
    product_event_count: int,
) -> bool:
    """Return whether a registry row belongs in the product-reality queue.

    The registry can contain market/topic/source buckets as well as true
    product-comparable companies. Until the registry has an explicit entity
    type, product-muscle blockers must be limited to rows with product metadata
    or product evidence so source buckets do not masquerade as competitors.
    """
    if competitor.product_surfaces:
        return True
    if known_cell_count > 0 or product_event_count > 0:
        return True

    category = _norm(competitor.category or "")
    if category:
        if any(hint in category for hint in _NON_PRODUCT_CATEGORY_HINTS):
            return False
        if any(hint in category for hint in _PRODUCT_CATEGORY_HINTS):
            return True

    if str(competitor.domain or "").strip():
        return True

    return False


def _known_feature_cells_by_company(feature_comparison: FeatureComparisonState) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in feature_comparison.rows:
        for cell in row.cells:
            if cell.position_status == "unknown":
                continue
            if cell.evidence_count <= 0:
                continue
            key = (_norm(cell.company_name), cell.company_role)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _product_events_by_company(evidence_ledger: EvidenceLedgerState) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for event in evidence_ledger.product_events:
        key = (_norm(event.company_name), event.company_role)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _norm(value))
    return slug.strip("-") or "unknown"


def _latest_surface_export_state(trace: dict | None) -> dict[str, object]:
    if not trace:
        return {}
    category, repair_action = _classify_latest_surface_export(trace)
    state: dict[str, object] = {
        "latest_surface_export_planned_count": int(trace.get("planned_surface_count") or 0),
        "latest_surface_export_succeeded_count": int(trace.get("succeeded_surface_count") or 0),
        "latest_surface_export_failed_count": int(trace.get("failed_surface_count") or 0),
        "latest_surface_export_row_count": int(trace.get("row_count") or 0),
        "latest_surface_export_empty_output_count": int(trace.get("empty_output_count") or 0),
    }
    if category:
        state["latest_surface_export_failure_category"] = category
    if repair_action:
        state["latest_surface_export_repair_action"] = repair_action
    if trace.get("last_error"):
        state["latest_surface_export_last_error"] = trace["last_error"]
    if trace.get("summary_path"):
        state["latest_surface_export_summary_path"] = trace["summary_path"]
    return state


def _classify_latest_surface_export(trace: dict) -> tuple[str | None, str | None]:
    last_error = str(trace.get("last_error") or "").lower()
    failed_count = int(trace.get("failed_surface_count") or 0)
    succeeded_count = int(trace.get("succeeded_surface_count") or 0)
    row_count = int(trace.get("row_count") or 0)
    empty_output_count = int(trace.get("empty_output_count") or 0)
    if "timed out" in last_error or "timeoutexpired" in last_error or "timeout" in last_error:
        return (
            "timeout",
            "Retry the surface with JavaScript enabled or a higher timeout, then replace the source if it still stalls.",
        )
    if "no markdown" in last_error:
        return (
            "no_markdown",
            "Replace or fix the product surface URL, or use a crawlable docs/changelog source that Scout can return as markdown.",
        )
    if failed_count > 0:
        return (
            "scout_failure",
            "Inspect the Scout failure and repair the source URL, Scout bridge, or extraction settings before rerunning.",
        )
    if succeeded_count > 0 and row_count == 0 and empty_output_count > 0:
        return (
            "empty_extraction",
            "Review the product-surface extraction prompt or replace the source with a page that contains concrete release, docs, pricing, or integration proof.",
        )
    return None, None


def _product_surface_next_step(observed_state: dict[str, object]) -> str | None:
    category = observed_state.get("latest_surface_export_failure_category")
    candidate_count = int(observed_state.get("candidate_product_surface_count") or 0)
    company_name = str(observed_state.get("company_name") or "").strip()
    if candidate_count > 0 and company_name:
        return (
            f"Promote validated candidate product surfaces for {company_name}, then rerun "
            "surface extraction before trusting the feature matrix."
        )
    if _has_unprocessed_active_surfaces(observed_state) and company_name:
        return (
            f"Run product-surface extraction for newly active {company_name} surfaces, then refresh "
            "Argus from the evidence ledger before retrying older failed surfaces."
        )
    repair_action = observed_state.get("latest_surface_export_repair_action")
    if isinstance(repair_action, str) and repair_action.strip():
        return f"{repair_action} Then refresh Argus from the evidence ledger."
    return None


def _product_surface_action(
    *,
    tenant_slug: str,
    company_name: str,
    observed_state: dict[str, object],
) -> dict[str, str | None]:
    category = observed_state.get("latest_surface_export_failure_category")
    failed_count = int(observed_state.get("latest_surface_export_failed_count") or 0)
    is_empty_extraction = category == "empty_extraction"
    candidate_count = int(observed_state.get("candidate_product_surface_count") or 0)
    if candidate_count > 0:
        promote_query = urlencode({"company_name": company_name, "limit": 1})
        if isinstance(category, str) and category.strip():
            secondary_label = "Run repair retry"
            secondary_href = (
                f"/admin/{tenant_slug}/argus/product-surface-repair?"
                f"{urlencode({'company_name': company_name, 'category': category})}"
            )
            secondary_method = "post"
        else:
            secondary_label = "Run surface extraction"
            secondary_href = (
                f"/admin/{tenant_slug}/argus/product-surface-extraction?"
                f"{urlencode({'company_name': company_name})}"
            )
            secondary_method = "post"
        return {
            "primary_label": "Promote candidate surface",
            "primary_href": f"/admin/{tenant_slug}/argus/product-surface-candidates/promote?{promote_query}",
            "primary_method": "post",
            "secondary_label": secondary_label,
            "secondary_href": secondary_href,
            "secondary_method": secondary_method,
        }
    if _has_unprocessed_active_surfaces(observed_state):
        extraction_query = urlencode({"company_name": company_name})
        if isinstance(category, str) and category.strip():
            secondary_label = "Run repair retry"
            secondary_href = (
                f"/admin/{tenant_slug}/argus/product-surface-repair?"
                f"{urlencode({'company_name': company_name, 'category': category})}"
            )
            secondary_method = "post"
        else:
            secondary_label = "Open product surfaces"
            secondary_href = f"/admin?tenant={tenant_slug}#add-product-surface"
            secondary_method = "get"
        return {
            "primary_label": "Run surface extraction",
            "primary_href": f"/admin/{tenant_slug}/argus/product-surface-extraction?{extraction_query}",
            "primary_method": "post",
            "secondary_label": secondary_label,
            "secondary_href": secondary_href,
            "secondary_method": secondary_method,
        }
    if isinstance(category, str) and category.strip() and (failed_count > 0 or is_empty_extraction):
        query = urlencode({"company_name": company_name, "category": category})
        return {
            "primary_label": "Run repair retry",
            "primary_href": f"/admin/{tenant_slug}/argus/product-surface-repair?{query}",
            "primary_method": "post",
            "secondary_label": "Open product surfaces",
            "secondary_href": f"/admin?tenant={tenant_slug}#add-product-surface",
            "secondary_method": "get",
        }
    active_surface_count = int(observed_state.get("active_product_surface_count") or 0)
    if active_surface_count > 0:
        query = urlencode({"company_name": company_name})
        return {
            "primary_label": "Run surface extraction",
            "primary_href": f"/admin/{tenant_slug}/argus/product-surface-extraction?{query}",
            "primary_method": "post",
            "secondary_label": "Open product surfaces",
            "secondary_href": f"/admin?tenant={tenant_slug}#add-product-surface",
            "secondary_method": "get",
        }
    return {
        "primary_label": "Open product surfaces",
        "primary_href": f"/admin?tenant={tenant_slug}#add-product-surface",
        "primary_method": "get",
        "secondary_label": "Refresh Argus from evidence ledger",
        "secondary_href": f"/admin/{tenant_slug}/argus/ledger-refresh",
        "secondary_method": "post",
    }


def _has_unprocessed_active_surfaces(observed_state: dict[str, object]) -> bool:
    active_surface_count = int(observed_state.get("active_product_surface_count") or 0)
    planned_surface_count = int(observed_state.get("latest_surface_export_planned_count") or 0)
    return active_surface_count > 0 and planned_surface_count > 0 and active_surface_count > planned_surface_count


def product_muscle_observed_state_text(item: ProductMuscleWorkItem) -> str:
    """Format observed state for artifact writers and admin UI."""
    if not item.observed_state:
        return "No observed state recorded."
    parts: list[str] = []
    for key, value in item.observed_state.items():
        if value is None or value == "":
            continue
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return " · ".join(parts) if parts else "No observed state recorded."


__all__ = ["build_product_muscle_work_queue", "product_muscle_observed_state_text"]
