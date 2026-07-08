"""Collector tests: first-party fetch, tenant scoping, dedup. In-memory
fakes only -- no network."""

from __future__ import annotations

from cios.collect.types import ContentFetchResult, FetchStatus
from cios.ownbrand.collector import OwnBrandCollector
from cios.ownbrand.types import OwnBrandSource, OwnBrandSourceSpec, RawBrandStatement


class FakeContentFetcher:
    def __init__(self, pages: dict[str, ContentFetchResult]) -> None:
        self._pages = pages

    def fetch_content(self, url: str) -> ContentFetchResult:
        return self._pages.get(
            url, ContentFetchResult(status=FetchStatus.ERROR, error="not found")
        )


class FakeStatementProvider:
    def __init__(self, statements: list[RawBrandStatement]) -> None:
        self._statements = statements

    def fetch(self, tenant_id: int, spec: OwnBrandSourceSpec) -> list[RawBrandStatement]:
        return self._statements


def test_collects_first_party_page_as_observation() -> None:
    fetcher = FakeContentFetcher(
        {
            "https://example.com/press/a": ContentFetchResult(
                status=FetchStatus.OK,
                text="Acme announced record growth in its search platform.",
            )
        }
    )
    collector = OwnBrandCollector(fetcher)
    spec = OwnBrandSourceSpec(
        tenant_id=1, source_type=OwnBrandSource.PRESS_RELEASE, url="https://example.com/press/a"
    )

    observations = collector.collect(1, [spec])

    assert len(observations) == 1
    assert observations[0].tenant_id == 1
    assert observations[0].source_url == "https://example.com/press/a"
    assert observations[0].quote


def test_failed_fetch_produces_no_observation() -> None:
    fetcher = FakeContentFetcher({})
    collector = OwnBrandCollector(fetcher)
    spec = OwnBrandSourceSpec(
        tenant_id=1, source_type=OwnBrandSource.OWN_BLOG, url="https://example.com/blog"
    )

    assert collector.collect(1, [spec]) == []


def test_dedups_identical_quotes_across_sources() -> None:
    same_text = "Acme is the fastest search platform on the market."
    fetcher = FakeContentFetcher(
        {
            "https://example.com/a": ContentFetchResult(status=FetchStatus.OK, text=same_text),
            "https://example.com/b": ContentFetchResult(status=FetchStatus.OK, text=same_text),
        }
    )
    collector = OwnBrandCollector(fetcher)
    specs = [
        OwnBrandSourceSpec(tenant_id=1, source_type=OwnBrandSource.OWN_BLOG, url="https://example.com/a"),
        OwnBrandSourceSpec(tenant_id=1, source_type=OwnBrandSource.PRESS_RELEASE, url="https://example.com/b"),
    ]

    observations = collector.collect(1, specs)

    assert len(observations) == 1


def test_provider_statement_from_wrong_tenant_is_dropped() -> None:
    fetcher = FakeContentFetcher({})
    provider = FakeStatementProvider(
        [
            RawBrandStatement(
                tenant_id=2,
                source_type=OwnBrandSource.REVIEW_SITE,
                source_url="https://reviews.example.com/acme",
                quote="Users love how fast Acme search is.",
            )
        ]
    )
    collector = OwnBrandCollector(fetcher, providers=[provider])
    spec = OwnBrandSourceSpec(
        tenant_id=1, source_type=OwnBrandSource.REVIEW_SITE, url="https://reviews.example.com/acme"
    )

    observations = collector.collect(1, [spec])

    assert observations == []


def test_provider_statement_missing_quote_is_dropped() -> None:
    fetcher = FakeContentFetcher({})
    provider = FakeStatementProvider(
        [
            RawBrandStatement(
                tenant_id=1,
                source_type=OwnBrandSource.ANALYST_MENTION,
                source_url="https://analyst.example.com/report",
                quote=None,
                claim="Analysts see Acme as a market leader.",
            )
        ]
    )
    collector = OwnBrandCollector(fetcher, providers=[provider])
    spec = OwnBrandSourceSpec(
        tenant_id=1, source_type=OwnBrandSource.ANALYST_MENTION, url="https://analyst.example.com/report"
    )

    observations = collector.collect(1, [spec])

    assert observations == []


def test_provider_statement_with_quote_and_tenant_is_kept() -> None:
    fetcher = FakeContentFetcher({})
    provider = FakeStatementProvider(
        [
            RawBrandStatement(
                tenant_id=1,
                source_type=OwnBrandSource.ANALYST_MENTION,
                source_url="https://analyst.example.com/report",
                quote="Acme leads the market in search relevance.",
            )
        ]
    )
    collector = OwnBrandCollector(fetcher, providers=[provider])
    spec = OwnBrandSourceSpec(
        tenant_id=1, source_type=OwnBrandSource.ANALYST_MENTION, url="https://analyst.example.com/report"
    )

    observations = collector.collect(1, [spec])

    assert len(observations) == 1
    assert observations[0].source_type == OwnBrandSource.ANALYST_MENTION
