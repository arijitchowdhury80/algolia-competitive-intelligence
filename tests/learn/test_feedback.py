"""Tests for the feedback loop: proposal evidence linkage, classification,
and the injected-synthesizer extension point."""

from __future__ import annotations

from cios.learn.feedback import (
    FeedbackLoop,
    FeedbackProposal,
    LearningApplyPlanner,
    NextSweepPlanner,
    NextSweepInstruction,
    ProposalKind,
)
from cios.learn.types import ImprovementItem, ImprovementPriority, ImprovementStatus


def _item(**overrides) -> ImprovementItem:
    defaults = dict(
        id=1,
        tenant_id=1,
        source="https://example.com/blog",
        problem="fetch failed repeatedly with http 503",
        proposed_fix="add exponential backoff retry",
        priority=ImprovementPriority.MEDIUM,
    )
    defaults.update(overrides)
    return ImprovementItem(**defaults)


def test_propose_returns_none_without_evidence():
    loop = FeedbackLoop()

    proposal = loop.propose(_item(), evidence_event_ids=[])

    assert proposal is None


def test_proposal_cannot_be_constructed_without_evidence_event_ids():
    try:
        FeedbackProposal(tenant_id=1, kind=ProposalKind.OTHER, summary="x", evidence_event_ids=[])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_propose_classifies_retry_related_item_as_source_retry_tuning():
    loop = FeedbackLoop()

    proposal = loop.propose(_item(), evidence_event_ids=[10, 11])

    assert proposal is not None
    assert proposal.kind == ProposalKind.SOURCE_RETRY_TUNING
    assert proposal.evidence_event_ids == [10, 11]
    assert proposal.source_improvement_ids == [1]


def test_propose_classifies_extraction_marker_item():
    loop = FeedbackLoop()
    item = _item(problem="extraction missed the price selector", proposed_fix="add new CSS marker")

    proposal = loop.propose(item, evidence_event_ids=[5])

    assert proposal.kind == ProposalKind.EXTRACTION_MARKER_ADDITION


def test_propose_classifies_suppression_rule_item():
    loop = FeedbackLoop()
    item = _item(problem="noisy duplicate alerts for the same claim", proposed_fix="suppress repeat within 24h")

    proposal = loop.propose(item, evidence_event_ids=[5])

    assert proposal.kind == ProposalKind.SUPPRESSION_RULE


def test_propose_classifies_coverage_recheck_item():
    loop = FeedbackLoop()
    item = _item(
        problem="recommendation challenge said Coveo coverage was incomplete",
        proposed_fix="re-audit source coverage before ranking Constructor again",
    )

    proposal = loop.propose(item, evidence_event_ids=[5])

    assert proposal.kind == ProposalKind.COVERAGE_RECHECK


def test_propose_classifies_scoring_review_item():
    loop = FeedbackLoop()
    item = _item(
        problem="recommendation challenge said the scorecard rationale was thin",
        proposed_fix="compare scorecard rationale against evidence strength before promoting action",
    )

    proposal = loop.propose(item, evidence_event_ids=[5])

    assert proposal.kind == ProposalKind.SCORING_REVIEW


def test_propose_classifies_priority_recheck_item():
    loop = FeedbackLoop()
    item = _item(
        problem="recommendation challenge asked why Constructor was prioritized",
        proposed_fix="re-rank recommendation against other current market moves",
    )

    proposal = loop.propose(item, evidence_event_ids=[5])

    assert proposal.kind == ProposalKind.PRIORITY_RECHECK


def test_propose_classifies_evidence_recheck_item():
    loop = FeedbackLoop()
    item = _item(
        problem="recommendation challenge said proof links were weak",
        proposed_fix="require stronger evidence links before keeping the recommendation actionable",
    )

    proposal = loop.propose(item, evidence_event_ids=[5])

    assert proposal.kind == ProposalKind.EVIDENCE_RECHECK


