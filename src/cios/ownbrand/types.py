"""Shared data types for argus-own-brand-research.

Mirrors the execspeech evidence rule exactly (docs/planning/
Argus-project-manifesto.md, CI-OS-product-doctrine-2026-07-08.md Addendum 2
point 2): a BrandObservation is only usable evidence when it carries a
verbatim quote AND a source URL. No paraphrase-only observations, no
fabricated "how the market sees us" narratives.

This module does not write a schema.sql table of its own -- it produces
value objects that feed src/cios/brain.SynthesisInput.own_position_facts (the
"where you are" leg of the doctrine's three-position framing), via
position.py's to_own_position_facts() adapter. No network or DB access
lives in this module.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class OwnBrandSource(str, Enum):
    """Where a statement about the tenant's own brand was captured. Distinct
    from ExecSource (execspeech) -- these are FIRST-PARTY and third-party
    perception channels, not the tenant's own executives speaking."""

    OWN_BLOG = "own_blog"
    NEWSROOM = "newsroom"
    CHANGELOG = "changelog"
    PRESS_RELEASE = "press_release"
    REVIEW_SITE = "review_site"
    ANALYST_MENTION = "analyst_mention"
    OTHER = "other"


class OwnBrandSourceSpec(BaseModel):
    """One configured own-brand source for a tenant, mapped from the
    config/tenants-sources.yaml own_brand section by the caller (mirrors
    cios.collect.types.SourceContext's role for competitor sources)."""

    tenant_id: int
    source_type: OwnBrandSource
    url: str
    name: Optional[str] = None


class RawBrandStatement(BaseModel):
    """One candidate statement about the tenant's own brand, fetched from an
    injected content source, before evidence validation. Collector's input
    shape -- not a schema table."""

    tenant_id: int
    source_type: OwnBrandSource = OwnBrandSource.OTHER
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    quote: Optional[str] = None
    claim: Optional[str] = None


class BrandObservation(BaseModel):
    """A validated statement about the tenant's own brand: what is said or
    shown about them, with verbatim evidence. Same evidence rule as
    execspeech.SpeechSignal -- quote AND source_url are both required,
    enforced here since callers may construct these directly in tests."""

    id: Optional[int] = None
    tenant_id: int
    source_type: OwnBrandSource
    source_url: str
    published_at: Optional[datetime] = None
    quote: str
    claim: Optional[str] = None
    theme: Optional[str] = None

    @model_validator(mode="after")
    def _require_verbatim_quote(self) -> "BrandObservation":
        # Evidence rule: no paraphrase-only observations -- a claim about the
        # tenant's own brand must be traceable to an exact quote and a URL,
        # same discipline execspeech applies to competitor executives.
        if not self.quote or not self.quote.strip():
            raise ValueError(
                "BrandObservation requires a verbatim quote (evidence rule: "
                "no paraphrase-only observations)"
            )
        if not self.source_url or not self.source_url.strip():
            raise ValueError("BrandObservation requires a source_url")
        return self


class BrandTheme(BaseModel):
    """One compiled theme in how the tenant's brand is currently positioned.
    Deterministic guard (position.py): a theme with zero observation_urls is
    invalid and must never be constructed -- evidence-or-silence extends to
    the tenant's own position, not just competitor claims."""

    label: str
    summary: str
    observation_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_observation(self) -> "BrandTheme":
        if not self.observation_urls:
            raise ValueError(
                "BrandTheme requires >=1 observation_urls (no theme without "
                "an observation backing it)"
            )
        return self


class BrandPositionRead(BaseModel):
    """Compiled read of how the tenant's brand is currently positioned:
    themes, and gaps versus competitors. Feeds the "where you are" leg of
    the doctrine's three-position framing (SynthesisInput.own_position_facts)
    via to_own_position_facts()."""

    tenant_id: int
    tenant_company_name: str
    themes: list[BrandTheme] = Field(default_factory=list)
    gaps_vs_competitors: list[str] = Field(default_factory=list)
    observations_considered: int = 0

    def to_own_position_facts(self) -> list[str]:
        """Adapter producing the plain-string facts SynthesisInput expects.
        Each fact ends with its evidence URL(s) so the brain's
        evidence_urls() collection can still see them (SynthesisInput reads
        deltas/facts/exec_signals for URLs, not own_position_facts itself --
        embedding the URL inline keeps the string self-evidencing for anyone
        reading the fact directly, e.g. in a prompt DATA block or a log)."""
        facts: list[str] = []
        for theme in self.themes:
            urls = ", ".join(theme.observation_urls)
            facts.append(f"{theme.label}: {theme.summary} (source: {urls})")
        for gap in self.gaps_vs_competitors:
            facts.append(gap)
        return facts
