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

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, Field, model_validator

from cios.learn.types import ImprovementItem, ImprovementPriority, ImprovementStatus


class ProposalKind(str, Enum):
    """The category of config adjustment a proposal makes -- kept closed
    so the (eventual) gated apply step only ever has to handle known shapes."""

    SOURCE_RETRY_TUNING = "source_retry_tuning"
    EXTRACTION_MARKER_ADDITION = "extraction_marker_addition"
    SUPPRESSION_RULE = "suppression_rule"
    COVERAGE_RECHECK = "coverage_recheck"
    SCORING_REVIEW = "scoring_review"
    PRIORITY_RECHECK = "priority_recheck"
    EVIDENCE_RECHECK = "evidence_recheck"
    ACTIONABILITY_REWRITE = "actionability_rewrite"
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


class NextSweepInstruction(BaseModel):
    """One approved learning item translated into an instruction for the
    next Hermes-run sweep. This is deliberately an artifact, not an apply
    mechanism: Hermes/Argus can read it and adjust the next run, while code,
    prompt, source, or threshold mutations remain gated."""

    tenant_id: int
    kind: ProposalKind
    priority: ImprovementPriority
    summary: str
    instruction: str
    status: str = "ready_for_next_sweep"
    change: dict = Field(default_factory=dict)
    evidence_event_ids: list[int] = Field(default_factory=list)
    source_improvement_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _requires_traceability(self) -> "NextSweepInstruction":
        if not self.instruction.strip():
            raise ValueError("a NextSweepInstruction requires instruction")
        if not self.evidence_event_ids:
            raise ValueError("a NextSweepInstruction requires evidence_event_ids")
        if not self.source_improvement_ids:
            raise ValueError("a NextSweepInstruction requires source_improvement_ids")
        return self


class NextSweepPlan(BaseModel):
    """Hermes-facing artifact for approved Argus learning.

    `skipped` is explicit so an operator can see when something was approved
    but could not safely influence the next sweep because evidence linkage is
    missing.
    """

    tenant_id: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    instructions: list[NextSweepInstruction] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class LearningApplyAction(BaseModel):
    """One gated CI-OS package change proposed from approved Argus learning.

    This is still not an auto-apply mechanism. It is the missing bridge
    between "Argus learned something" and "an operator can see exactly which
    CI-OS package policy/config should change." The guard fields make the
    Hermes boundary explicit in the artifact itself.
    """

    tenant_id: int
    kind: ProposalKind
    package_scope: str = "ci-os"
    target: str
    operation: str = "propose_policy_update"
    package_path: str
    summary: str
    instruction: str
    change: dict = Field(default_factory=dict)
    requires_human_approval: bool = True
    touches_hermes_core: bool = False
    evidence_event_ids: list[int] = Field(default_factory=list)
    source_improvement_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _requires_safe_traceable_package_target(self) -> "LearningApplyAction":
        if self.package_scope != "ci-os":
            raise ValueError("LearningApplyAction package_scope must be ci-os")
        if self.touches_hermes_core:
            raise ValueError("LearningApplyAction must not touch Hermes core")
        if not self.requires_human_approval:
            raise ValueError("LearningApplyAction requires human approval")
        if not self.package_path.strip():
            raise ValueError("LearningApplyAction requires package_path")
        unsafe_prefixes = ("/", "..", "hermes-core/", "Hermes/", "src/hermes/")
        if self.package_path.startswith(unsafe_prefixes):
            raise ValueError("LearningApplyAction package_path must stay inside the CI-OS package")
        if not self.evidence_event_ids:
            raise ValueError("LearningApplyAction requires evidence_event_ids")
        if not self.source_improvement_ids:
            raise ValueError("LearningApplyAction requires source_improvement_ids")
        if not self.summary.strip():
            raise ValueError("LearningApplyAction requires summary")
        if not self.instruction.strip():
            raise ValueError("LearningApplyAction requires instruction")
        return self


class LearningApplyPlan(BaseModel):
    """Operator-facing plan for turning approved learning into package work."""

    tenant_id: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actions: list[LearningApplyAction] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)


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
    if any(term in text for term in ("coverage", "missed the market", "missed source", "not checked")):
        return ProposalKind.COVERAGE_RECHECK
    if any(term in text for term in ("scorecard", "score", "rationale", "scoring")):
        return ProposalKind.SCORING_REVIEW
    if any(term in text for term in ("re-rank", "rerank", "priorit", "ranking")):
        return ProposalKind.PRIORITY_RECHECK
    if any(term in text for term in ("evidence", "proof", "source link", "evidence link")):
        return ProposalKind.EVIDENCE_RECHECK
    if any(term in text for term in ("actionability", "owner", "next action", "decision point")):
        return ProposalKind.ACTIONABILITY_REWRITE
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


