"""Capture learning events from run outcomes and classify them into
improvement_queue candidates.

Storage access is via injected repository protocols only -- no direct DB
access here (tests use in-memory fakes). Every outcome that reaches this
module becomes a `LearningEvent` row (manifesto doctrine: Argus learns from
every run, not just failures) -- some event types additionally raise an
`ImprovementItem` when the outcome implies a concrete fix candidate.
"""

from __future__ import annotations

from typing import Optional, Protocol

from cios.learn.types import (
    ImprovementItem,
    ImprovementPriority,
    LearningEvent,
    LearningEventType,
    QualityReview,
    QualityReviewStatus,
)


class LearningEventRepository(Protocol):
    def insert(self, event: LearningEvent) -> LearningEvent: ...


class ImprovementQueueRepository(Protocol):
    def insert(self, item: ImprovementItem) -> ImprovementItem: ...


# event_type -> (priority, source label) for the improvement item this
# event type raises. Types absent from this map produce a learning event
# only (e.g. a positive quality verdict has no fix to queue).
_IMPROVEMENT_PRIORITY: dict[LearningEventType, ImprovementPriority] = {
    LearningEventType.FETCH_FAILURE: ImprovementPriority.MEDIUM,
    LearningEventType.EXTRACTION_MISS: ImprovementPriority.MEDIUM,
    LearningEventType.FALSE_NEGATIVE: ImprovementPriority.CRITICAL,
    LearningEventType.USER_FEEDBACK: ImprovementPriority.LOW,
    LearningEventType.RECOMMENDATION_CHALLENGE: ImprovementPriority.HIGH,
}


class LearningRecorder:
    """Turns run outcomes into `learning_events` (+ `improvement_queue` where
    the outcome implies a fix candidate)."""

    def __init__(
        self,
        learning_events: LearningEventRepository,
        improvement_queue: ImprovementQueueRepository,
    ) -> None:
        self._learning_events = learning_events
        self._improvement_queue = improvement_queue

    def record(
        self,
        tenant_id: int,
        event_type: LearningEventType,
        lesson: str,
        run_id: Optional[str] = None,
        proposed_change: Optional[str] = None,
        source: Optional[str] = None,
        priority: Optional[ImprovementPriority] = None,
    ) -> tuple[LearningEvent, Optional[ImprovementItem]]:
        """Record one learning event, then classify it into an improvement
        queue item if this event type carries a fix candidate."""
        event = self._learning_events.insert(
            LearningEvent(
                tenant_id=tenant_id,
                run_id=run_id,
                event_type=event_type,
                lesson=lesson,
                proposed_change=proposed_change,
            )
        )

        if not proposed_change:
            return event, None

        resolved_priority = priority or _IMPROVEMENT_PRIORITY.get(event_type)
        if resolved_priority is None:
            return event, None

        item = self._improvement_queue.insert(
            ImprovementItem(
                tenant_id=tenant_id,
                source=source or event_type.value,
                problem=lesson,
                proposed_fix=proposed_change,
                priority=resolved_priority,
            )
        )
        return event, item

    def record_fetch_failure(
        self, tenant_id: int, run_id: str, source_url: str, detail: str, proposed_change: str
    ) -> tuple[LearningEvent, Optional[ImprovementItem]]:
        return self.record(
            tenant_id=tenant_id,
            event_type=LearningEventType.FETCH_FAILURE,
            lesson=f"fetch failed for {source_url}: {detail}",
            run_id=run_id,
            proposed_change=proposed_change,
            source=source_url,
        )

    def record_extraction_miss(
        self, tenant_id: int, run_id: str, source_url: str, detail: str, proposed_change: str
    ) -> tuple[LearningEvent, Optional[ImprovementItem]]:
        return self.record(
            tenant_id=tenant_id,
            event_type=LearningEventType.EXTRACTION_MISS,
            lesson=f"extraction missed expected content at {source_url}: {detail}",
            run_id=run_id,
            proposed_change=proposed_change,
            source=source_url,
        )

    def record_quality_verdict(
        self, tenant_id: int, review: QualityReview
    ) -> tuple[LearningEvent, Optional[ImprovementItem]]:
        """Classify a quality reviewer verdict. A `failed` review with
        required fixes becomes an improvement candidate; `passed`/`pending`
        become a learning event only."""
        if review.status != QualityReviewStatus.FAILED or not review.required_fixes:
            lesson = f"quality review {review.status.value} for run {review.run_id}"
            return self.record(
                tenant_id=tenant_id,
                event_type=LearningEventType.QUALITY_VERDICT,
                lesson=lesson,
                run_id=review.run_id,
            )

        fixes = "; ".join(str(fix) for fix in review.required_fixes)
        return self.record(
            tenant_id=tenant_id,
            event_type=LearningEventType.QUALITY_VERDICT,
            lesson=f"quality review failed for run {review.run_id}: {fixes}",
            run_id=review.run_id,
            proposed_change=fixes,
            source=review.review_type,
            priority=ImprovementPriority.HIGH,
        )

    def record_user_feedback(
        self, tenant_id: int, run_id: Optional[str], feedback: str, proposed_change: Optional[str] = None
    ) -> tuple[LearningEvent, Optional[ImprovementItem]]:
        return self.record(
            tenant_id=tenant_id,
            event_type=LearningEventType.USER_FEEDBACK,
            lesson=feedback,
            run_id=run_id,
            proposed_change=proposed_change,
        )
