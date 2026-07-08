from __future__ import annotations

from cios.execspeech.providers import SnapshotQuoteProvider
from cios.execspeech.scanner import ExecSpeechScanner
from cios.hunter.types import Competitor


def _competitor(**overrides) -> Competitor:
    base = dict(id=7, tenant_id=1, name="Rival Inc")
    base.update(overrides)
    return Competitor(**base)


def test_extracts_attributed_quote_from_fetched_page_text():
    pages = {
        "https://rival.com/blog/pivot": (
            'In today\'s announcement, "We are pivoting our entire GTM to be '
            'agent-first," said Jane Smith, CEO of Rival Inc, during the keynote.'
        )
    }
    provider = SnapshotQuoteProvider(pages)
    statements = provider.fetch(_competitor())
    assert len(statements) == 1
    s = statements[0]
    assert s.quote == "We are pivoting our entire GTM to be agent-first,"
    assert s.executive_name == "Jane Smith"
    assert "CEO" in s.executive_role
    assert s.source_url == "https://rival.com/blog/pivot"
    assert s.competitor_id == 7
    assert s.tenant_id == 1


def test_no_quote_no_attribution_yields_nothing():
    pages = {"https://rival.com/pricing": "Our entry tier is now $400 per month."}
    provider = SnapshotQuoteProvider(pages)
    assert provider.fetch(_competitor()) == []


def test_quote_without_attribution_is_not_extracted():
    pages = {"https://rival.com/blog": '"This changes everything for our customers."'}
    provider = SnapshotQuoteProvider(pages)
    assert provider.fetch(_competitor()) == []


def test_feeds_scanner_end_to_end_and_produces_a_valid_signal():
    pages = {
        "https://rival.com/blog/pivot": (
            'She told reporters, "We are doubling down on enterprise search," '
            "said Jane Smith, Chief Product Officer, at the event."
        )
    }
    scanner = ExecSpeechScanner(providers=[SnapshotQuoteProvider(pages)])
    signals = scanner.scan(_competitor())
    assert len(signals) == 1
    assert signals[0].source_url == "https://rival.com/blog/pivot"
    assert signals[0].quote