class NextSweepPlanner:
    """Build the exact learning instructions the next Hermes sweep may read.

    Only approved items are eligible, and even approved items are skipped
    without linked learning evidence. This keeps the loop useful without
    letting chat feedback silently mutate production behavior.
    """

    _PRIORITY_ORDER = {
        ImprovementPriority.CRITICAL: 0,
        ImprovementPriority.HIGH: 1,
        ImprovementPriority.MEDIUM: 2,
        ImprovementPriority.LOW: 3,
    }

    def __init__(self, feedback_loop: Optional[FeedbackLoop] = None) -> None:
        self._feedback_loop = feedback_loop or FeedbackLoop()

    def build(
        self,
        *,
        tenant_id: int,
        items: list[ImprovementItem],
        evidence_by_item: dict[int, list[int]],
    ) -> NextSweepPlan:
        instructions: list[NextSweepInstruction] = []
        skipped: list[dict] = []

        eligible = [item for item in items if item.status == ImprovementStatus.APPROVED]
        eligible.sort(
            key=lambda item: (
                self._PRIORITY_ORDER.get(item.priority, 99),
                item.id if item.id is not None else 10**12,
            )
        )

        for item in eligible:
            if item.id is None:
                skipped.append(
                    {
                        "improvement_id": None,
                        "reason": "approved improvement has no id",
                    }
                )
                continue

            evidence_event_ids = evidence_by_item.get(item.id, [])
            if not evidence_event_ids:
                skipped.append(
                    {
                        "improvement_id": item.id,
                        "reason": "approved improvement has no linked learning evidence",
                    }
                )
                continue

            proposal = self._feedback_loop.propose(item, evidence_event_ids)
            if proposal is None:
                skipped.append(
                    {
                        "improvement_id": item.id,
                        "reason": "approved improvement has no linked learning evidence",
                    }
                )
                continue

            instructions.append(
                NextSweepInstruction(
                    tenant_id=tenant_id,
                    kind=proposal.kind,
                    priority=item.priority,
                    summary=proposal.summary,
                    instruction=proposal.summary,
                    change=proposal.change,
                    evidence_event_ids=proposal.evidence_event_ids,
                    source_improvement_ids=proposal.source_improvement_ids or [item.id],
                )
            )

        return NextSweepPlan(tenant_id=tenant_id, instructions=instructions, skipped=skipped)


_APPLY_TARGETS: dict[ProposalKind, tuple[str, str]] = {
    ProposalKind.SOURCE_RETRY_TUNING: ("source_retry_policy", "config/source-retry-policy.yaml"),
    ProposalKind.EXTRACTION_MARKER_ADDITION: (
        "extraction_marker_policy",
        "config/extraction-markers.yaml",
    ),
    ProposalKind.SUPPRESSION_RULE: ("suppression_policy", "config/suppression-rules.yaml"),
    ProposalKind.COVERAGE_RECHECK: ("source_coverage_policy", "config/source-coverage-policy.yaml"),
    ProposalKind.SCORING_REVIEW: ("argus_scoring_policy", "config/argus-scoring-policy.yaml"),
    ProposalKind.PRIORITY_RECHECK: ("argus_scoring_policy", "config/argus-scoring-policy.yaml"),
    ProposalKind.EVIDENCE_RECHECK: ("argus_evidence_policy", "config/argus-evidence-policy.yaml"),
    ProposalKind.ACTIONABILITY_REWRITE: (
        "recommendation_actionability_policy",
        "config/recommendation-actionability-policy.yaml",
    ),
    ProposalKind.OTHER: ("manual_learning_review", "docs/workspace/argus-learning-apply-review.md"),
}


class LearningApplyPlanner:
    """Build the safe apply plan after next-sweep learning has been approved.

    The previous loop could influence one run. This planner makes durable
    follow-up work explicit while keeping two hard boundaries: CI-OS package
    only, and human-approved before mutation.
    """

    _PRIORITY_ORDER = NextSweepPlanner._PRIORITY_ORDER

    def build(
        self,
        *,
        tenant_id: int,
        instructions: list[NextSweepInstruction],
    ) -> LearningApplyPlan:
        actions: list[LearningApplyAction] = []
        skipped: list[dict] = []

        ordered = sorted(
            instructions,
            key=lambda instruction: (
                self._PRIORITY_ORDER.get(instruction.priority, 99),
                instruction.source_improvement_ids[0] if instruction.source_improvement_ids else 10**12,
            ),
        )

        for instruction in ordered:
            trace = {"source_improvement_ids": list(instruction.source_improvement_ids)}
            if instruction.tenant_id != tenant_id:
                skipped.append(
                    {
                        **trace,
                        "reason": "instruction tenant_id does not match apply plan tenant_id",
                    }
                )
                continue
            if instruction.status != "ready_for_next_sweep":
                skipped.append(
                    {
                        **trace,
                        "reason": "instruction is not ready for apply planning",
                    }
                )
                continue

            target, package_path = _APPLY_TARGETS[instruction.kind]
            actions.append(
                LearningApplyAction(
                    tenant_id=tenant_id,
                    kind=instruction.kind,
                    target=target,
                    package_path=package_path,
                    summary=instruction.summary,
                    instruction=instruction.instruction,
                    change=instruction.change,
                    evidence_event_ids=instruction.evidence_event_ids,
                    source_improvement_ids=instruction.source_improvement_ids,
                )
            )

        return LearningApplyPlan(tenant_id=tenant_id, actions=actions, skipped=skipped)
