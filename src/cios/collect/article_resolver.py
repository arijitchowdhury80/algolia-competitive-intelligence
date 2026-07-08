"""Article-link resolution for index/blog-family sources.

Root-cause fix for the collector snapshotting a blog *index* page (e.g.
elastic.co/blog) and citing that index URL as evidence for a specific
claim that only exists on one of the articles it links to. Given an index
page's HTML and its own URL, this module finds the individual article URLs
linked from it so the runner can fetch and cite those instead.

Stdlib-only (HTMLParser), matching the style of fetcher.py's
`_TextExtractor` -- no LLM, no extra HTML parsing dependency.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Optional, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

DEFAULT_ARTICLE_LINK_CAP = 10


class _LinkCollector(HTMLParser):
    """Collects every `<a href>` in document order."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value)
                break


def _normalized_path(path: str) -> str:
    return path.rstrip("/") or "/"


def _path_depth(path: str) -> int:
    return len([seg for seg in path.split("/") if seg])


def resolve_article_links(html: str, base_url: str, cap: int = DEFAULT_ARTICLE_LINK_CAP) -> list[str]:
    """Extract candidate article links from an index page's HTML.

    A candidate must:
      - resolve to an absolute http(s) URL
      - share the same host as `base_url` (ignoring a leading "www.")
      - have a path strictly deeper than the index page's own path (so the
        index page itself, its anchors, and sibling nav links are excluded)

    Returned in the order first seen on the page (index pages list newest
    first), deduplicated, capped at `cap`.
    """
    base_parts = urlsplit(base_url)
    base_host = base_parts.netloc.lower().removeprefix("www.")
    base_path = _normalized_path(base_parts.path)
    base_depth = _path_depth(base_path)

    parser = _LinkCollector()
    parser.feed(html or "")

    seen: set[str] = set()
    articles: list[str] = []
    for href in parser.hrefs:
        resolved = urljoin(base_url, href.strip())
        parts = urlsplit(resolved)
        if parts.scheme not in ("http", "https"):
            continue
        host = parts.netloc.lower().removeprefix("www.")
        if host != base_host:
            continue
        path = _normalized_path(parts.path)
        if path == base_path or _path_depth(path) <= base_depth:
            continue
        canonical = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        if canonical in seen:
            continue
        seen.add(canonical)
        articles.append(canonical)
        if len(articles) >= cap:
            break
    return articles
