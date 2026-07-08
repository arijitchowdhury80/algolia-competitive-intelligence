"""Network adapter layer for collection.

This is the one module under src/cios/collect where live network calls
happen; every other collection module takes fetched content as a plain
argument and never touches the network directly. Implements two things:

  - `ContentFetcher` (this module): full-page retrieval for snapshot/extract,
    porting V0's fetch_url() behavior (timeout, retry, user-agent, HTML text
    extraction, 120k char cap).
  - `ProbeFetcherAdapter`: wraps a ContentFetcher to satisfy
    cios.hunter.validator.Fetcher (a lightweight reachability probe) so
    discovery -> validate -> lifecycle can reuse the same real adapter
    instead of a second, competing network client.
"""

from __future__ import annotations

import time
from html.parser import HTMLParser
from typing import Optional, Protocol, Sequence

import httpx

from cios.collect.extract import normalize_text
from cios.collect.types import ContentFetchResult, FetchStatus
from cios.hunter.validator import FetchResult as ProbeFetchResult

USER_AGENT = "Mozilla/5.0 (compatible; CIOSCompetitiveResearch/1.0)"
DEFAULT_TIMEOUT_S = 25.0
DEFAULT_RETRIES = 2
MAX_BODY_BYTES = 1_500_000
MAX_TEXT_CHARS = 120_000


class _TextExtractor(HTMLParser):
    """Small HTML-to-text extractor, ported from V0's TextExtractor -- avoids
    pulling in a full HTML parsing dependency for plain text retrieval."""

    _BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "tr", "br", "section", "article"}
    _SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, Optional[str]]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip += 1
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return normalize_text(" ".join(self._parts))


class ContentFetcher(Protocol):
    """Injected network boundary for full-page retrieval."""

    def fetch_content(self, url: str) -> ContentFetchResult: ...


class HttpContentFetcher:
    """Real HTTP fetcher: httpx, timeout + retry, V0-compatible behavior
    (user-agent, HTML text extraction, 120k char cap on returned text)."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT_S,
        retries: int = DEFAULT_RETRIES,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._timeout = timeout
        self._retries = retries
        self._transport = transport

    def fetch_content(self, url: str) -> ContentFetchResult:
        started = time.time()
        last_error: Optional[str] = None
        last_status: Optional[int] = None
        for _attempt in range(self._retries + 1):
            try:
                return self._fetch_once(url, started)
            except httpx.HTTPStatusError as exc:
                last_status = exc.response.status_code
                last_error = f"http_error:{last_status}"
                continue
            except Exception as exc:  # noqa: BLE001 -- network boundary: every failure becomes a ContentFetchResult
                last_error = str(exc)[:500]
                continue
        return ContentFetchResult(
            status=FetchStatus.ERROR,
            http_status=last_status,
            text="",
            error=last_error,
            collector="direct_http",
            duration_ms=int((time.time() - started) * 1000),
        )

    def _fetch_once(self, url: str, started: float) -> ContentFetchResult:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
        }
        with httpx.Client(timeout=self._timeout, follow_redirects=True, transport=self._transport) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            raw = response.content[:MAX_BODY_BYTES]
            charset = response.encoding or "utf-8"
            body = raw.decode(charset, errors="replace")
            text = self._extract_text(body)
            return ContentFetchResult(
                status=FetchStatus.OK,
                http_status=response.status_code,
                text=text[:MAX_TEXT_CHARS],
                error=None,
                collector="direct_http",
                duration_ms=int((time.time() - started) * 1000),
            )

    @staticmethod
    def _extract_text(body: str) -> str:
        if "<html" in body[:1000].lower() or "<body" in body[:5000].lower():
            parser = _TextExtractor()
            parser.feed(body)
            return parser.text()
        return normalize_text(body)


class ProbeFetcherAdapter:
    """Adapts an HttpContentFetcher to cios.hunter.validator.Fetcher (a
    reachability probe with a source-family hint), so the discovery ->
    validate -> lifecycle sweep runs against the same real network adapter
    used for full-page collection -- no second, competing HTTP client."""

    def __init__(self, content_fetcher: ContentFetcher) -> None:
        self._content_fetcher = content_fetcher

    def fetch(self, url: str) -> ProbeFetchResult:
        result = self._content_fetcher.fetch_content(url)
        if result.status != FetchStatus.OK:
            return ProbeFetchResult(reachable=False, http_status=result.http_status, error=result.error or "fetch_error")
        return ProbeFetchResult(reachable=True, http_status=result.http_status)