def test_propose_all_skips_items_without_evidence():
    loop = FeedbackLoop()
    items = [_item(id=1), _item(id=2, problem="unrelated problem", proposed_fix="unrelated fix")]

    proposals = loop.propose_all(items, evidence_by_item={1: [7]})

    assert len(proposals) == 1
    assert proposals[0].source_improvement_ids == [1]


class ScriptedSynthesizer:
    def __init__(self, result):
        self._result = result

    def synthesize(self, item, evidence_event_ids):
        return self._result


def test_injected_synthesizer_overrides_deterministic_classification():
    scripted = FeedbackProposal(
        tenant_id=1,
        kind=ProposalKind.OTHER,
        summary="LLM-synthesized proposal",
        evidence_event_ids=[99],
    )
    loop = FeedbackLoop(synthesizer=ScriptedSynthesizer(scripted))

    proposal = loop.propose(_item(), evidence_event_ids=[1])

    assert proposal is scripted


def test_synthesizer_returning_none_falls_back_to_deterministic_rules():
    loop = FeedbackLoop(synthesizer=ScriptedSynthesizer(None))

    proposal = loop.propose(_item(), evidence_event_ids=[1])

    assert proposal is not None
    assert proposal.kind == ProposalKind.SOURCE_RETRY_TUNING


def test_next_sweep_planner_turns_only_approved_evidence_backed_items_into_instructions():
    planner = NextSweepPlanner()
    approved = _item(
        id=1,
        priority=ImprovementPriority.CRITICAL,
        status=ImprovementStatus.APPROVED,
        problem="recommendation challenge said coverage missed Coveo",
        proposed_fix="re-audit Coveo source coverage before ranking Constructor",
    )
    open_item = _item(
        id=2,
        status=ImprovementStatus.OPEN,
        problem="fetch failed repeatedly with http 503",
        proposed_fix="add exponential backoff retry",
    )
    approved_without_evidence = _item(
        id=3,
        status=ImprovementStatus.APPROVED,
        problem="quality review found unclear action",
        proposed_fix="make owner and next action explicit",
    )

    plan = planner.build(
        tenant_id=1,
        items=[open_item, approved_without_evidence, approved],
        evidence_by_item={1: [101, 102]},
    )

    assert len(plan.instructions) == 1
    instruction = plan.instructions[0]
    assert instruction.tenant_id == 1
    assert instruction.priority == ImprovementPriority.CRITICAL
    assert instruction.status == "ready_for_next_sweep"
    assert instruction.source_improvement_ids == [1]
    assert instruction.evidence_event_ids == [101, 102]
    assert "re-audit Coveo source coverage" in instruction.instruction
    assert plan.skipped == [
        {
            "improvement_id": 3,
            "reason": "approved improvement has no linked learning evidence",
        }
    ]


def test_next_sweep_planner_orders_instructions_by_priority_then_id():
    planner = NextSweepPlanner()
    medium = _item(
        id=10,
        status=ImprovementStatus.APPROVED,
        priority=ImprovementPriority.MEDIUM,
        problem="medium",
        proposed_fix="medium fix",
    )
    critical = _item(
        id=11,
        status=ImprovementStatus.APPROVED,
        priority=ImprovementPriority.CRITICAL,
        problem="critical",
        proposed_fix="critical fix",
    )
    high = _item(
        id=12,
        status=ImprovementStatus.APPROVED,
        priority=ImprovementPriority.HIGH,
        problem="high",
        proposed_fix="high fix",
    )

    plan = planner.build(
        tenant_id=1,
        items=[medium, critical, high],
        evidence_by_item={10: [10], 11: [11], 12: [12]},
    )

    assert [instruction.source_improvement_ids[0] for instruction in plan.instructions] == [11, 12, 10]


