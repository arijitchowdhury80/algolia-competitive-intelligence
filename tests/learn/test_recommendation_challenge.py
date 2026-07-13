from __future__ import annotations

import pytest

from cios.learn.recommendation_challenge import (
    RecommendationChallengeCategory,
    RecommendationChallengeRecorder,
)
from cios.learn.types import ImprovementItem, ImprovementPriority, LearningEvent, LearningEventType


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
    return RecommendationChallengeRecorder(events, queue), events, queue


def test_scoring_challenge_records_learning_event_and_high_priority_improvement() -> None:
    recorder, events, queue = _recorder()

    result = recorder.record_challenge(
        tenant_id=1,
        recommendation_id=7,
        run_id="run-2026-07-10",
        challenge=(
            "Why prioritize Constructor when Coveo had five failed sources and "
            "the audience demand proof looks thin?"
        ),
        category=RecommendationChallengeCategory.SCORING,
        scorecard_dimension="audience_demand",
    )

    assert result.event.event_type == LearningEventType.RECOMMENDATION_CHALLENGE
    assert result.event.run_id == "run-2026-07-10"
    assert "recommendation 7" in result.event.lesson
    assert "audience_demand" in result.event.lesson
    assert "Constructor" in result.event.lesson
    assert result.improvement is not None
    assert result.improvement.priority == ImprovementPriority.HIGH
    assert result.improvement.source == "argus_recommendation:7"
    assert "Re-evaluate recommendation 7" in result.improvement.proposed_fix
    assert "audience_demand" in result.improvement.proposed_fix
    assert result.next_sweep_instruction == result.improvement.proposed_fix
    assert events.rows == [result.event]
    assert queue.rows == [result.improvement]


def test_coverage_challenge_is_critical_because_it_can_mean_argus_missed_the_market() -> None:
    recorder, _events, _queue = _recorder()

    result = recorder.record_challenge(
        tenant_id=1,
        recommendation_id=11,
        run_id=None,
        challenge="You missed Bloomreach and Coveo entirely today.",
        category=RecommendationChallengeCategory.COVERAGE,
    )

    assert result.improvement is not None
    assert result.improvement.priority == ImprovementPriority.CRITICAL
    assert "source coverage" in result.improvement.proposed_fix
    assert "Bloomreach" in result.improvement.problem


def test_blank_challenge_is_rejected_before_learning_rows_are_written() -> None:
    recorder, events, queue = _recorder()

    with pytest.raises(ValueError, match="challenge"):
        recorder.record_challenge(
            tenant_id=1,
            recommendation_id=7,
            run_id="run-1",
            challenge=" ",
            category=RecommendationChallengeCategory.EVIDENCE,
        )

    assert events.rows == []
    assert queue.rows == []
