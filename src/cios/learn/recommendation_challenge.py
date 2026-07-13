"""Turn user challenges to Argus recommendations into durable learning.

This is the first conversational learning bridge: when a user challenges why
Argus prioritized something, the system records the challenge and queues a
gated improvement for the next sweep. It does not auto-change rules.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from cios.learn.recorder import ImprovementQueueRepository, LearningEventRepository, LearningRecorder
from cios.learn.types import ImprovementItem, ImprovementPriority, LearningEvent, LearningEventType


class RecommendationChallengeCategory(str, Enum):
    """Why the user challenged the recommendation."""

    PRIORITY = "priority"
    EVIDENCE = "evidence"
    SCORING = "scoring"
    COVERAGE = "coverage"
    ACTIONABILITY = "actionability"


class RecommendationChallengeResult(BaseModel):
    """Saved learning artifacts from one recommendation challenge."""

    event: LearningEvent
    improvement: Optional[ImprovementItem] = None
    next_sweep_instruction: Optional[str] = None


_CATEGORY_PRIORITY = {
    RecommendationChallengeCategory.COVERAGE: ImprovementPriority.CRITICAL,
    RecommendationChallengeCategory.SCORING: ImprovementPriority.HIGH,
    RecommendationChallengeCategory.EVIDENCE: ImprovementPriority.HIGH,
    RecommendationChallengeCategory.PRIORITY: ImprovementPriority.HIGH,
    RecommendationChallengeCategory.ACTIONABILITY: ImprovementPriority.MEDIUM,
}


class RecommendationChallengeRecorder:
    """Records challenges against Argus recommendations.

    The underlying `LearningRecorder` owns persistence. This class owns the
    product-intelligence wording and priority rules so chat/UI flows do not
    invent their own learning behavior.
    """

    def __init__(
        self,
        learning_events: LearningEventRepository,
        improvement_queue: ImprovementQueueRepository,
    ) -> None:
        self._recorder = LearningRecorder(learning_events, improvement_queue)

    def record_challenge(
        self,
        *,
        tenant_id: int,
        recommendation_id: int,
        run_id: Optional[str],
        challenge: str,
        category: RecommendationChallengeCategory | str,
        scorecard_dimension: Optional[str] = None,
    ) -> RecommendationChallengeResult:
        normalized_challenge = challenge.strip()
        if not normalized_challenge:
            raise ValueError("recommendation challenge requires challenge text")
        if recommendation_id <= 0:
            raise ValueError("recommendation challenge requires recommendation_id")
        category = RecommendationChallengeCategory(category)

        lesson = self._lesson(
            recommendation_id=recommendation_id,
            challenge=normalized_challenge,
            category=category,
            scorecard_dimension=scorecard_dimension,
        )
        proposed_change = self._proposed_change(
            recommendation_id=recommendation_id,
            challenge=normalized_challenge,
            category=category,
            scorecard_dimension=scorecard_dimension,
        )
        event, improvement = self._recorder.record(
            tenant_id=tenant_id,
            event_type=LearningEventType.RECOMMENDATION_CHALLENGE,
            lesson=lesson,
            run_id=run_id,
            proposed_change=proposed_change,
            source=f"argus_recommendation:{recommendation_id}",
            priority=_CATEGORY_PRIORITY[category],
        )
        return RecommendationChallengeResult(
            event=event,
            improvement=improvement,
            next_sweep_instruction=proposed_change,
        )

    @staticmethod
    def _lesson(
        *,
        recommendation_id: int,
        challenge: str,
        category: RecommendationChallengeCategory,
        scorecard_dimension: Optional[str],
    ) -> str:
        dimension = f"; challenged scorecard dimension: {scorecard_dimension}" if scorecard_dimension else ""
        return (
            f"User challenged recommendation {recommendation_id}; "
            f"category: {category.value}{dimension}; challenge: {challenge}"
        )

    @staticmethod
    def _proposed_change(
        *,
        recommendation_id: int,
        challenge: str,
        category: RecommendationChallengeCategory,
        scorecard_dimension: Optional[str],
    ) -> str:
        dimension = f" and the {scorecard_dimension} scorecard dimension" if scorecard_dimension else ""
        if category is RecommendationChallengeCategory.COVERAGE:
            return (
                f"Re-evaluate recommendation {recommendation_id} in the next sweep by auditing source coverage, "
                f"missed competitors, failed sources, and quiet-day assumptions raised by: {challenge}"
            )
        if category is RecommendationChallengeCategory.SCORING:
            return (
                f"Re-evaluate recommendation {recommendation_id}{dimension}; compare scorecard rationale "
                f"against evidence strength, failed sources, and competing market moves raised by: {challenge}"
            )
        if category is RecommendationChallengeCategory.EVIDENCE:
            return (
                f"Re-evaluate recommendation {recommendation_id} by requiring stronger evidence links or demoting "
                f"the recommendation if proof is weak; user challenge: {challenge}"
            )
        if category is RecommendationChallengeCategory.ACTIONABILITY:
            return (
                f"Rework recommendation {recommendation_id} into a clearer owner, next action, and decision point; "
                f"user challenge: {challenge}"
            )
        return (
            f"Re-rank recommendation {recommendation_id} against other current market moves and explain why it should "
            f"or should not stay prioritized; user challenge: {challenge}"
        )
