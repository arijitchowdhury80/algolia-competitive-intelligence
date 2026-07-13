"""Build Argus operator work items from missing evidence planes."""

from __future__ import annotations

from typing import Any

from cios.admin.demand_imports import ACCEPTED_DEMAND_SUFFIXES, DEMAND_IMPORT_TEMPLATE_FIELDS
from cios.admin.types import ArgusEvidenceWorkItem, ArgusRunStatus, EvidenceLedgerState


def build_argus_evidence_work_queue(
    *,
    tenant_slug: str,
    run_status: ArgusRunStatus,
    evidence_ledger: EvidenceLedgerState,
) -> list[ArgusEvidenceWorkItem]:
    """Return operator tasks Argus needs before its read can become action."""
    latest = run_status.run_intelligence_history[0] if run_status.run_intelligence_history else None
    if latest is None:
        return []

    items: list[ArgusEvidenceWorkItem] = []
    if latest.pattern_count > 0 and latest.demand_signal_count == 0:
        items.append(
            ArgusEvidenceWorkItem(
                work_item_id=_work_item_id(latest.run_intelligence_id, "demand"),
                evidence_plane="demand",
                severity="blocks_action",
                title="Demand plane missing",
                why_needed=_first_matching_limit(
                    latest.confidence_limits,
                    "demand",
                    default=(
                        "Argus found product-market patterns, but no tenant-side demand "
                        "evidence was captured in this run."
                    ),
                ),
                blocks=["owner recommendations", "priority ranking", "action promotion"],
                next_step="Upload GA4 / Looker demand export for the current and previous periods.",
                operator_surface="Demand imports",
                primary_action_label="Download demand template",
                primary_action_href=f"/api/tenants/{tenant_slug}/argus/demand-imports/template",
                primary_action_method="get",
                secondary_action_label="Prepare demand and refresh Argus",
                secondary_action_href=f"/admin/{tenant_slug}/argus/demand-imports/refresh",
                secondary_action_method="post",
                accepted_input_formats=_accepted_demand_formats(),
                required_fields=list(DEMAND_IMPORT_TEMPLATE_FIELDS),
                observed_state=_demand_observed_state(run_status, evidence_ledger),
                related_run_intelligence_id=latest.run_intelligence_id,
                observed_pattern_count=latest.pattern_count,
            )
        )

    if latest.conversation_theme_count > 0 and latest.product_event_count == 0:
        items.append(
            ArgusEvidenceWorkItem(
                work_item_id=_work_item_id(latest.run_intelligence_id, "product_muscle"),
                evidence_plane="product_muscle",
                severity="blocks_action",
                title="Product proof missing",
                why_needed=(
                    "Argus captured market conversation, but no changelog, docs, release, pricing, "
                    "API, or product-surface proof was captured for the run."
                ),
                blocks=["feature comparison", "product gap scoring", "action promotion"],
                next_step=(
                    "Add or repair Scout product-surface sources for changelog, docs, release notes, "
                    "pricing, API docs, and product pages."
                ),
                operator_surface="Product surfaces",
                primary_action_label="Add product surface",
                primary_action_href=f"/admin?tenant={tenant_slug}#add-product-surface",
                primary_action_method="get",
                secondary_action_label="Refresh Argus from evidence ledger",
                secondary_action_href=f"/admin/{tenant_slug}/argus/ledger-refresh",
                secondary_action_method="post",
                observed_state=_ledger_observed_state(evidence_ledger),
                related_run_intelligence_id=latest.run_intelligence_id,
                observed_pattern_count=latest.pattern_count,
            )
        )

    if latest.product_event_count > 0 and latest.conversation_theme_count == 0:
        items.append(
            ArgusEvidenceWorkItem(
                work_item_id=_work_item_id(latest.run_intelligence_id, "conversation"),
                evidence_plane="conversation",
                severity="limits_priority",
                title="Conversation plane missing",
                why_needed=(
                    "Argus captured product proof, but no public GTM, content, executive, or "
                    "market conversation evidence was captured for the run."
                ),
                blocks=["narrative-gap scoring", "sales messaging priority"],
                next_step=(
                    "Add or repair outward conversation sources: blogs, campaigns, news, "
                    "case studies, executive speech, and social surfaces."
                ),
                operator_surface="Sources",
                primary_action_label="Add source URL",
                primary_action_href=f"/admin?tenant={tenant_slug}#add-source",
                primary_action_method="get",
                secondary_action_label="Refresh Argus from evidence ledger",
                secondary_action_href=f"/admin/{tenant_slug}/argus/ledger-refresh",
                secondary_action_method="post",
                observed_state=_ledger_observed_state(evidence_ledger),
                related_run_intelligence_id=latest.run_intelligence_id,
                observed_pattern_count=latest.pattern_count,
            )
        )

    if (
        latest.product_event_count > 0
        and latest.conversation_theme_count > 0
        and latest.pattern_count == 0
        and latest.recommendation_count == 0
    ):
        items.append(
            ArgusEvidenceWorkItem(
                work_item_id=_work_item_id(latest.run_intelligence_id, "pattern"),
                evidence_plane="pattern",
                severity="blocks_action",
                title="Pattern synthesis missing",
                why_needed=(
                    "Argus has raw product and conversation evidence, but no cross-plane pattern "
                    "was persisted for recommendation scoring."
                ),
                blocks=["strategic synthesis", "owner recommendations", "learning apply"],
                next_step="Refresh Argus from the evidence ledger and inspect blocked learning gates.",
                operator_surface="Argus run console",
                primary_action_label="Refresh Argus from evidence ledger",
                primary_action_href=f"/admin/{tenant_slug}/argus/ledger-refresh",
                primary_action_method="post",
                observed_state=_ledger_observed_state(evidence_ledger),
                related_run_intelligence_id=latest.run_intelligence_id,
                observed_pattern_count=latest.pattern_count,
            )
        )

    return items


def _accepted_demand_formats() -> list[str]:
    return [suffix.removeprefix(".") for suffix in ACCEPTED_DEMAND_SUFFIXES]


def _work_item_id(run_intelligence_id: int | None, plane: str) -> str:
    run_id = run_intelligence_id if run_intelligence_id is not None else "latest"
    return f"argus-evidence:{run_id}:{plane}"


def _first_matching_limit(limits: list[str], needle: str, *, default: str) -> str:
    needle_l = needle.lower()
    for limit in limits:
        if needle_l in limit.lower():
            return limit
    return default


def _demand_observed_state(run_status: ArgusRunStatus, evidence_ledger: EvidenceLedgerState) -> dict[str, Any]:
    state = {
        "demand_plane_status": run_status.demand_plane_status,
        "looker_discovered_count": run_status.looker_discovered_count,
        "looker_ready_count": run_status.looker_ready_count,
        "looker_error_count": run_status.looker_error_count,
        "looker_normalized_row_count": run_status.looker_normalized_row_count,
        "looker_skipped_row_count": run_status.looker_skipped_row_count,
        "ledger_demand_signal_count": len(evidence_ledger.demand_signals),
    }
    if run_status.looker_manifest_path:
        state["looker_manifest_path"] = run_status.looker_manifest_path
    return state


def _ledger_observed_state(evidence_ledger: EvidenceLedgerState) -> dict[str, Any]:
    return {
        "product_event_count": len(evidence_ledger.product_events),
        "conversation_theme_count": len(evidence_ledger.conversation_themes),
        "demand_signal_count": len(evidence_ledger.demand_signals),
        "pattern_count": len(evidence_ledger.patterns),
    }
