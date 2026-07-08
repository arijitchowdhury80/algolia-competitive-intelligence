#!/usr/bin/env python3
"""CLI: run the tenant onboarding pipeline for one company.

Usage:
    python scripts/onboard_tenant.py "<company-name>" <domain> [--dry-run] [--execute]

Default (neither flag): runs research + discovery live, prints the plan for
human review, seeds nothing. `--dry-run` is the explicit spelling of that
same behavior. `--execute` additionally seeds the DB (CIOS_DATABASE_URL
required) and prints the config/tenants-sources.yaml block to add.

Per doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md rule 2): the
seller reviews the plan before seeding -- --execute is a deliberate second
step, never the default.

Env:
  CIOS_DATABASE_URL     - Postgres DSN, required for --execute
  CIOS_CLAUDE_SHIM_URL  - claude-shim base URL (default http://127.0.0.1:8663)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.collect.fetcher import HttpContentFetcher  # noqa: E402
from cios.hunter.discovery import SourceDiscoverer  # noqa: E402
from cios.hunter.types import Competitor  # noqa: E402
from cios.hunter.validator import ProbeFetcherAdapter, SourceValidator  # noqa: E402
from cios.hunter.validator import normalize_url  # noqa: E402
from cios.onboard.discovery_providers import SitemapProber, WellKnownPathProber  # noqa: E402
from cios.onboard.research import CompetitorResearcher  # noqa: E402
from cios.onboard.seeder import OnboardSeeder  # noqa: E402
from cios.onboard.types import (  # noqa: E402
    CompetitorPlan,
    OnboardPlan,
    OnboardRequest,
    PlannedSource,
    slugify,
)
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider  # noqa: E402


class _NoOpExistingSources:
    """Plan-building runs before we know the tenant_id (tenant doesn't exist
    yet on first onboard). Dedup against the real ledger happens for free on
    the DB-backed re-run via SourceLifecycle's own upsert-by-normalized-url;
    this stub only needs to satisfy the Validator's ExistingSourceLookup
    Protocol for the plan-building pass."""

    def exists(self, tenant_id: int, normalized_url: str) -> bool:
        return False


async def build_plan(request: OnboardRequest, shim_url: str) -> OnboardPlan:
    model = ClaudeCliShimProvider(model_alias="sonnet", base_url=shim_url)
    researcher = CompetitorResearcher(model)
    candidates = await researcher.research(request)

    content_fetcher = HttpContentFetcher(timeout=15.0, retries=1)
    probe = ProbeFetcherAdapter(content_fetcher)
    validator = SourceValidator(fetcher=probe, existing_sources=_NoOpExistingSources())
    discoverer = SourceDiscoverer([WellKnownPathProber(content_fetcher), SitemapProber(content_fetcher)])

    tenant_slug = slugify(request.company_name)
    competitor_plans: list[CompetitorPlan] = []
    for idx, candidate in enumerate(candidates, start=1):
        # tenant_id/id are not yet real DB ids at plan-building time; 0 is a
        # placeholder the discoverer only uses to stamp SourceCandidate rows,
        # which this script discards in favor of PlannedSource.
        fake_competitor = Competitor(id=idx, tenant_id=0, name=candidate.name, domain=candidate.domain)
        discovered = discoverer.discover(fake_competitor)
        planned_sources: list[PlannedSource] = []
        for hit in discovered:
            result = validator.validate(tenant_id=0, url=hit.url)
            if not result.accepted:
                continue
            planned_sources.append(
                PlannedSource(
                    url=result.url,
                    source_family=result.source_family or hit.source_family,
                    reason=hit.reason or "onboard_discovery",
                    http_status=result.http_status,
                )
            )
        competitor_plans.append(CompetitorPlan(candidate=candidate, sources=planned_sources))

    own_brand_sources: list[PlannedSource] = []
    own_brand_result = validator.validate(tenant_id=0, url=f"https://{request.domain.strip('/')}/blog")
    if own_brand_result.accepted:
        own_brand_sources.append(
            PlannedSource(
                url=own_brand_result.url,
                source_family="own_blog",
                reason="onboard_own_brand",
                http_status=own_brand_result.http_status,
            )
        )

    return OnboardPlan(
        tenant_slug=tenant_slug,
        tenant_name=request.company_name,
        domain=request.domain,
        competitors=competitor_plans,
        own_brand_sources=own_brand_sources,
    )


def print_plan(plan: OnboardPlan) -> None:
    print(f"\n=== Onboard plan: {plan.tenant_name} ({plan.tenant_slug}) ===")
    print(f"Domain: {plan.domain}")
    print(f"Competitors: {plan.competitor_count()}  Sources: {plan.source_count()}\n")
    for comp_plan in plan.competitors:
        c = comp_plan.candidate
        print(f"- {c.name} ({c.domain or 'domain unknown'})")
        print(f"    why: {c.why}")
        if not comp_plan.sources:
            print("    sources: none discovered")
        for src in comp_plan.sources:
            print(f"    source [{src.source_family or 'unclassified'}]: {src.url}")
    if plan.own_brand_sources:
        print("\nOwn-brand sources:")
        for src in plan.own_brand_sources:
            print(f"  [{src.source_family}]: {src.url}")
    print()


def execute_plan(plan: OnboardPlan, database_url: str) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from cios.db.repos.sources import PgSourceRepository
    from cios.db.session import tenant_context
    from cios.hunter.lifecycle import SourceLifecycle

    class PgTenantRepository:
        def __init__(self, conn) -> None:
            self._conn = conn

        def upsert(self, name: str, slug: str, domain: Optional[str]) -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO tenants (name, slug, primary_domain)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE SET primary_domain = EXCLUDED.primary_domain
                    RETURNING id
                    """,
                    (name, slug, domain),
                )
                return cur.fetchone()["id"]

    class PgCompetitorRepository:
        def __init__(self, conn) -> None:
            self._conn = conn

        def upsert(self, tenant_id: int, name: str, domain: Optional[str]) -> int:
            with tenant_context(self._conn, tenant_id):
                with self._conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        INSERT INTO competitors (tenant_id, name, domain, category, priority, status)
                        VALUES (%s, %s, %s, 'unclassified', 3, 'active')
                        ON CONFLICT (tenant_id, name) DO UPDATE SET domain = EXCLUDED.domain
                        RETURNING id
                        """,
                        (tenant_id, name, domain),
                    )
                    return cur.fetchone()["id"]

    class NoOpOwnBrandRepository:
        """No dedicated own-brand table wired to this script yet -- own-brand
        sources are surfaced only via the printed yaml block for now; a
        DB-backed OwnBrandRepository lands with the ownbrand module's own
        onboarding hook, not duplicated here."""

        def upsert(self, tenant_id: int, name: str, source_type: str, url: str) -> None:
            return None

    conn = psycopg.connect(database_url, autocommit=True)
    try:
        source_repo = PgSourceRepository(conn)

        class _ExistingLookup:
            def exists(self, tenant_id: int, normalized: str) -> bool:
                return source_repo.get_by_normalized_url(tenant_id, normalized) is not None

        lifecycle = SourceLifecycle(sources=source_repo, health_events=lambda ev: None)
        seeder = OnboardSeeder(
            tenants=PgTenantRepository(conn),
            competitors=PgCompetitorRepository(conn),
            lifecycle=lifecycle,
            own_brand=NoOpOwnBrandRepository(),
        )
        result = seeder.seed(plan)
    finally:
        conn.close()

    print(f"\nSeeded tenant '{result.tenant_slug}' (id={result.tenant_id}): "
          f"{result.competitors_seeded} competitors, {result.sources_seeded} sources.")
    print("\nAdd this block to config/tenants-sources.yaml:\n")
    print(result.yaml_block)


def main() -> None:
    parser = argparse.ArgumentParser(description="Onboard a new CI-OS tenant.")
    parser.add_argument("company_name")
    parser.add_argument("domain")
    parser.add_argument("--dry-run", action="store_true", help="build and print the plan only (default behavior)")
    parser.add_argument("--execute", action="store_true", help="seed the DB and print the yaml block")
    args = parser.parse_args()

    request = OnboardRequest(company_name=args.company_name, domain=args.domain)
    shim_url = os.environ.get("CIOS_CLAUDE_SHIM_URL", "http://127.0.0.1:8663")
    plan = asyncio.run(build_plan(request, shim_url))
    print_plan(plan)

    if args.execute:
        database_url = os.environ.get("CIOS_DATABASE_URL")
        if not database_url:
            print("ERROR: --execute requires CIOS_DATABASE_URL", file=sys.stderr)
            sys.exit(1)
        execute_plan(plan, database_url)
    elif not args.dry_run:
        print("(dry run -- pass --execute to seed the DB)")


if __name__ == "__main__":
    main()
