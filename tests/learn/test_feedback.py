"""Tests for the feedback loop: proposal evidence linkage, classification,
and the injected-synthesizer extension point."""

from __future__ import annotations

from cios.learn.feedback import FeedbackLoop, FeedbackProposal, ProposalKind
from cios.learn.types import ImprovementItem, ImprovementPriority


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
