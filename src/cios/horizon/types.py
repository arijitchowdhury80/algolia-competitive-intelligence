"""Shared data types for multi-horizon industry research.

No DB, no network. These are the value objects the horizon module reasons
over and returns; the caller's injected repositories map inputs onto
tenant-scoped rows (semantic_deltas / semantic_facts / signals, per
cios.brain.types and cios.collect.types) and, eventually, a horizon_reads
table (not yet in schema.sql -- out of scope for this build).

Evidence rule (same invariant as the rest of Argus): an IndustryObservation
must carry a verbatim-grounded summary AND a source URL. A theme in a
HorizonRead needs at least 2 observations from distinct sources or it is
marked single-source, unconfirmed rather than promoted as a confirmed theme.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Horizon(str, Enum):
    """The three lookback windows Argus researches on, per doctrine."""

    D10 = "d10"
    D30 = "d30"
    D60 = "d60"

    @property
    def days(self) -> int:
        return {Horizon.D10: 10, Horizon.D30: 30, Horizon.D60: 60}[self]


class ObservationOrigin(str, Enum):
    """Where an IndustryObservation came from. LEDGER = the tenant's own
    accumulated ledger (deterministic scan). EXTERNAL = an injected
    IndustryFeed (news RSS, analyst notes, ...) -- not built in this module,
    the Protocol exists so a future feed can plug in without touching the
    synthesis or connector logic."""

    LEDGER = "ledger"
    EXTERNAL = "external"


class IndustryObservation(BaseModel):
    """One dated, evidence-grounded event or trend observed in the industry
    (not necessarily tied to a single named competitor). Invariant: a
    verbatim-grounded summary and a source URL -- no paraphrase-only,
    no-URL observations (evidence rule)."""

    competitor_id: Optional[int] = None
    observed_at: date
    kind: str  # e.g. "event" | "trend"
    summary: str
    source_url: str
    origin: ObservationOrigin = ObservationOrigin.LEDGER

    @model_validator(mode="after")
    def _require_evidence(self) -> "IndustryObservation":
        if not self.summary or not self.summary.strip():
            raise ValueError("IndustryObservation requires a non-empty summary")
        if not self.source_url or not self.source_url.strip():
            raise ValueError("IndustryObservation requires a source_url")
        return self


class ThemeConfidence(str, Enum):
    CONFIRMED = "confirmed"  # >=2 observations, >=2 distinct sources
    SINGLE_SOURCE_UNCONFIRMED = "single_source_unconfirmed"


class IndustryTheme(BaseModel):
    """An emerging theme synthesized across observations within a horizon.
    Invariant: evidence_urls is a subset of the observations it was built
    from (evidence-or-silence, same as cios.brain)."""

    theme: str
    confidence: ThemeConfidence
    evidence_urls: list[str] = Field(default_factory=list)


class RelevanceScore(BaseModel):
    """How relevant an observation or theme is to the tenant, scored 0..1.
    Kept as a separate object (not a bare float) so the read can carry a
    one-line grounded rationale rather than an unexplained number."""

    score: float = Field(ge=0.0, le=1.0)
    rationale: str


class HorizonRead(BaseModel):
    """The compiled read for a single horizon window: notable industry
    movements, emerging themes, and a relevance-to-tenant score."""

    tenant_id: int
    horizon: Horizon
    as_of: date
    notable_movements: list[str] = Field(default_factory=list)
    themes: list[IndustryTheme] = Field(default_factory=list)
    relevance: Optional[RelevanceScore] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DotConnection(BaseModel):
    """This week's signal tied to a standing horizon trend. Invariant: cites
    BOTH the current signal's evidence URL(s) AND the horizon observation
    URL(s) it connects to -- both drawn only from the caller-supplied
    allowed set (deterministic guard in connector.py)."""

    tenant_id: int
    horizon: Horizon
    connection: str
    signal_evidence_urls: list[str] = Field(default_factory=list)
    horizon_evidence_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_both_sides_evidenced(self) -> "DotConnection":
        if not self.signal_evidence_urls:
            raise ValueError("DotConnection requires at least one signal evidence URL")
        if not self.horizon_evidence_urls:
            raise ValueError("DotConnection requires at least one horizon evidence URL")
        return self
