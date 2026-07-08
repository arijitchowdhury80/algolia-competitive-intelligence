"""Scanner tests: evidence rule, classification wiring, tenant scoping, dedup.

All providers here are in-memory fakes -- no network.
"""

from __future__ import annotations

from cios.execspeech.scanner import ContentProvider, ExecSpeechScanner
from cios.execspeech.types import ExecSource, RawStatement, SignalType
from cios.hunter.types import Competitor


def _competitor(tenant_id: int = 1, competitor_id: int = 1) -> Competitor:
    return Competitor(id=competitor_id, tenant_id=tenant_id, name="Acme Search")


class FakeProvider:
    def __init__(self, statements: list[RawStatement]) -> None:
        self._statements = statements

    def fetch(self, competitor: Competitor) -> list[RawStatement]:
        return self._statements


def test_rejects_statement_without_quote() -> None:
    competitor = _competitor()
    provider: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=1,
                tenant_id=1,
                exec_source=ExecSource.INTERVIEW,
                source_url="https://example.com/a",
                quote=None,
                claim="They are pivoting strategy.",
            )
        ]
    )
    scanner = ExecSpeechScanner([provider])
    signals = scanner.scan(competitor)

    assert signals == []
    assert len(scanner.rejected) == 1
    assert scanner.rejected[0].reason == "missing verbatim quote"


def test_rejects_statement_without_source_url() -> None:
    competitor = _competitor()
    provider: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=1,
                tenant_id=1,
                exec_source=ExecSource.PODCAST,
                source_url=None,
                quote="We are pivoting our strategy.",
            )
        ]
    )
    scanner = ExecSpeechScanner([provider])
    signals = scanner.scan(competitor)

    assert signals == []
    assert scanner.rejected[0].reason == "missing source_url"


def test_accepts_statement_with_quote_and_url_and_classifies() -> None:
    competitor = _competitor()
    provider: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=1,
                tenant_id=1,
                executive_name="Jane Exec",
                executive_role="CEO",
                exec_source=ExecSource.EARNINGS_CALL,
                source_url="https://example.com/earnings-q2",
                quote="We are pivoting our strategy toward AI-native search.",
            )
        ]
    )
    scanner = ExecSpeechScanner([provider])
    signals = scanner.scan(competitor)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.executive_name == "Jane Exec"
    assert signal.source_url == "https://example.com/earnings-q2"
    assert signal.market_signal == SignalType.STRATEGY_SHIFT.value
    assert signal.confidence is not None
    assert scanner.rejected == []


def test_dedups_same_quote_seen_twice_across_providers() -> None:
    competitor = _competitor()
    quote = "We are pivoting our strategy toward AI-native search."
    provider_a: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=1,
                tenant_id=1,
                source_url="https://example.com/a",
                quote=quote,
            )
        ]
    )
    provider_b: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=1,
                tenant_id=1,
                # Same quote, different whitespace/case -- still a dup.
                source_url="https://example.com/b",
                quote="  WE ARE PIVOTING our strategy toward AI-native search.  ",
            )
        ]
    )
    scanner = ExecSpeechScanner([provider_a, provider_b])
    signals = scanner.scan(competitor)

    assert len(signals) == 1


def test_tenant_scoping_rejects_cross_tenant_statement() -> None:
    competitor = _competitor(tenant_id=1, competitor_id=1)
    provider: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=1,
                tenant_id=2,  # wrong tenant
                source_url="https://example.com/a",
                quote="We are pivoting our strategy.",
            )
        ]
    )
    scanner = ExecSpeechScanner([provider])
    signals = scanner.scan(competitor)

    assert signals == []
    assert scanner.rejected[0].reason == "tenant mismatch"


def test_tenant_scoping_rejects_cross_competitor_statement() -> None:
    competitor = _competitor(tenant_id=1, competitor_id=1)
    provider: ContentProvider = FakeProvider(
        [
            RawStatement(
                competitor_id=99,  # wrong competitor
                tenant_id=1,
                source_url="https://example.com/a",
                quote="We are pivoting our strategy.",
            )
        ]
    )
    scanner = ExecSpeechScanner([provider])
    signals = scanner.scan(competitor)

    assert signals == []
    assert scanner.rejected[0].reason == "competitor mismatch"
