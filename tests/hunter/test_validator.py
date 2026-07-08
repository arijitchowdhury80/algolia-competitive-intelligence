"""Tests for candidate validation: dedup, classification, reject paths.

All storage/network is in-memory fakes -- no network, no mocking framework.
"""

from __future__ import annotations

from cios.hunter.types import Source, SourceStatus
from cios.hunter.validator import FetchResult, SourceValidator, classify_source_family, normalize_url


class FakeFetcher:
    def __init__(self, results: dict[str, FetchResult]):
        self._results = results

    def fetch(self, url: str) -> FetchResult:
        return self._results.get(url, FetchResult(reachable=False, error="not_stubbed"))


class FakeExistingSourceLookup:
    def __init__(self, sources: list[Source] | None = None):
        self._sources = list(sources or [])

    def exists(self, tenant_id: int, normalized_url: str) -> bool:
        return any(
            s.tenant_id == tenant_id and s.normalized_url == normalized_url
            for s in self._sources
        )


def test_normalize_url_strips_query_fragment_trailing_slash_and_lowercases_host():
    assert normalize_url("https://Blog.Example.com/posts/?utm=x#frag") == "https://blog.example.com/posts"
    assert normalize_url("https://example.com") == "https://example.com/"


def test_classify_source_family_matches_well_known_path():
    assert classify_source_family("https://example.com/blog/post-1") == "blog"
    assert classify_source_family("https://example.com/changelog") == "changelog"
    assert classify_source_family("https://example.com/release-notes/v2") == "changelog"


def test_classify_source_family_returns_none_for_unknown_path():
    assert classify_source_family("https://example.com/whatever/page") is None


def test_validate_rejects_duplicate_normalized_url():
    existing = Source(
        id=1,
        tenant_id=1,
        competitor_id=1,
        source_family="blog",
        url="https://example.com/blog",
        normalized_url="https://example.com/blog",
        status=SourceStatus.ACTIVE,
    )
    fetcher = FakeFetcher({"https://example.com/blog/": FetchResult(reachable=True)})
    validator = SourceValidator(fetcher, FakeExistingSourceLookup([existing]))

    result = validator.validate(tenant_id=1, url="https://example.com/blog/")

    assert result.accepted is False
    assert result.reason == "duplicate_normalized_url"


def test_validate_rejects_unreachable_url():
    fetcher = FakeFetcher({"https://example.com/dead": FetchResult(reachable=False, http_status=404, error="http_error")})
    validator = SourceValidator(fetcher, FakeExistingSourceLookup())

    result = validator.validate(tenant_id=1, url="https://example.com/dead")

    assert result.accepted is False
    assert result.reason == "http_error"
    assert result.http_status == 404


def test_validate_accepts_and_classifies_new_reachable_url():
    fetcher = FakeFetcher({"https://example.com/changelog": FetchResult(reachable=True, http_status=200)})
    validator = SourceValidator(fetcher, FakeExistingSourceLookup())

    result = validator.validate(tenant_id=1, url="https://example.com/changelog")

    assert result.accepted is True
    assert result.source_family == "changelog"
    assert result.normalized_url == "https://example.com/changelog"


def test_validate_prefers_fetcher_supplied_family_hint_over_path_classification():
    fetcher = FakeFetcher(
        {"https://example.com/x": FetchResult(reachable=True, source_family_hint="press")}
    )
    validator = SourceValidator(fetcher, FakeExistingSourceLookup())

    result = validator.validate(tenant_id=1, url="https://example.com/x")

    assert result.source_family == "press"
