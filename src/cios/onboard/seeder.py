"""Turns a reviewed OnboardPlan into ledger reality: tenant, competitors,
validated sources, own-brand entries -- plus the config/tenants-sources.yaml
block a human adds for the new tenant.

Idempotent by construction: tenant upsert is keyed by slug (deterministic
from company name, see types.slugify), competitor upsert is keyed by
(tenant_id, name), and source upsert reuses hunter.lifecycle.SourceLifecycle,
which is keyed by (tenant_id, normalized_url). Re-running the same plan
twice seeds the same rows, not duplicates. A company swap produces a
different slug -> a different tenant_id -> the old tenant's rows are never
touched.
"""

from __future__ import annotations

from typing import Optional, Protocol

import yaml as _yaml

from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import ValidationResult
from cios.hunter.validator import normalize_url
from cios.onboard.types import OnboardPlan, OnboardResult


class TenantRepository(Protocol):
    def upsert(self, name: str, slug: str, domain: Optional[str]) -> int:  # returns tenant_id
        ...


class CompetitorRepository(Protocol):
    def upsert(self, tenant_id: int, name: str, domain: Optional[str]) -> int:  # returns competitor_id
        ...


class OwnBrandRepository(Protocol):
    def upsert(self, tenant_id: int, name: str, source_type: str, url: str) -> None: ...


class OnboardSeeder:
    def __init__(
        self,
        tenants: TenantRepository,
        competitors: CompetitorRepository,
        lifecycle: SourceLifecycle,
        own_brand: OwnBrandRepository,
    ) -> None:
        self._tenants = tenants
        self._competitors = competitors
        self._lifecycle = lifecycle
        self._own_brand = own_brand

    def seed(self, plan: OnboardPlan) -> OnboardResult:
        tenant_id = self._tenants.upsert(plan.tenant_name, plan.tenant_slug, plan.domain)

        competitors_seeded = 0
        sources_seeded = 0
        for comp_plan in plan.competitors:
            competitor_id = self._competitors.upsert(
                tenant_id, comp_plan.candidate.name, comp_plan.candidate.domain
            )
            competitors_seeded += 1
            for planned_source in comp_plan.sources:
                validation = ValidationResult(
                    accepted=True,
                    reason=planned_source.reason,
                    url=planned_source.url,
                    normalized_url=normalize_url(planned_source.url),
                    source_family=planned_source.source_family,
                    http_status=planned_source.http_status,
                )
                self._lifecycle.upsert_validated(tenant_id, competitor_id, validation)
                sources_seeded += 1

        own_brand_seeded = 0
        for ob_source in plan.own_brand_sources:
            self._own_brand.upsert(
                tenant_id, plan.tenant_name, ob_source.source_family or "own_blog", ob_source.url
            )
            own_brand_seeded += 1

        return OnboardResult(
            tenant_slug=plan.tenant_slug,
            tenant_id=tenant_id,
            competitors_seeded=competitors_seeded,
            sources_seeded=sources_seeded,
            own_brand_seeded=own_brand_seeded,
            yaml_block=render_tenant_yaml_block(plan),
        )


def render_tenant_yaml_block(plan: OnboardPlan) -> str:
    """Renders the config/tenants-sources.yaml block for this tenant, in the
    same shape as the file's existing tenant entries (see
    config/tenants-sources.yaml): top-level `<slug>: [{name, domain, url,
    family}, ...]` plus an `own_brand.<slug>: [...]` entry. One competitor
    source (the first accepted one) is emitted per competitor, matching the
    file's existing <=1-line-per-competitor convention for the production
    runner's per-cycle plan; writing the file is the caller's choice, not
    this function's."""
    competitor_rows: list[dict] = []
    for comp_plan in plan.competitors:
        if not comp_plan.sources:
            continue
        src = comp_plan.sources[0]
        competitor_rows.append(
            {
                "name": comp_plan.candidate.name,
                "domain": comp_plan.candidate.domain,
                "url": src.url,
                "family": src.source_family or "blog",
            }
        )

    doc: dict = {plan.tenant_slug: competitor_rows}
    if plan.own_brand_sources:
        doc["own_brand"] = {
            plan.tenant_slug: [
                {
                    "name": f"{plan.tenant_name} {(s.source_family or 'own_blog').replace('_', ' ').title()}",
                    "source_type": s.source_family or "own_blog",
                    "url": s.url,
                }
                for s in plan.own_brand_sources
            ]
        }
    return _yaml.dump(doc, sort_keys=False, default_flow_style=False)
