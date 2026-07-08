"""Candidate validation: is a candidate URL a real, non-duplicate source?

Network access is abstracted behind the injected `Fetcher` protocol so this
module (and its tests) never touch the network directly -- tests use
in-memory fakes. Validation covers three things per
docs/planning/CI-OS-evaluation-plan.md (Source Hunter Evals):

  1. reachability (via the injected fetcher)
  2. source-family classification (blog/changelog/news/... by well-known
     path or content hints)
  3. duplicate rejection against the existing ledger by canonical URL
"""

from __future__ import annotations

from typing import Optional, Protocol
from urllib.parse import urlsplit, urlunsplit

from cios.hunter.types import ValidationResult

# Well-known path segments -> source family, used when the fetcher does not
# supply a stronger classification hint. Longest/most specific match wins.
_WELL_KNOWN_FAMILIES: dict[str, str] = {
    "changelog": "changelog",
    "release-notes": "changelog",
    "releases": "changelog",
    "blog": "blog",
    "news": "news",
    "press": "news",
    "pricing": "pricing",
    "docs": "docs",
    "documentation": "docs",
    "customers": "customer",
    "case-studies": "customer",
    "case-study": "customer",
    "partners": "partner",
    "partner": "partner",
    "marketplace": "marketplace",
    "community": "community",
    "resources": "resources",
    "reports": "resources",
    "careers": "careers",
    "jobs": "careers",
}


def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup: lowercase host, strip default scheme
    noise, strip trailing slash, drop query/fragment (a query-string variant
    of the same page is the same source for ledger purposes)."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def classify_source_family(url: str) -> Optional[str]:
    """Classify by well-known path segment. Returns None if no segment matches
    (caller may fall back to a fetcher-supplied hint or leave unclassified)."""
    path = urlsplit(url).path.lower()
    segments = [seg for seg in path.split("/") if seg]
    for segment in segments:
        if segment in _WELL_KNOWN_FAMILIES:
            return _WELL_KNOWN_FAMILIES[segment]
    return None


class FetchResult:
    """Outcome of an injected fetcher probing a candidate URL."""

    def __init__(
        self,
        reachable: bool,
        http_status: Optional[int] = None,
        source_family_hint: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self.reachable = reachable
        self.http_status = http_status
        self.source_family_hint = source_family_hint
        self.error = error


class Fetcher(Protocol):
    """Injected network boundary. Real implementations live outside this
    package (HTTP client); tests supply in-memory fakes."""

    def fetch(self, url: str) -> FetchResult: ...


class ExistingSourceLookup(Protocol):
    """Read-only ledger lookup used for dedup, kept separate from the
    write-side SourceRepository in lifecycle.py."""

    def exists(self, tenant_id: int, normalized_url: str) -> bool: ...


class SourceValidator:
    """Validates a single candidate URL: reachable, classifiable, and not
    already present in the source ledger."""

    def __init__(self, fetcher: Fetcher, existing_sources: ExistingSourceLookup) -> None:
        self._fetcher = fetcher
        self._existing_sources = existing_sources

    def validate(self, tenant_id: int, url: str) -> ValidationResult:
        normalized = normalize_url(url)

        if self._existing_sources.exists(tenant_id, normalized):
            return ValidationResult(
                accepted=False,
                reason="duplicate_normalized_url",
                url=url,
                normalized_url=normalized,
            )

        result = self._fetcher.fetch(url)
        if not result.reachable:
            return ValidationResult(
                accepted=False,
                reason=result.error or "unreachable",
                url=url,
                normalized_url=normalized,
                http_status=result.http_status,
            )

        family = result.source_family_hint or classify_source_family(url)
        return ValidationResult(
            accepted=True,
            reason="validated",
            url=url,
            normalized_url=normalized,
            source_family=family,
            http_status=result.http_status,
        )
