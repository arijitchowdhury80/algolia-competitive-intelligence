"""Own-brand collection: tenant -> BrandObservation rows.

Pure orchestration -- no network in this module, same pattern as
execspeech/scanner.py and hunter/discovery.py. Retrieval of the tenant's own
sources (blog, newsroom, changelog, press releases, review sites, analyst
mentions) reuses the existing collect layer boundary: `ContentFetcher` for
raw page text (src/cios/collect/fetcher.py) and `resolve_article_links` for
index/listing pages (src/cios/collect/article_resolver.py). Nothing here
duplicates that fetching logic.
"""

from __future__ import annotations

from typing import Optional, Protocol

from cios.collect.article_resolver import resolve_article_links
from cios.collect.fetcher import ContentFetcher
from cios.collect.types import ContentFetchResult, FetchStatus
from cios.ownbrand.types import (
    BrandObservation,
    OwnBrandSource,
    OwnBrandSourceSpec,
    RawBrandStatement,
)

DEFAULT_ARTICLE_FETCH_CAP = 5

# Source families whose page is a listing/index that needs article-link
# resolution before there is any statement text to extract from. Mirrors
# collect/runner.py's INDEX_SOURCE_FAMILIES convention for this module's
# own source-type vocabulary.
INDEX_SOURCE_TYPES = {
    OwnBrandSource.OWN_BLOG,
    OwnBrandSource.NEWSROOM,
    OwnBrandSource.CHANGELOG,
}


class StatementProvider(Protocol):
    """A retrieval strategy that turns fetched page text into candidate
    statements about the tenant's own brand (e.g. a review-site or analyst-
    mention search, as opposed to first-party page fetching handled inline
    below). Optional -- the collector also fetches first-party sources
    directly via the injected ContentFetcher."""

    def fetch(self, tenant_id: int, spec: OwnBrandSourceSpec) -> list[RawBrandStatement]: ...


class OwnBrandCollector:
    """Fetches each configured own-brand source for a tenant and produces
    BrandObservation rows. Tenant-scoped: every observation it returns
    carries the tenant_id it was collected for, and a source belonging to a
    different tenant is never mixed in (the caller supplies one tenant's
    sources per call, but the guard below defends against a misrouted
    provider result the same way execspeech.scanner defends tenant/
    competitor mismatches)."""

    def __init__(
        self,
        content_fetcher: ContentFetcher,
        providers: Optional[list[StatementProvider]] = None,
        article_fetch_cap: int = DEFAULT_ARTICLE_FETCH_CAP,
    ) -> None:
        self._content_fetcher = content_fetcher
        self._providers = providers or []
        self._article_fetch_cap = article_fetch_cap

    def collect(
        self, tenant_id: int, sources: list[OwnBrandSourceSpec]
    ) -> list[BrandObservation]:
        observations: list[BrandObservation] = []
        seen_quotes: set[str] = set()

        for spec in sources:
            observations.extend(
                self._dedup(self._collect_first_party(tenant_id, spec), seen_quotes)
            )

        for provider in self._providers:
            for spec in sources:
                statements = provider.fetch(tenant_id, spec)
                observations.extend(
                    self._dedup(
                        (self._to_observation(s) for s in statements if s.tenant_id == tenant_id),
                        seen_quotes,
                    )
                )

        return observations

    # -- internals -----------------------------------------------------

    def _collect_first_party(
        self, tenant_id: int, spec: OwnBrandSourceSpec
    ) -> list[BrandObservation]:
        """First-party pages (own blog/newsroom/changelog/press) are fetched
        directly -- no separate provider is required to see what the
        tenant's own site says about itself."""
        fetch_result = self._content_fetcher.fetch_content(spec.url)
        if fetch_result.status != FetchStatus.OK:
            return []

        page_urls = [spec.url]
        if spec.source_type in INDEX_SOURCE_TYPES:
            article_urls = resolve_article_links(
                fetch_result.raw_html or fetch_result.text, spec.url
            )[: self._article_fetch_cap]
            if article_urls:
                page_urls = article_urls

        observations: list[BrandObservation] = []
        for url in page_urls:
            result = fetch_result if url == spec.url else self._content_fetcher.fetch_content(url)
            if result.status != FetchStatus.OK or not result.text.strip():
                continue
            quote = self._lead_statement(result)
            if not quote:
                continue
            observations.append(
                BrandObservation(
                    tenant_id=tenant_id,
                    source_type=spec.source_type,
                    source_url=url,
                    quote=quote,
                )
            )
        return observations

    @staticmethod
    def _lead_statement(result: ContentFetchResult, max_chars: int = 400) -> str:
        text = result.text.strip()
        return text[:max_chars] if text else ""

    @staticmethod
    def _to_observation(statement: RawBrandStatement) -> Optional[BrandObservation]:
        if not statement.quote or not statement.quote.strip():
            return None
        if not statement.source_url or not statement.source_url.strip():
            return None
        return BrandObservation(
            tenant_id=statement.tenant_id,
            source_type=statement.source_type,
            source_url=statement.source_url,
            published_at=statement.published_at,
            quote=statement.quote,
            claim=statement.claim,
        )

    @staticmethod
    def _dedup(
        candidates, seen_quotes: set[str]
    ) -> list[BrandObservation]:
        out: list[BrandObservation] = []
        for obs in candidates:
            if obs is None:
                continue
            key = " ".join(obs.quote.strip().lower().split())
            if key in seen_quotes:
                continue
            seen_quotes.add(key)
            out.append(obs)
        return out
