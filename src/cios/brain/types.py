"""Shared data types for the Argus semantic brain (Gate 4).

Mirrors the SEMANTIC LAYER + CLAIMS AND THESES tables in
src/cios/db/schema.sql (semantic_deltas, claims, claim_observations,
competitor_theses, action_items). These are the value objects the brain
reasons over; the caller's injected repositories map them onto tenant-scoped
DB rows. No network or DB access lives in this module.

Doctrine enforced by these types (docs/planning/CI-OS-Fable-build-goal-spec.md
section 6, Argus-project-manifesto.md):
  - evidence-or-silence: a promoted Signal MUST carry >=1 source URL.
  - coverage-before-quiet: a quiet verdict is only valid when every required
    lane provably ran; otherwise the brain emits a coverage-failure event.
  - decision-layer-not-feed: every Signal carries an owner + recommended action.
  - materiality-before-urgency: Signals below the materiality floor are
    suppressed, not promoted.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field

from cios.collect.types import Delta, ExtractedFact

# --------------------------------------------------------------------------
# Model gateway abstraction (injected). Matches the async shape of
# cios.platform.models.provider.ModelProvider.generate so a router-backed
# adapter or an in-memory fake can be supplied interchangeably.
# --------------------------------------------------------------------------

from cios.platform.models.types import ModelRequest, ModelResponse  # noqa: E402


class BrainModel(Protocol):
    """The single LLM entry point the brain depends on.

    Implementations route through the ModelRouter + a concrete provider (see
    RouterBackedModel) or return canned output (tests). The brain never names
    a provider or model id -- it declares a task_profile + capability needs on
    the ModelRequest and lets routing decide the tier (synthesis -> judgment).
    """

    async def generate(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover - protocol
        ...


# --------------------------------------------------------------------------
# Coverage: the proof that quiet is earned, not assumed.
# --------------------------------------------------------------------------


class LaneStatus(BaseModel):
    """Did one required collection lane run cleanly this cycle?"""

    lane: str
    ran: bool
    error: Optional[str] = None


class CoverageReport(BaseModel):
    """Per-cycle proof of which lanes ran. A quiet verdict is only valid when
    every required lane ran without error (coverage-before-quiet)."""

    lanes: list[LaneStatus] = Field(default_factory=list)

    @property
    def all_ran(self) -> bool:
        return bool(self.lanes) and all(l.ran and l.error is None for l in self.lanes)

    @property
    def failed_lanes(self) -> list[str]:
        return [l.lane for l in self.lanes if not l.ran or l.error is not None]


# --------------------------------------------------------------------------
# Synthesis input / output.
# --------------------------------------------------------------------------


class SynthesisInput(BaseModel):
    """Everything the synthesizer needs for one competitor for one cycle."""

    tenant_id: int
    competitor_id: int
    competitor_name: str
    deltas: list[Delta] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)
    exec_signals: list[dict[str, Any]] = Field(default_factory=list)
    prior_theses: list[str] = Field(default_factory=list)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    # The reader's own company. Used ONLY to ground the doctrine's "where you
    # are" position in the three-position framing (competitor / tenant /
    # competitor's next move). Optional and evidence-backed: if the tenant
    # has supplied no facts about their own position, own_position_facts is
    # empty and the synthesizer must not fabricate a "where you are" claim
    # (evidence-or-silence extends to the tenant's own position too).
    tenant_company_name: Optional[str] = None
    own_position_facts: list[str] = Field(default_factory=list)
    # Set on a quality-loop revision pass: the reviewer's required_fixes,
    # framed as instructions the synthesizer must apply (cut or hedge the
    # flagged specifics). Empty on a normal first pass.
    extra_instructions: str = ""

    def evidence_urls(self) -> set[str]:
        """The set of source URLs the brain is allowed to cite. Anything the
        LLM returns outside this set is fabricated evidence and is rejected."""
        urls: set[str] = set()
        for d in self.deltas:
            urls.update(u for u in d.evidence_urls if u)
        for f in self.facts:
            if f.evidence_url:
                urls.add(f.evidence_url)
        for s in self.exec_signals:
            url = s.get("source_url") or s.get("evidence_url")
            if url:
                urls.add(url)
        return urls


class Verdict(str, Enum):
    SIGNALS = "signals"           # material signals were promoted
    QUIET = "quiet"               # nothing material AND coverage ran clean
    COVERAGE_FAILURE = "coverage_failure"  # nothing material BUT lanes missing


class BrainEventType(str, Enum):
    COVERAGE_FAILURE = "coverage_failure"
    EVIDENCE_REJECTED = "evidence_rejected"      # signal cited no / fabricated URL
    MATERIALITY_SUPPRESSED = "materiality_suppressed"
    MALFORMED_LLM_OUTPUT = "malformed_llm_output"
    CONTRADICTION_FLAGGED = "contradiction_flagged"
    SIGNAL_DEDUPED = "signal_deduped"  # near-duplicate candidates merged into one


class BrainEvent(BaseModel):
    """An auditable diagnostic. These are how the brain stays honest: every
    rejection, suppression, and coverage gap is recorded rather than hidden."""

    event_type: BrainEventType
    detail: str
    payload: dict[str, Any] = Field(default_factory=dict)
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Signal(BaseModel):
    """A promoted, decision-grade signal (maps to a published semantic_delta +
    an action_item). Invariant: at least one evidence URL and an owner.

    `owner` is the internal routing function (PMM | Sales Enablement |
    Product | Executive Review) consumed by the action router. `team_to_involve`
    is the doctrine-facing label (docs/planning/CI-OS-product-doctrine-2026-07-08.md)
    shown to the tenant's CMO/marketing leadership: Marketing | Content |
    Product | Sales Enablement | Executive. The two are separate concepts
    kept as separate fields deliberately -- renaming/repurposing `owner`
    would break action_router's existing routing contract for no doctrine
    benefit."""

    competitor_id: int
    signal_type: str
    headline: str
    what_changed: str
    why_it_matters: Optional[str] = None
    implication: Optional[str] = None
    recommended_action: str
    owner: str
    team_to_involve: str
    materiality_score: float
    confidence: Optional[float] = None
    evidence_urls: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    tenant_id: int
    competitor_id: int
    verdict: Verdict
    signals: list[Signal] = Field(default_factory=list)
    events: list[BrainEvent] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Claims.
# --------------------------------------------------------------------------


class Claim(BaseModel):
    """A competitor claim tracked over time (schema: claims). Invariant: a
    claim cannot exist without evidence URLs."""

    id: Optional[int] = None
    tenant_id: int
    competitor_id: int
    claim_text: str
    claim_type: Optional[str] = None
    # normalized subject/assertion used for deterministic contradiction checks.
    subject: Optional[str] = None
    assertion: Optional[str] = None
    evidence_urls: list[str] = Field(default_factory=list)
    repetition_count: int = 1
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    supersedes_id: Optional[int] = None
    superseded_by_id: Optional[int] = None
    active: bool = True


class Contradiction(BaseModel):
    """Two claims about the same subject that cannot both be true."""

    tenant_id: int
    competitor_id: int
    subject: str
    claim_a_id: int
    claim_b_id: int
    detail: str
    method: str = "deterministic"  # or "llm"


# --------------------------------------------------------------------------
# Living competitor thesis.
# --------------------------------------------------------------------------


class ThesisHistoryEntry(BaseModel):
    """A prior state of a thesis, preserved (never destructive rewrite)."""

    thesis: str
    confidence: Optional[float] = None
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Thesis(BaseModel):
    """A living strategic thesis for one competitor (schema: competitor_theses).
    Updates only with new evidence-backed claims; every update appends the
    prior state to history."""

    id: Optional[int] = None
    tenant_id: int
    competitor_id: int
    thesis: str
    status: str = "active"  # active | confirmed | weakened | retired
    confidence: Optional[float] = None
    evidence_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    history: list[ThesisHistoryEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# Cadence ladder: weekly pattern identification + monthly roll-up.
# Doctrine (CI-OS-product-doctrine-2026-07-08.md): daily digest -> weekly
# (pattern identification + action plan over the week's daily signals) ->
# monthly (roll-up of weeklies). Both are first-class pipeline outputs, same
# evidence-or-silence and decision-layer-not-feed invariants as Signal.
# --------------------------------------------------------------------------


class Pattern(BaseModel):
    """A pattern identified across multiple signals (weekly) or multiple
    weekly reports (monthly). Invariant: at least one evidence URL, drawn
    only from the evidence already attached to the inputs reasoned over."""

    pattern: str
    materiality_score: float = 0.0
    evidence_urls: list[str] = Field(default_factory=list)


class CadenceActionItem(BaseModel):
    """A concrete action for the period ahead. Invariant: a team_to_involve
    and at least one evidence URL -- decision-layer-not-feed applies to the
    weekly/monthly ladder exactly as it does to daily signals."""

    action: str
    team_to_involve: str
    evidence_urls: list[str] = Field(default_factory=list)


class WeeklySynthesisResult(BaseModel):
    """Output of the weekly pattern-identification pass over one week's
    daily signal ledger for one competitor."""

    tenant_id: int
    competitor_id: int
    week_start: date
    verdict: Verdict
    patterns: list[Pattern] = Field(default_factory=list)
    action_plan: list[CadenceActionItem] = Field(default_factory=list)
    events: list[BrainEvent] = Field(default_factory=list)


class MonthlySynthesisResult(BaseModel):
    """Output of the monthly roll-up pass over a month's prior weekly
    synthesis results (not raw daily signals) for one competitor."""

    tenant_id: int
    competitor_id: int
    month_start: date
    verdict: Verdict
    patterns: list[Pattern] = Field(default_factory=list)
    action_plan: list[CadenceActionItem] = Field(default_factory=list)
    events: list[BrainEvent] = Field(default_factory=list)
