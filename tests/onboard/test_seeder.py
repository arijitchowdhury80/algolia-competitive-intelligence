"""Tests for OnboardSeeder: idempotent tenant/competitor/source seeding and
yaml rendering. All storage is in-memory fakes -- no DB, no network.
"""

from __future__ import annotations

from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import Source, SourceHealthEvent
from cios.hunter.validator import normalize_url
from cios.onboard.seeder import OnboardSeeder, render_tenant_yaml_block
from cios.onboard.types import CompetitorCandidate, CompetitorPlan, OnboardPlan, PlannedSource, slugify


class FakeTenantRepo:
    def __init__(self):
        self.by_slug: dict[str, int] = {}
        self._next_id = 1
        self.upsert_calls = 0

    def upsert(self, name: str, slug: str, domain):
        self.upsert_calls += 1
        if slug not in self.by_slug:
            self.by_slug[slug] = self._next_id
            self._next_id += 1
        return self.by_slug[slug]


class FakeCompetitorRepo:
    def __init__(self):
        self.by_key: dict[tuple[int, str], int] = {}
        self._next_id = 1
        self.upsert_calls = 0

    def upsert(self, tenant_id: int, name: str, domain):
        self.upsert_calls += 1
        key = (tenant_id, name)
        if key not in self.by_key:
            self.by_key[key] = self._next_id
            self._next_id += 1
        return self.by_key[key]


class FakeSourceRepo:
    def __init__(self):
        self._sources: dict[tuple[int, str], Source] = {}
        self._next_id = 1

    def get_by_normalized_url(self, tenant_id: int, normalized_url: str):
        return self._sources.get((tenant_id, normalized_url))

    def upsert(self, source: Source) -> Source:
        key = (source.tenant_id, source.normalized_url)
        if key not in self._sources:
            source = source.model_copy(update={"id": self._next_id})
            self._next_id += 1
        else:
            source = source.model_copy(update={"id": self._sources[key].id})
        self._sources[key] = source
        return source


class FakeOwnBrandRepo:
    def __init__(self):
        self.upserts: list[tuple] = []

    def upsert(self, tenant_id: int, name: str, source_type: str, url: str) -> None:
        self.upserts.append((tenant_id, name, source_type, url))


def _plan(company="Acme", domain="acme.com") -> OnboardPlan:
    return OnboardPlan(
        tenant_slug=slugify(company),
        tenant_name=company,
        domain=domain,
        competitors=[
            CompetitorPlan(
                candidate=CompetitorCandidate(name="Rival", domain="rival.com", why="same buyers"),
                sources=[PlannedSource(url="https://rival.com/blog", source_family="blog")],
            )
        ],
        own_brand_sources=[PlannedSource(url="https://acme.com/blog", source_family="own_blog")],
    )


def _build_seeder():
    tenants = FakeTenantRepo()
    competitors = FakeCompetitorRepo()
    source_repo = FakeSourceRepo()
    health_events: list[SourceHealthEvent] = []
    lifecycle = SourceLifecycle(sources=source_repo, health_events=health_events.append)
    own_brand = FakeOwnBrandRepo()
    seeder = OnboardSeeder(tenants=tenants, competitors=competitors, lifecycle=lifecycle, own_brand=own_brand)
    return seeder, tenants, competitors, source_repo, own_brand


def test_seed_creates_tenant_competitor_and_source():
    seeder, tenants, competitors, source_repo, own_brand = _build_seeder()
    plan = _plan()

    result = seeder.seed(plan)

    assert result.tenant_slug == "acme"
    assert result.competitors_seeded == 1
    assert result.sources_seeded == 1
    assert result.own_brand_seeded == 1
    assert own_brand.upserts == [(result.tenant_id, "Acme", "own_blog", "https://acme.com/blog")]
    assert source_repo.get_by_normalized_url(result.tenant_id, normalize_url("https://rival.com/blog")) is not None


def test_seed_is_idempotent_on_rerun():
    seeder, tenants, competitors, source_repo, _ = _build_seeder()
    plan = _plan()

    first = seeder.seed(plan)
    second = seeder.seed(plan)

    assert first.tenant_id == second.tenant_id
    assert tenants.upsert_calls == 2  # called twice, but resolves to the same id
    assert len(tenants.by_slug) == 1
    assert len(competitors.by_key) == 1
    assert len(source_repo._sources) == 1


def test_company_swap_creates_new_tenant_leaves_old_untouched():
    seeder, tenants, competitors, source_repo, _ = _build_seeder()
    first = seeder.seed(_plan(company="Acme", domain="acme.com"))
    second = seeder.seed(_plan(company="Globex", domain="globex.com"))

    assert first.tenant_id != second.tenant_id
    assert first.tenant_slug != second.tenant_slug
    # old tenant's rows are still present, untouched by the new tenant's seed
    assert source_repo.get_by_normalized_url(first.tenant_id, normalize_url("https://rival.com/blog")) is not None


def test_render_yaml_block_shape():
    plan = _plan()
    text = render_tenant_yaml_block(plan)

    assert "acme:" in text
    assert "rival.com" in text
    assert "own_brand:" in text
    assert "acme.com/blog" in text


def test_render_yaml_block_skips_competitor_with_no_sources():
    plan = OnboardPlan(
        tenant_slug="acme",
        tenant_name="Acme",
        domain="acme.com",
        competitors=[
            CompetitorPlan(candidate=CompetitorCandidate(name="NoSources", domain="none.com", why="x"), sources=[])
        ],
    )
    text = render_tenant_yaml_block(plan)
    assert "NoSources" not in text


def test_slugify_is_deterministic_and_url_safe():
    assert slugify("Acme, Inc.") == "acme-inc"
    assert slugify("Acme, Inc.") == slugify("  acme, inc.  ")
