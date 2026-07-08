"""Shared data types for the tenant onboarding pipeline.

Domain-agnostic (doctrine rule 1): nothing here names a vertical, a vendor,
or Algolia. `OnboardRequest` describes any company; the pipeline researches
its real competitors and discovers their public sources the same way
regardless of what business the tenant is in.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


def slugify(name: str) -> str:
    """Deterministic tenant slug from a company name: lowercase, alnum runs
    joined by single hyphens. Same input always produces the same slug, so a
    re-run against the same company name always targets the same tenant
    (idempotent); a different company name always produces a different slug
    (company swap = a new tenant, old tenant untouched)."""
    lowered = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "tenant"


class OnboardRequest(BaseModel):
    """The seller's input: the buyer's company, nothing else required."""

    company_name: str
    domain: str
    seed_competitors: list[str] = Field(default_factory=list)
    vertical_hint: Optional[str] = None


class CompetitorCandidate(BaseModel):
    """One evidence-grounded competitor proposal from research.py.

    `why` must be a one-line, evidence-grounded justification -- never a
    generic filler sentence -- per Addendum 3.3.
    """

    name: str
    domain: Optional[str] = None
    why: str


class PlannedSource(BaseModel):
    """A discovered-and-validated source URL, ready to seed. Mirrors the
    fields SourceLifecycle.upsert_validated needs from a ValidationResult so
    the seeder can hand it straight through without re-deriving anything."""

    url: str
    source_family: Optional[str] = None
    reason: str = "onboard_discovery"
    http_status: Optional[int] = None


class CompetitorPlan(BaseModel):
    """One competitor plus the source candidates discovered for it."""

    candidate: CompetitorCandidate
    sources: list[PlannedSource] = Field(default_factory=list)


class OnboardPlan(BaseModel):
    """The full seller-reviewable plan for one company-swap run."""

    tenant_slug: str
    tenant_name: str
    domain: str
    competitors: list[CompetitorPlan] = Field(default_factory=list)
    own_brand_sources: list[PlannedSource] = Field(default_factory=list)

    def competitor_count(self) -> int:
        return len(self.competitors)

    def source_count(self) -> int:
        return sum(len(c.sources) for c in self.competitors) + len(self.own_brand_sources)


class OnboardResult(BaseModel):
    """What actually got seeded when a plan is executed."""

    tenant_slug: str
    tenant_id: Optional[int] = None
    competitors_seeded: int = 0
    sources_seeded: int = 0
    own_brand_seeded: int = 0
    yaml_block: str = ""
