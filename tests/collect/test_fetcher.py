"""Tests for the HTTP content fetcher. Uses httpx.MockTransport -- no live
network, per the "network allowed only in fetcher.py, mocked in tests" rule.
"""

from __future__ import annotations

import httpx
import pytest

from cios.collect.fetcher import HttpContentFetcher, ProbeFetcherAdapter
from cios.collect.types import FetchStatus


def transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_fetch_content_extracts_text_from_html_and_strips_scripts():
    def handler(request: httpx.Request) -> httpx.Response:
        html = "<html><body><script>evil()</script><h1>Launch</h1><p>Agentic search is here.</p></body></html>"
        return httpx.Response(200, text=html)

    fetcher = HttpContentFetcher(transport=transport(handler))
    result = fetcher.fetch_content("https://example.com/blog")

    assert result.status == FetchStatus.OK
    assert result.http_status == 200
    assert "evil()" not in result.text
    assert "Agentic search is here." in result.text


def test_fetch_content_returns_plain_text_when_no_html_markers():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Plain feed content, no html tags here.")

    fetcher = HttpContentFetcher(transport=transport(handler))
    result = fetcher.fetch_content("https://example.com/feed.txt")

    assert result.status == FetchStatus.OK
    assert "Plain feed content" in result.text


def test_fetch_content_returns_error_result_on_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    fetcher = HttpContentFetcher(transport=transport(handler), retries=0)
    result = fetcher.fetch_content("https://example.com/missing")

    assert result.status == FetchStatus.ERROR
    assert result.http_status == 404


def test_fetch_content_returns_error_result_on_connection_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    fetcher = HttpContentFetcher(transport=transport(handler), retries=0)
    result = fetcher.fetch_content("https://example.com/down")

    assert result.status == FetchStatus.ERROR
    assert result.error is not None


def test_probe_fetcher_adapter_reports_reachable_true_on_ok_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><p>ok</p></body></html>")

    content_fetcher = HttpContentFetcher(transport=transport(handler))
    probe = ProbeFetcherAdapter(content_fetcher)

    result = probe.fetch("https://example.com/blog")

    assert result.reachable is True
    assert result.http_status == 200


def test_probe_fetcher_adapter_reports_reachable_false_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    content_fetcher = HttpContentFetcher(transport=transport(handler), retries=0)
    probe = ProbeFetcherAdapter(content_fetcher)

    result = probe.fetch("https://example.com/blog")

    assert result.reachable is False


def test_probe_fetcher_adapter_rejects_empty_success_response_as_not_sweepable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, text="")

    content_fetcher = HttpContentFetcher(transport=transport(handler), retries=0)
    probe = ProbeFetcherAdapter(content_fetcher)

    result = probe.fetch("https://example.com/docs")

    assert result.reachable is False
    assert result.http_status == 202
    assert result.error == "empty"


def test_fetch_content_classifies_aws_waf_challenge_as_blocked_not_empty_success():
    def handler(request: httpx.Request) -> httpx.Response:
        html = """
        <!DOCTYPE html>
        <html>
          <head>
            <script src="https://token.awswaf.com/challenge.js"></script>
          </head>
          <body>
            <div id="challenge-container"></div>
            <noscript>In order to continue, we need to verify that you're not a robot.</noscript>
          </body>
        </html>
        """
        return httpx.Response(202, text=html)

    fetcher = HttpContentFetcher(transport=transport(handler), retries=0)
    result = fetcher.fetch_content("https://example.com/protected")

    assert result.status == FetchStatus.ERROR
    assert result.http_status == 202
    assert result.error == "blocked_by_waf:aws_waf_challenge"
    assert "token.awswaf.com" in result.raw_html
