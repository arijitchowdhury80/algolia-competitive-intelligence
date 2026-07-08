"""Apply-loop: turn improvement_queue items into concrete, evidence-backed
config-adjustment proposals.

Nothing here auto-applies a change (manifesto Phase 7 "requires approval"
list covers code changes, semantic thresholds, credentials, action-routing
policy, and report doctrine). This module only produces `FeedbackProposal`
objects for a human (or a future gated apply step) to act on. Deterministic
rule-based synthesis lives here; `ImprovementSynthesizer` is the marked
extension point where Gate 4's LLM-driven improvement synthesis plugs in.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, Field, model_validator

from cios.learn.types import ImprovementItem


class ProposalKind(str, Enum):
    """The category of config adjustment a proposal makes -- kept closed
    so the (eventual) gated apply step only ever has to handle known shapes."""

    SOURCE_RETRY_TUNING = "source_retry_tuning"
    EXTRACTION_MARKER_ADDITION = "extraction_marker_addition"
    SUPPRESSION_RULE = "suppression_rule"
    OTHER = "other"


class FeedbackProposal(BaseModel):
    """A structured, evidence-backed config-adjustment proposal.

    Never auto-applied. `evidence_event_ids` traces back to the learning
    events (schema: learning_events.id) that justify the change --
    mirrors the claims table's `claim_needs_evidence` invariant: no
    proposal without evidence.
    """

    tenant_id: int
    kind: ProposalKind
    summary: str
    change: dict = Field(default_factory=dict)
    evidence_event_ids: list[int] = Field(default_factory=list)
    source_improvement_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _requires_evidence(self) -> "FeedbackProposal":
        if not self.evidence_event_ids:
            raise ValueError("a FeedbackProposal must carry at least one evidence event id")
        return self


class ImprovementSynthesizer(Protocol):
    """Extension point for LLM-driven improvement synthesis (Gate 4 brain
    territory). The default `FeedbackLoop` uses deterministic rules only;
    a Gate 4 implementation of this Protocol can be injected to produce
    richer proposals from the same improvement queue + evidence."""

    def synthesize(
        self, item: ImprovementItem, evidence_event_ids: list[int]
    ) -> Optional[FeedbackProposal]: ...


def _classify_kind(item: ImprovementItem) -> ProposalKind:
    problem = (item.problem or "").lower()
    fix = (item.proposed_fix or "").lower()
    text = f"{problem} {fix}"
    if any(term in text for term in ("retry", "timeout", "backoff", "fetch failed", "http")):
        return ProposalKind.SOURCE_RETRY_TUNING
    if any(term in text for term in ("marker", "selector", "extraction", "parse")):
        return ProposalKind.EXTRACTION_MARKER_ADDITION
    if any(term in text for term in ("suppress", "noisy", "false positive", "duplicate")):
        return ProposalKind.SUPPRESSION_RULE
    return ProposalKind.OTHER


class FeedbackLoop:
    """Given the improvement queue, produce structured, evidence-linked
    config-adjustment proposals. Deterministic by default; an injected
    `ImprovementSynthesizer` (Gate 4) may override or augment per item."""

    def __init__(self, synthesizer: Optional[ImprovementSynthesizer] = None) -> None:
        self._synthesizer = synthesizer

    def propose(
        self, item: ImprovementItem, evidence_event_ids: list[int]
    ) -> Optional[FeedbackProposal]:
        """Produce one proposal for one improvement_queue item. Returns
        None if there is no evidence to link (never propose blind)."""
        if not evidence_event_ids:
            return None

        if self._synthesizer is not None:
            synthesized = self._synthesizer.synthesize(item, evidence_event_ids)
            if synthesized is not None:
                return synthesized

        kind = _classify_kind(item)
        return FeedbackProposal(
            tenant_id=item.tenant_id,
            kind=kind,
            summary=item.proposed_fix or item.problem,
            change={
                "source": item.source,
                "problem": item.problem,
                "proposed_fix": item.proposed_fix,
                "priority": item.priority.value,
            },
            evidence_event_ids=evidence_event_ids,
            source_improvement_ids=[item.id] if item.id is not None else [],
        )

    def propose_all(
        self, items: list[ImprovementItem], evidence_by_item: dict[int, list[int]]
    ) -> list[FeedbackProposal]:
        """Batch form of `propose`. `evidence_by_item` maps improvement_queue
        id -> learning_event ids that justify it. Items missing from the map
        (or with an id of None) are skipped -- no proposal without evidence."""
        proposals: list[FeedbackProposal] = []
        for item in items:
            if item.id is None:
                continue
            evidence_event_ids = evidence_by_item.get(item.id, [])
            proposal = self.propose(item, evidence_event_ids)
            if proposal is not None:
                proposals.append(proposal)
        return proposals
