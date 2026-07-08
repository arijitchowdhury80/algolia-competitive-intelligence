"""Tests for article-link resolution off an index/blog page."""

from __future__ import annotations

from cios.collect.article_resolver import resolve_article_links

INDEX_HTML = """
<html><body>
<nav><a href="/blog">Blog Home</a><a href="/pricing">Pricing</a></nav>
<a href="/blog/newest-launch">Newest launch</a>
<a href="https://example.com/blog/second-post">Second post</a>
<a href="/blog/newest-launch">Newest launch (dup nav link)</a>
<a href="https://competitor.com/blog/external-post">External host</a>
<a href="#comments">Jump to comments</a>
<a href="/blog/">Blog index trailing slash</a>
</body></html>
"""


def test_resolve_article_links_extracts_relative_and_absolute_same_host_links():
    urls = resolve_article_links(INDEX_HTML, "https://example.com/blog")

    assert "https://example.com/blog/newest-launch" in urls
    assert "https://example.com/blog/second-post" in urls


def test_resolve_article_links_excludes_external_host():
    urls = resolve_article_links(INDEX_HTML, "https://example.com/blog")

    assert not any("competitor.com" in url for url in urls)


def test_resolve_article_links_excludes_index_page_and_shallower_links():
    urls = resolve_article_links(INDEX_HTML, "https://example.com/blog")

    assert "https://example.com/blog" not in urls
    assert "https://example.com/pricing" not in urls
    assert "https://example.com/blog/comments" not in urls


def test_resolve_article_links_dedupes_and_preserves_document_order():
    urls = resolve_article_links(INDEX_HTML, "https://example.com/blog")

    assert urls[0] == "https://example.com/blog/newest-launch"
    assert urls.count("https://example.com/blog/newest-launch") == 1


def test_resolve_article_links_respects_cap():
    many_links = "".join(f'<a href="/blog/post-{i}">Post {i}</a>' for i in range(20))
    html = f"<html><body>{many_links}</body></html>"

    urls = resolve_article_links(html, "https://example.com/blog", cap=10)

    assert len(urls) == 10


def test_resolve_article_links_www_host_normalized():
    html = '<a href="https://www.example.com/blog/post-1">Post</a>'

    urls = resolve_article_links(html, "https://example.com/blog")

    assert urls == ["https://www.example.com/blog/post-1"]


def test_resolve_article_links_empty_html_returns_empty_list():
    assert resolve_article_links("", "https://example.com/blog") == []
