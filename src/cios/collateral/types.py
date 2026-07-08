"""Shared data types for the collateral generator (Gate 19).

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md, Addendum 2
point 4), Arijit verbatim: "a module that generates marketing collateral
from gathered intel: marketing dashboards and marketing landing pages are
the first two named. Intelligence that ends in a produced asset, not a
paragraph."

A CollateralAsset executes a cios.prescribe.types.Prescription -- it does
not invent its own strategy. The asset's claims trace back to the
prescription's grounding evidence exactly as a Signal or Prescription must
trace back to source evidence (evidence-or-silence extends to collateral).

No DB, no network. These are the value objects the generators build and
return; a caller's repo maps them onto tenant-scoped rows (no schema table
exists yet for this module). Brand is always injected per tenant -- never
a literal in template or prompt code (domain-agnostic, test-enforced).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from cios.prescribe.types import Prescription


class CollateralKind(str, Enum):
    LANDING_PAGE = "landing_page"
    MARKETING_DASHBOARD = "marketing_dashboard"


class ReviewStatus(str, Enum):
    """Assets never auto-publish. A human approves before anything ships."""

    DRAFT = "draft"
    NEEDS_VERIFICATION = "needs_verification"
    APPROVED = "approved"
    REJECTED = "rejected"


class BrandTokens(BaseModel):
    """Per-tenant brand identity, injected -- never hardcoded in a template
    or prompt. Applied to generated HTML as CSS custom properties so no
    generator needs to know a tenant's colors/fonts at authoring time."""

    company_name: str
    primary_color: str = "#003dff"
    secondary_color: str = "#06133f"
    accent_color: str = "#087f5b"
    font_family: str = "Inter, ui-sans-serif, system-ui, sans-serif"
    logo_url: str | None = None

    @model_validator(mode="after")
    def _require_company_name(self) -> "BrandTokens":
        if not self.company_name or not self.company_name.strip():
            raise ValueError("BrandTokens requires a non-empty company_name")
        return self


class CollateralRequest(BaseModel):
    """Input to a collateral generator: which prescription to execute, for
    which tenant, rendered in which brand."""

    tenant_id: int
    kind: CollateralKind
    prescription: Prescription
    brand: BrandTokens

    @model_validator(mode="after")
    def _require_tenant_match(self) -> "CollateralRequest":
        if self.prescription.tenant_id != self.tenant_id:
            raise ValueError(
                "CollateralRequest.tenant_id must match prescription.tenant_id "
                "(tenant-scoped: a request cannot execute another tenant's "
                "prescription)"
            )
        return self


class CollateralAsset(BaseModel):
    """A produced marketing asset (Addendum 2 point 4: "a produced asset,
    not a paragraph"). Invariant: never auto-published -- review_status
    always starts at draft and only a human elevates it to approved."""

    tenant_id: int
    kind: CollateralKind
    html: str
    sources: list[str] = Field(default_factory=list)
    prescription_title: str
    review_status: ReviewStatus = ReviewStatus.DRAFT
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _require_content(self) -> "CollateralAsset":
        if not self.html or not self.html.strip():
            raise ValueError("CollateralAsset requires non-empty html")
        return self
