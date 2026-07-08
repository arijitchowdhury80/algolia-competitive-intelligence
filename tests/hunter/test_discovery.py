"""Tests for discovery orchestration: fan-out, in-pass dedup, no auto-promotion."""

from __future__ import annotations

from cios.hunter.discovery import DiscoveredUrl, SourceDiscoverer
from cios.hunter.types import Competitor, SourceCandidateStatus


def _competitor() -> Competitor:
    return Competitor(id=1, tenant_id=1, name="Elastic", domain="elastic.co")


class FakeProvider:
    def __init__(self, hits: list[DiscoveredUrl]):
        self._hits = hits

    def discover(self, competitor: Competitor) -> list[DiscoveredUrl]:
        return self._hits


def test_discover_fans_out_across_all_providers():
    sitemap = FakeProvider([DiscoveredUrl("https://elastic.co/blog", source_family="blog")])
    well_known = FakeProvider([DiscoveredUrl("https://elastic.co/changelog", source_family="changelog")])
    discoverer = SourceDiscoverer([sitemap, well_known])

    candidates = discoverer.discover(_competitor())

    urls = {c.url for c in candidates}
    assert urls == {"https://elastic.co/blog", "https://elastic.co/changelog"}


def test_discover_dedups_same_url_proposed_by_multiple_providers():
    provider_a = FakeProvider([DiscoveredUrl("https://elastic.co/blog", reason="sitemap")])
    provider_b = FakeProvider([DiscoveredUrl("https://elastic.co/blog", reason="well_known_path")])
    discoverer = SourceDiscoverer([provider_a, provider_b])

    candidates = discoverer.discover(_competitor())

    assert len(candidates) == 1
    assert candidates[0].reason == "sitemap"  # first provider wins


def test_discover_produces_pending_candidates_not_promoted_sources():
    provider = FakeProvider([DiscoveredUrl("https://elastic.co/news")])
    discoverer = SourceDiscoverer([provider])

    candidates = discoverer.discover(_competitor())

    assert all(c.status == SourceCandidateStatus.PENDING for c in candidates)
    assert all(c.id is None and c.promoted_at is None for c in candidates)


def test_discover_with_no_providers_returns_empty():
    discoverer = SourceDiscoverer([])
    assert discoverer.discover(_competitor()) == []
