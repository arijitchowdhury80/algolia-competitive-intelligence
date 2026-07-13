"""Derived product-feature comparison read for the CI-OS admin app."""

from __future__ import annotations

from cios.admin.types import (
    FeatureComparisonCell,
    FeatureComparisonCompany,
    FeatureComparisonRow,
    FeatureComparisonState,
    FeatureMatrixAdminRecord,
    RegistryState,
)


def build_feature_comparison_state(
    *,
    registry: RegistryState,
    feature_matrix: list[FeatureMatrixAdminRecord],
    planned_capabilities: list[str] | None = None,
    own_company_name: str | None = None,
) -> FeatureComparisonState:
    """Build a matrix that shows captured proof and monitored unknowns.

    Unknown is deliberately not a product-gap claim. It means Argus has no
    product proof for that company/capability in the current evidence ledger.
    """

    companies = _comparison_companies(registry, feature_matrix, own_company_name=own_company_name)
    capabilities = _comparison_capabilities(
        feature_matrix=feature_matrix,
        planned_capabilities=planned_capabilities or [],
    )
    planned_keys = {_norm(capability) for capability in planned_capabilities or [] if str(capability or "").strip()}
    by_key = {
        (_norm(row.capability_text), _norm(row.company_name), row.company_role): row
        for row in feature_matrix
    }
    rows: list[FeatureComparisonRow] = []
    for capability in capabilities:
        cells: list[FeatureComparisonCell] = []
        for company in companies:
            matrix_row = by_key.get((_norm(capability), _norm(company.company_name), company.company_role))
            if matrix_row is None:
                cells.append(_unknown_cell(capability=capability, company=company))
                continue
            evidence_urls = _evidence_urls(matrix_row.evidence_refs)
            cells.append(
                FeatureComparisonCell(
                    company_name=matrix_row.company_name,
                    company_role=matrix_row.company_role,
                    position_status=matrix_row.position_status,
                    summary=matrix_row.summary or f"{matrix_row.company_name} has captured {matrix_row.position_status} evidence.",
                    confidence=matrix_row.confidence,
                    evidence_count=len(evidence_urls),
                    first_evidence_url=evidence_urls[0] if evidence_urls else None,
                    updated_at=matrix_row.updated_at,
                )
            )
        rows.append(_comparison_row(capability, cells, planned_by_argus=_norm(capability) in planned_keys))
    return FeatureComparisonState(
        tenant_slug=registry.tenant_slug,
        tenant_id=registry.tenant_id,
        companies=companies,
        rows=rows,
    )


def _comparison_companies(
    registry: RegistryState,
    feature_matrix: list[FeatureMatrixAdminRecord],
    *,
    own_company_name: str | None = None,
) -> list[FeatureComparisonCompany]:
    by_key: dict[tuple[str, str], FeatureComparisonCompany] = {}

    if own_company_name and own_company_name.strip():
        key = (_norm(own_company_name), "own")
        by_key.setdefault(
            key,
            FeatureComparisonCompany(
                company_name=own_company_name.strip(),
                company_role="own",
                status="active",
            ),
        )

    for row in feature_matrix:
        if row.company_role == "own":
            key = (_norm(row.company_name), row.company_role)
            by_key.setdefault(
                key,
                FeatureComparisonCompany(
                    company_name=row.company_name,
                    company_role=row.company_role,
                    status="active",
                ),
            )

    active_competitors = [
        competitor
        for competitor in registry.competitors
        if competitor.status != "retired"
    ]
    active_competitors.sort(key=lambda competitor: (competitor.priority, competitor.competitor_name.lower()))
    for competitor in active_competitors:
        key = (_norm(competitor.competitor_name), "competitor")
        by_key.setdefault(
            key,
            FeatureComparisonCompany(
                company_name=competitor.competitor_name,
                company_role="competitor",
                status=competitor.status,
            ),
        )

    for row in feature_matrix:
        key = (_norm(row.company_name), row.company_role)
        by_key.setdefault(
            key,
            FeatureComparisonCompany(
                company_name=row.company_name,
                company_role=row.company_role,
                status="active",
            ),
        )

    return list(by_key.values())


def _comparison_capabilities(
    *,
    feature_matrix: list[FeatureMatrixAdminRecord],
    planned_capabilities: list[str],
) -> list[str]:
    by_key: dict[str, str] = {}
    for capability in [row.capability_text for row in feature_matrix] + planned_capabilities:
        cleaned = " ".join(str(capability or "").split())
        if not cleaned:
            continue
        by_key.setdefault(_norm(cleaned), cleaned)
    return sorted(by_key.values(), key=lambda value: value.lower())


def _comparison_row(
    capability: str,
    cells: list[FeatureComparisonCell],
    *,
    planned_by_argus: bool = False,
) -> FeatureComparisonRow:
    return FeatureComparisonRow(
        capability_text=capability,
        planned_by_argus=planned_by_argus,
        cells=cells,
        proven_count=sum(1 for cell in cells if cell.position_status == "proven"),
        claimed_count=sum(1 for cell in cells if cell.position_status == "claimed"),
        gap_count=sum(1 for cell in cells if cell.position_status == "gap"),
        disproven_count=sum(1 for cell in cells if cell.position_status == "disproven"),
        unknown_count=sum(1 for cell in cells if cell.position_status == "unknown"),
        evidence_count=sum(cell.evidence_count for cell in cells),
    )


def _unknown_cell(*, capability: str, company: FeatureComparisonCompany) -> FeatureComparisonCell:
    return FeatureComparisonCell(
        company_name=company.company_name,
        company_role=company.company_role,
        position_status="unknown",
        summary=(
            f"No product proof captured for {company.company_name} on {capability} "
            "in this evidence set."
        ),
    )


def _evidence_urls(evidence_refs: list[dict]) -> list[str]:
    urls: list[str] = []
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        source_url = str(ref.get("source_url") or "").strip()
        if source_url:
            urls.append(source_url)
    return urls


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


__all__ = ["build_feature_comparison_state"]
