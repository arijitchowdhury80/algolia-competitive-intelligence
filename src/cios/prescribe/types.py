"""Shared data types for the prescription engine.

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md, Addendum 2
point 3), Arijit verbatim: "Gather intel, contextualize it to MY business,
and hand me VERY specific strategies -- marketing strategies, ploys --
grounded in what was gathered. Not observations. Prescriptions."

A Prescription is the unit that satisfies that bar: a named play with
concrete steps, a team to run it, an urgency window, and grounding that
traces back to the exact signal(s), horizon connection(s), and/or thesis
this cycle's intel produced. No DB, no network -- these are the value
objects the engine reasons over and returns; a caller's repo maps them onto
tenant-scoped rows (no schema table exists yet for this module).

Evidence rule (same invariant as brain/horizon/ownbrand): a Prescription
cannot exist without grounding. `Grounding.evidence_urls` must be non-empty
AND must reference at least one of a signal, a horizon connection, or a
thesis actually supplied this cycle -- evidence-or-silence extends to
prescriptions exactly as it does to signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Team(str, Enum):
    """Doctrine-facing routing label, same vocabulary as
    cios.brain.types.Signal.team_to_involve / cadence.VALID_TEAMS_TO_INVOLVE."""

    MARKETING = "Marketing"
    CONTENT = "Content"
    PRODUCT = "Product"
    SALES_ENABLEMENT = "Sales Enablement"
    EXECUTIVE = "Executive"


class UrgencyWindow(str, Enum):
    """Doctrine freshness window: how soon the play must be run to matter."""

    ACT_NOW = "act_now"       # <= 1 day
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"

    @property
    def weight(self) -> float:
        """Ranking weight used by the engine's urgency x materiality cap.
        Not a doctrine number -- an internal ordering device only."""
        return {
            UrgencyWindow.ACT_NOW: 3.0,
            UrgencyWindow.THIS_WEEK: 2.0,
            UrgencyWindow.THIS_MONTH: 1.0,
        }[self]


class Effort(str, Enum):
    S = "S"
    M = "M"
    L = "L"


class Grounding(BaseModel):
    """What this prescription is actually grounded in. Invariant: at least
    one evidence URL, and at least one traceable reference (a signal's own
    evidence URL, a horizon connection's evidence URL, or a supplied
    thesis id) -- a prescription that names no source is an opinion, not a
    prescription."""

    signal_evidence_urls: list[str] = Field(default_factory=list)
    connection_evidence_urls: list[str] = Field(default_factory=list)
    thesis_ids: list[int] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_grounding(self) -> "Grounding":
        if not self.evidence_urls:
            raise ValueError(
                "Grounding requires >=1 evidence_urls (evidence-or-silence: "
                "no ungrounded prescriptions)"
            )
        if not (self.signal_evidence_urls or self.connection_evidence_urls or self.thesis_ids):
            raise ValueError(
                "Grounding requires a traceable reference to at least one "
                "signal, horizon connection, or thesis supplied this cycle"
            )
        return self


class Prescription(BaseModel):
    """A specific, concrete strategy or ploy -- the unit doctrine demands
    instead of an observation. Invariant: `play` is a list of concrete
    steps (never a single vague sentence), `team` and `urgency_window` are
    always set (decision-layer-not-feed), and `grounding` is always
    evidence-backed (enforced by Grounding itself)."""

    tenant_id: int
    title: str
    play: list[str] = Field(default_factory=list)
    team: Team
    urgency_window: UrgencyWindow
    grounding: Grounding
    expected_effect: str
    effort: Effort
    materiality_score: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _require_concrete_play(self) -> "Prescription":
        if not self.title or not self.title.strip():
            raise ValueError("Prescription requires a non-empty title")
        steps = [s.strip() for s in self.play if s and s.strip()]
        if not steps:
            raise ValueError(
                "Prescription requires >=1 concrete step in `play` (not an "
                "observation -- a play)"
            )
        if not self.expected_effect or not self.expected_effect.strip():
            raise ValueError("Prescription requires expected_effect")
        return self

    @property
    def rank_score(self) -> float:
        """urgency x materiality -- the ranking key the engine caps ~5/cycle
        by. A property (not stored) so ranking always reflects the current
        urgency_window/materiality_score rather than a stale snapshot."""
        return self.urgency_window.weight * self.materiality_score
