"""Tests for WellKnownPathProber and SitemapProber: fake fetcher, no network."""

from __future__ import annotations

from cios.collect.types import ContentFetchResult, FetchStatus
from cios.hunter.types import Competitor
from cios.onboard.discovery_providers import SitemapProber, WellKnownPathProber

VALID_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/blog</loc></url>
  <url><loc>https://example.com/changelog</loc></url>
</urlset>
"""


class FakeFetcher:
    def __init__(self, results: dict[str, ContentFetchResult]):
        self._results = results

    def fetch_content(self, url: str) -> ContentFetchResult:
        return self._results.get(url, ContentFetchResult(status=FetchStatus.ERROR, error="not_stubbed"))


def _competitor(domain: str = "example.com") -> Competitor:
    return Competitor(id=1, tenant_id=1, name="Acme", domain=domain)


def test_well_known_path_prober_returns_only_reachable_paths():
    fetcher = FakeFetcher(
        {
            "https://example.com/blog": ContentFetchResult(status=FetchStatus.OK, text="blog"),
            "https://example.com/changelog": ContentFetchResult(status=FetchStatus.ERROR, error="404"),
        }
    )
    prober = WellKnownPathProber(fetcher, paths={"/blog": "blog", "/changelog": "changelog"})

    hits = prober.discover(_competitor())

    assert [h.url for h in hits] == ["https://example.com/blog"]
    assert hits[0].source_family == "blog"


def test_well_known_path_prober_returns_empty_without_domain():
    prober = WellKnownPathProber(FakeFetcher({}))
    competitor = Competitor(id=1, tenant_id=1, name="Acme", domain=None)
    assert prober.discover(competitor) == []


def test_sitemap_prober_extracts_locs():
    fetcher = FakeFetcher(
        {"https://example.com/sitemap.xml": ContentFetchResult(status=FetchStatus.OK, text=VALID_SITEMAP)}
    )
    prober = SitemapProber(fetcher)

    hits = prober.discover(_competitor())

    assert {h.url for h in hits} == {"https://example.com/blog", "https://example.com/changelog"}


def test_sitemap_prober_caps_candidates():
    urls = "".join(f"<url><loc>https://example.com/p{i}</loc></url>" for i in range(50))
    xml = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    fetcher = FakeFetcher({"https://example.com/sitemap.xml": ContentFetchResult(status=FetchStatus.OK, text=xml)})
    prober = SitemapProber(fetcher, cap=5)

    hits = prober.discover(_competitor())

    assert len(hits) == 5


def test_sitemap_prober_handles_malformed_xml_defensively():
    fetcher = FakeFetcher(
        {"https://example.com/sitemap.xml": ContentFetchResult(status=FetchStatus.OK, text="<not-xml<<<")}
    )
    prober = SitemapProber(fetcher)

    assert prober.discover(_competitor()) == []


def test_sitemap_prober_handles_missing_sitemap():
    fetcher = FakeFetcher({"https://example.com/sitemap.xml": ContentFetchResult(status=FetchStatus.ERROR, error="404")})
    prober = SitemapProber(fetcher)

    assert prober.discover(_competitor()) == []
