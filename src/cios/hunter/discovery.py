"""Discovery orchestration: competitor -> candidate source URLs.

Pure orchestration -- no network in this module. Actual probing (sitemap
parsing, well-known-path HEAD checks, open-web discovery queries) lives in
injected `DiscoveryProvider` implementations outside this package; this
module fans a competitor out to every configured provider, collects raw
URL/reason/confidence tuples, and turns them into `SourceCandidate` rows.

Candidates are NEVER auto-promoted to `Source` rows here -- promotion is a
validator.py + lifecycle.py concern (per eval: "discovery producing
candidates not auto-promoted to sources").
"""

from __future__ import annotations

from __future__ import annotations

from typing import Optional, Protocol

from cios.hunter.types import Competitor, SourceCandidate


class DiscoveredUrl:
    """One raw discovery hit before it becomes a SourceCandidate."""

    def __init__(self, url: str, source_family: Optional[str] = None,
                 confidence: Optional[float] = None, reason: Optional[str] = None) -> None:
        self.url = url
        self.source_family = source_family
        self.confidence = confidence
        self.reason = reason


class DiscoveryProvider(Protocol):
    """A single discovery strategy (sitemap prober, well-known-path prober,
    open-web query, ...). Each provider covers one or more source families;
    the discoverer does not hardcode any single provider or URL."""

    def discover(self, competitor: Competitor) -> list[DiscoveredUrl]: ...


class SourceDiscoverer:
    """Fans a competitor out across all configured discovery providers and
    produces candidate rows. Providers may overlap (two providers proposing
    the same URL); dedup within a single discovery pass by raw URL, so a
    prospective source is proposed once regardless of provider count. Cross-
    ledger dedup against existing sources is the validator's job."""

    def __init__(self, providers: list[DiscoveryProvider]) -> None:
        self._providers = providers

    def discover(self, competitor: Competitor) -> list[SourceCandidate]:
        seen_urls: set[str] = set()
        candidates: list[SourceCandidate] = []

        for provider in self._providers:
            for hit in provider.discover(competitor):
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                candidates.append(
                    SourceCandidate(
                        tenant_id=competitor.tenant_id,
                        competitor_id=competitor.id,
                        url=hit.url,
                        source_family=hit.source_family,
                        confidence=hit.confidence,
                        reason=hit.reason,
                    )
                )

        return candidates
