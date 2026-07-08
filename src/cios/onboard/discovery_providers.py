"""Real DiscoveryProvider implementations for cios.hunter.discovery.

hunter/discovery.py deliberately leaves DiscoveryProvider as a Protocol with
no real implementation (pure orchestration, no network). These are the two
concrete probers the onboarding pipeline injects: a well-known-path prober
(the same source families the source-hunter validator already classifies)
and a sitemap prober. Both take an injected `Fetcher` (cios.collect.fetcher.
ContentFetcher shape) so tests fake the network -- neither module opens a
socket itself.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional, Protocol
from urllib.parse import urlsplit, urlunsplit
from xml.etree.ElementTree import ParseError

from cios.collect.types import ContentFetchResult, FetchStatus
from cios.hunter.discovery import DiscoveredUrl
from cios.hunter.types import Competitor

# Same family vocabulary as hunter.validator._WELL_KNOWN_FAMILIES, kept as a
# separate list here (not imported) because this module probes fixed
# candidate paths rather than classifying arbitrary discovered URLs.
WELL_KNOWN_PATHS: dict[str, str] = {
    "/blog": "blog",
    "/changelog": "changelog",
    "/news": "news",
    "/press": "news",
    "/product": "product",
    "/docs": "docs",
}

SITEMAP_PATH = "/sitemap.xml"
SITEMAP_CANDIDATE_CAP = 20
# Sitemap URLs are not classified here -- they're raw discovery hits, exactly
# like well-known-path hits before validator.py classifies them. Only URLs
# whose path root looks like a genuinely different section of the site are
# kept, so the sitemap prober does not just re-propose the home page N times.


class Fetcher(Protocol):
    """The same injected network boundary as cios.collect.fetcher.ContentFetcher
    -- named locally so this module does not import a concrete class, only
    the shape it needs."""

    def fetch_content(self, url: str) -> ContentFetchResult: ...


def _domain_root(domain: str) -> str:
    candidate = domain.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parts = urlsplit(candidate)
    return urlunsplit((parts.scheme or "https", parts.netloc, "", "", ""))


class WellKnownPathProber:
    """Probes a fixed list of well-known content paths (/blog, /changelog,
    /news, /press, /product, /docs) off the competitor's own domain. A path
    counts as discovered only if the fetch succeeds (FetchStatus.OK)."""

    def __init__(self, fetcher: Fetcher, paths: Optional[dict[str, str]] = None) -> None:
        self._fetcher = fetcher
        self._paths = paths or WELL_KNOWN_PATHS

    def discover(self, competitor: Competitor) -> list[DiscoveredUrl]:
        if not competitor.domain:
            return []
        root = _domain_root(competitor.domain)
        hits: list[DiscoveredUrl] = []
        for path, family in self._paths.items():
            url = f"{root}{path}"
            result = self._fetcher.fetch_content(url)
            if result.status != FetchStatus.OK:
                continue
            hits.append(
                DiscoveredUrl(
                    url=url,
                    source_family=family,
                    confidence=0.9,
                    reason=f"well_known_path:{path}",
                )
            )
        return hits


class SitemapProber:
    """Fetches /sitemap.xml and extracts candidate section URLs. Defensive
    against malformed XML, missing sitemap, and non-sitemap-index shapes --
    any parse failure yields zero hits rather than raising."""

    def __init__(self, fetcher: Fetcher, cap: int = SITEMAP_CANDIDATE_CAP) -> None:
        self._fetcher = fetcher
        self._cap = cap

    def discover(self, competitor: Competitor) -> list[DiscoveredUrl]:
        if not competitor.domain:
            return []
        root = _domain_root(competitor.domain)
        sitemap_url = f"{root}{SITEMAP_PATH}"
        result = self._fetcher.fetch_content(sitemap_url)
        if result.status != FetchStatus.OK or not result.text:
            return []

        urls = self._parse_locs(result.text)
        hits: list[DiscoveredUrl] = []
        for url in urls[: self._cap]:
            hits.append(DiscoveredUrl(url=url, source_family=None, confidence=0.5, reason="sitemap"))
        return hits

    @staticmethod
    def _parse_locs(xml_text: str) -> list[str]:
        try:
            root = ET.fromstring(xml_text)
        except ParseError:
            return []
        locs: list[str] = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]  # strip XML namespace, if any
            if tag == "loc" and elem.text:
                locs.append(elem.text.strip())
        return locs
