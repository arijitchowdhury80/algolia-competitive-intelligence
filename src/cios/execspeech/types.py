"""Shared data types for the argus-executive-speech-scanner skill.

Mirrors src/cios/db/schema.sql: executive_speech_signals. This module only
writes that table (plus reads raw_findings for the evidence link) per
docs/planning/Argus-skill-build-matrix.md ("Writes: executive_speech_signals,
raw_findings, semantic_facts" -- raw_findings/semantic_facts are the intel
collector's and synthesis engine's concern respectively; this scanner is
scoped to executive_speech_signals and may reference an existing raw_findings
row as evidence).

Evidence rule (Argus-project-manifesto.md + CI-OS-evaluation-plan.md Executive
Speech Evals): "No unattributed quotes" -- a signal must carry a verbatim
quote AND a source URL. Paraphrase-only claims are not signals.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ExecSource(str, Enum):
    """Where the executive statement was captured."""

    EARNINGS_CALL = "earnings_call"
    INTERVIEW = "interview"
    PODCAST = "podcast"
    KEYNOTE = "keynote"
    CONFERENCE_TALK = "conference_talk"
    NEWS_QUOTE = "news_quote"
    LINKEDIN_POST = "linkedin_post"
    PRESS_RELEASE = "press_release"
    OTHER = "other"


class SignalType(str, Enum):
    """Classification of the market-direction implication of a quote.

    Deterministic heuristics live in classify.py; this is the closed set of
    labels stored in executive_speech_signals.market_signal.
    """

    STRATEGY_SHIFT = "strategy_shift"
    PRODUCT_DIRECTION = "product_direction"
    GTM_CHANGE = "gtm_change"
    COMPETITIVE_MENTION = "competitive_mention"
    HIRING_ORG = "hiring_org"
    UNCLASSIFIED = "unclassified"


class RawStatement(BaseModel):
    """One candidate executive statement fetched from an injected content
    provider, before evidence validation and classification. This is the
    scanner's input shape -- not a schema table."""

    competitor_id: int
    tenant_id: int
    executive_name: Optional[str] = None
    executive_role: Optional[str] = None
    exec_source: ExecSource = ExecSource.OTHER
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    quote: Optional[str] = None
    claim: Optional[str] = None
    evidence_finding_id: Optional[int] = None


class SpeechSignal(BaseModel):
    """Row shape for executive_speech_signals. Field names and nullability
    match schema.sql exactly (source_url is the only NOT NULL business
    column beyond the tenant/competitor keys)."""

    id: Optional[int] = None
    tenant_id: int
    competitor_id: int
    executive_name: Optional[str] = None
    executive_role: Optional[str] = None
    source_url: str
    published_at: Optional[datetime] = None
    quote: Optional[str] = None
    claim: Optional[str] = None
    market_signal: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_finding_id: Optional[int] = None

    @model_validator(mode="after")
    def _require_verbatim_quote(self) -> "SpeechSignal":
        # Evidence rule: a signal MUST carry an exact quote + source URL --
        # no paraphrase-only signals. source_url is enforced by the pydantic
        # field type (str, required); quote is enforced here because the
        # column itself is nullable at the DB level (claims/market-only rows
        # are not valid *signals* even though the column allows NULL).
        if not self.quote or not self.quote.strip():
            raise ValueError(
                "SpeechSignal requires a verbatim quote (evidence rule: "
                "no paraphrase-only signals)"
            )
        if not self.source_url or not self.source_url.strip():
            raise ValueError("SpeechSignal requires a source_url")
        return self
