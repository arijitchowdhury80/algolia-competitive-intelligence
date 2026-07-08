"""Tests for the learning-event recorder: capture + classification into
improvement_queue, and tenant scoping."""

from __future__ import annotations

from cios.learn.recorder import LearningRecorder
from cios.learn.types import (
    ImprovementItem,
    ImprovementPriority,
    LearningEvent,
    LearningEventType,
    QualityReview,
    QualityReviewStatus,
)


class FakeLearningEventRepository:
    def __init__(self):
        self._next_id = 1
        self.rows: list[LearningEvent] = []

    def insert(self, event: LearningEvent) -> LearningEvent:
        saved = event.model_copy(update={"id": self._next_id})
        self._next_id += 1
        self.rows.append(saved)
        return saved


class FakeImprovementQueueRepository:
    def __init__(self):
        self._next_id = 1
        self.rows: list[ImprovementItem] = []

    def insert(self, item: ImprovementItem) -> ImprovementItem:
        saved = item.model_copy(update={"id": self._next_id})
        self._next_id += 1
        self.rows.append(saved)
        return saved


def _recorder():
    events = FakeLearningEventRepository()
    queue = FakeImprovementQueueRepository()
    return LearningRecorder(events, queue), events, queue


def test_record_fetch_failure_writes_learning_event_and_improvement_item():
    recorder, events, queue = _recorder()

    event, item = recorder.record_fetch_failure(
        tenant_id=1,
        run_id="run-1",
        source_url="https://example.com/blog",
        detail="timeout after 30s",
        proposed_change="raise retry count to 3 with backoff",
    )

    assert event.id is not None
    assert event.event_type == LearningEventType.FETCH_FAILURE
    assert events.rows == [event]
    assert item is not None
    assert item.priority == ImprovementPriority.MEDIUM
    assert queue.rows == [item]


def test_record_without_proposed_change_writes_learning_event_only():
    recorder, events, queue = _recorder()

    event, item = recorder.record(
        tenant_id=1,
        event_type=LearningEventType.QUALITY_VERDICT,
        lesson="run passed clean",
    )

    assert event.id is not None
    assert item is None
    assert queue.rows == []


def test_record_quality_verdict_passed_produces_learning_event_only():
    recorder, events, queue = _recorder()
    review = QualityReview(
        id=1, tenant_id=1, run_id="run-2", status=QualityReviewStatus.PASSED
    )

    event, item = recorder.record_quality_verdict(tenant_id=1, review=review)

    assert event.event_type == LearningEventType.QUALITY_VERDICT
    assert item is None


def test_record_quality_verdict_failed_with_fixes_raises_high_priority_improvement():
    recorder, events, queue = _recorder()
    review = QualityReview(
        id=1,
        tenant_id=1,
        run_id="run-3",
        status=QualityReviewStatus.FAILED,
        required_fixes=[{"issue": "missing evidence url"}],
    )

    event, item = recorder.record_quality_verdict(tenant_id=1, review=review)

    assert item is not None
    assert item.priority == ImprovementPriority.HIGH
    assert "missing evidence url" in item.proposed_fix


def test_record_false_negative_defaults_to_critical_priority():
    recorder, events, queue = _recorder()

    event, item = recorder.record(
        tenant_id=1,
        event_type=LearningEventType.FALSE_NEGATIVE,
        lesson="missed a competitor pricing change",
        proposed_change="add pricing page to source ledger",
    )

    assert item is not None
    assert item.priority == ImprovementPriority.CRITICAL


def test_events_are_tenant_scoped_in_storage():
    recorder, events, queue = _recorder()

    recorder.record_user_feedback(tenant_id=1, run_id=None, feedback="report was noisy")
    recorder.record_user_feedback(tenant_id=2, run_id=None, feedback="report was noisy for tenant 2")

    tenant_1_events = [e for e in events.rows if e.tenant_id == 1]
    tenant_2_events = [e for e in events.rows if e.tenant_id == 2]
    assert len(tenant_1_events) == 1
    assert len(tenant_2_events) == 1
    assert tenant_1_events[0].id != tenant_2_events[0].id
