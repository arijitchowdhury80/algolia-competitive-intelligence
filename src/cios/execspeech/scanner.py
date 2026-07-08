"""Executive speech scanning: competitor -> SpeechSignal rows.

Pure orchestration -- no network in this module. Actual retrieval (earnings
call transcripts, interview/podcast transcripts, news quote feeds, LinkedIn
posts) lives in injected `ContentProvider` implementations outside this
package, same pattern as hunter/discovery.py's DiscoveryProvider. The scanner
fans a competitor out to every configured provider, validates the evidence
rule (verbatim quote + source URL, no paraphrase-only signals), classifies
each statement, dedups repeated quotes, and returns SpeechSignal rows ready
for the executive_speech_signals table.
"""

from __future__ import annotations

from typing import Optional, Protocol

from cios.execspeech.classify import HeuristicClassifier, SignalClassifier
from cios.execspeech.types import RawStatement, SpeechSignal
from cios.hunter.types import Competitor


class ContentProvider(Protocol):
    """A single retrieval strategy (earnings-call fetcher, interview/podcast
    transcript fetcher, news-quote fetcher, LinkedIn post fetcher, ...).
    Each provider covers one or more ExecSource kinds; the scanner does not
    hardcode any single provider."""

    def fetch(self, competitor: Competitor) -> list[RawStatement]: ...


class RejectedStatement:
    """A statement that failed the evidence rule, kept for caller visibility
    (e.g. logging to source health / suppressed diagnostics) rather than
    silently dropped."""

    def __init__(self, statement: RawStatement, reason: str) -> None:
        self.statement = statement
        self.reason = reason


class ExecSpeechScanner:
    """Fans a competitor out across all configured content providers and
    produces SpeechSignal rows.

    Evidence rule: a RawStatement without both a verbatim quote and a
    source_url is rejected, not paraphrased into a signal.
    Dedup: the same quote (case/whitespace-insensitive) seen twice for a
    competitor, from the same or different providers, produces one signal.
    """

    def __init__(
        self,
        providers: list[ContentProvider],
        classifier: Optional[SignalClassifier] = None,
    ) -> None:
        self._providers = providers
        self._classifier = classifier or HeuristicClassifier()

    def scan(self, competitor: Competitor) -> list[SpeechSignal]:
        signals: list[SpeechSignal] = []
        self.rejected: list[RejectedStatement] = []
        seen_quotes: set[str] = set()

        for provider in self._providers:
            for statement in provider.fetch(competitor):
                if statement.tenant_id != competitor.tenant_id:
                    self.rejected.append(
                        RejectedStatement(statement, "tenant mismatch")
                    )
                    continue
                if statement.competitor_id != competitor.id:
                    self.rejected.append(
                        RejectedStatement(statement, "competitor mismatch")
                    )
                    continue
                if not statement.quote or not statement.quote.strip():
                    self.rejected.append(
                        RejectedStatement(statement, "missing verbatim quote")
                    )
                    continue
                if not statement.source_url or not statement.source_url.strip():
                    self.rejected.append(
                        RejectedStatement(statement, "missing source_url")
                    )
                    continue

                dedup_key = " ".join(statement.quote.strip().lower().split())
                if dedup_key in seen_quotes:
                    continue
                seen_quotes.add(dedup_key)

                text = statement.quote if not statement.claim else (
                    f"{statement.quote} {statement.claim}"
                )
                signal_type, confidence = self._classifier.classify(text)

                signals.append(
                    SpeechSignal(
                        tenant_id=statement.tenant_id,
                        competitor_id=statement.competitor_id,
                        executive_name=statement.executive_name,
                        executive_role=statement.executive_role,
                        source_url=statement.source_url,
                        published_at=statement.published_at,
                        quote=statement.quote,
                        claim=statement.claim,
                        market_signal=signal_type.value,
                        confidence=confidence,
                        evidence_finding_id=statement.evidence_finding_id,
                    )
                )

        return signals