def test_learning_apply_planner_turns_ready_instructions_into_package_scoped_actions():
    planner = LearningApplyPlanner()
    instruction = NextSweepInstruction(
        tenant_id=1,
        kind=ProposalKind.SCORING_REVIEW,
        priority=ImprovementPriority.HIGH,
        summary="Require stronger scorecard evidence before promotion.",
        instruction="Raise the action threshold until the challenged scorecard dimension is repaired.",
        change={"action_threshold": 84},
        evidence_event_ids=[501],
        source_improvement_ids=[301],
    )

    plan = planner.build(tenant_id=1, instructions=[instruction])

    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.tenant_id == 1
    assert action.kind == ProposalKind.SCORING_REVIEW
    assert action.package_scope == "ci-os"
    assert action.target == "argus_scoring_policy"
    assert action.operation == "propose_policy_update"
    assert action.package_path == "config/argus-scoring-policy.yaml"
    assert action.requires_human_approval is True
    assert action.touches_hermes_core is False
    assert action.evidence_event_ids == [501]
    assert action.source_improvement_ids == [301]
    assert action.change == {"action_threshold": 84}
    assert plan.skipped == []


def test_learning_apply_planner_maps_coverage_and_source_retry_to_distinct_safe_targets():
    planner = LearningApplyPlanner()
    coverage = NextSweepInstruction(
        tenant_id=1,
        kind=ProposalKind.COVERAGE_RECHECK,
        priority=ImprovementPriority.CRITICAL,
        summary="Re-audit Coveo before ranking Constructor.",
        instruction="Run a coverage recheck for Coveo product and conversation sources.",
        change={"company": "Coveo"},
        evidence_event_ids=[701],
        source_improvement_ids=[401],
    )
    retry = NextSweepInstruction(
        tenant_id=1,
        kind=ProposalKind.SOURCE_RETRY_TUNING,
        priority=ImprovementPriority.MEDIUM,
        summary="Add bounded retry for HTTP 503 fetch failures.",
        instruction="Tune source retry policy for repeated 503 failures.",
        change={"source": "https://coveo.com/blog", "proposed_fix": "add backoff"},
        evidence_event_ids=[702],
        source_improvement_ids=[402],
    )

    plan = planner.build(tenant_id=1, instructions=[retry, coverage])

    assert [(action.kind, action.target, action.package_path) for action in plan.actions] == [
        (ProposalKind.COVERAGE_RECHECK, "source_coverage_policy", "config/source-coverage-policy.yaml"),
        (ProposalKind.SOURCE_RETRY_TUNING, "source_retry_policy", "config/source-retry-policy.yaml"),
    ]
    assert all(action.package_scope == "ci-os" for action in plan.actions)
    assert all(action.requires_human_approval for action in plan.actions)
    assert all(action.touches_hermes_core is False for action in plan.actions)


def test_learning_apply_planner_skips_non_ready_and_wrong_tenant_instructions():
    planner = LearningApplyPlanner()
    non_ready = NextSweepInstruction(
        tenant_id=1,
        kind=ProposalKind.ACTIONABILITY_REWRITE,
        priority=ImprovementPriority.MEDIUM,
        summary="Rewrite unclear action.",
        instruction="Make the owner and decision point explicit.",
        status="draft",
        evidence_event_ids=[801],
        source_improvement_ids=[501],
    )
    wrong_tenant = NextSweepInstruction(
        tenant_id=2,
        kind=ProposalKind.EVIDENCE_RECHECK,
        priority=ImprovementPriority.HIGH,
        summary="Require stronger proof links.",
        instruction="Recheck evidence before promoting the read.",
        evidence_event_ids=[802],
        source_improvement_ids=[502],
    )

    plan = planner.build(tenant_id=1, instructions=[non_ready, wrong_tenant])

    assert plan.actions == []
    assert plan.skipped == [
        {"source_improvement_ids": [502], "reason": "instruction tenant_id does not match apply plan tenant_id"},
        {"source_improvement_ids": [501], "reason": "instruction is not ready for apply planning"},
    ]
