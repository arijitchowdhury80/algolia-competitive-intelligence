"""Concrete ContentProvider implementations for ExecSpeechScanner.

Root-cause note (task #25, live-audit finding #3): the exec_speech lane
never ran in production not because it wasn't called, but because no
ContentProvider implementation existed at all -- scanner.py only declared
the Protocol. daily_production_run.py hardcoded `exec_speech_ran = False`
honestly rather than fabricate a pass. This module is the first real
provider: it re-uses text the collection loop ALREADY fetched (no new
network calls, no new API) and extracts attributed quotes deterministically.
It will miss quotes a real transcript/news-API provider would catch -- that
is an honest coverage gap, not a fabricated one, and more ContentProvider
implementations (earnings-call transcripts, news-quote feeds) can be added
later without touching the scanner.
"""

from __future__ import annotations

import re

from cios.execspeech.types import ExecSource, RawStatement
from cios.hunter.types import Competitor

# Deterministic extraction: a quoted span (>=20 chars, plain double quotes)
# followed within a short window by an attribution clause naming a person
# and a leadership title. Both the quote AND the attribution must be present
# in the SAME already-fetched page for a RawStatement to be produced --
# scanner.py's evidence rule (verbatim quote + source_url) still applies on
# top of this.
_QUOTE_ATTRIBUTION_RE = re.compile(
    r'"([^"]{20,400})"\s*,?\s*(?:said|says|according to)\s+'
    r'([A-Z][a-zA-Z\'\-]+(?:\s+[A-Z][a-zA-Z\'\-]+){0,3}),?\s*'
    r'(CEO|CTO|CFO|COO|CMO|CPO|Chief\s+[A-Za-z]+\s+Officer|VP\s+of\s+[A-Za-z ]+|'
    r'Vice\s+President[a-zA-Z ,]*|Founder|Co-[Ff]ounder|President)',
    re.MULTILINE,
)

_MAX_STATEMENTS_PER_PAGE = 5  # bounded: this is a heuristic scan, not a full NLP pass


class SnapshotQuoteProvider:
    """Extracts attributed quotes from page text the collection loop already
    fetched for one competitor this cycle. `pages` maps source_url ->
    fetched text (the same `evidence_texts` dict daily_production_run.py
    already builds); no separate fetch happens here."""

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    def fetch(self, competitor: Competitor) -> list[RawStatement]:
        statements: list[RawStatement] = []
        for url, text in self._pages.items():
            if not text:
                continue
            matches = _QUOTE_ATTRIBUTION_RE.findall(text)[:_MAX_STATEMENTS_PER_PAGE]
            for quote, exec_name, exec_role in matches:
                statements.append(
                    RawStatement(
                        competitor_id=competitor.id,
                        tenant_id=competitor.tenant_id,
                        executive_name=exec_name.strip(),
                        executive_role=exec_role.strip(),
                        exec_source=ExecSource.OTHER,
                        source_url=url,
                        quote=quote.strip(),
                    )
                )
        return statements
