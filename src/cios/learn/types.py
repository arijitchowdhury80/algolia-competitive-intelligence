"""Shared data types for the argus-learning-loop skill.

Mirrors src/cios/db/schema.sql: learning_events, improvement_queue,
quality_reviews, false_negative_audits. `suppressed_diagnostics` is read
(not owned) here -- it is written by the quality reviewer / dashboard,
per docs/planning/Argus-skill-build-matrix.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class LearningEventType(str, Enum):
    """What kind of run outcome produced this lesson (manifesto Phase 7 inputs)."""

    FETCH_FAILURE = "fetch_failure"
    EXTRACTION_MISS = "extraction_miss"
    QUALITY_VERDICT = "quality_verdict"
    USER_FEEDBACK = "user_feedback"
    FALSE_NEGATIVE = "false_negative"
    DELIVERY_OUTCOME = "delivery_outcome"


class LearningEventStatus(str, Enum):
    OPEN = "open"
    APPLIED = "applied"
    REJECTED = "rejected"


class ImprovementPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImprovementStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"


class QualityReviewStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class FalseNegativeAuditStatus(str, Enum):
    PENDING = "pending"
    CLEAN = "clean"
    AT_RISK = "at_risk"
    FAILED = "failed"


class LearningEvent(BaseModel):
    """A lesson + proposed change captured from a run (schema: learning_events)."""

    id: Optional[int] = None
    tenant_id: int
    run_id: Optional[str] = None
    event_type: LearningEventType
    lesson: str
    proposed_change: Optional[str] = None
    status: LearningEventStatus = LearningEventStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImprovementItem(BaseModel):
    """A gated code/threshold/policy change candidate (schema: improvement_queue).

    Per manifesto Phase 7 "requires approval" list, nothing here is
    auto-applied -- status only advances past `open` via human approval.
    """

    id: Optional[int] = None
    tenant_id: int
    source: Optional[str] = None
    problem: str
    proposed_fix: Optional[str] = None
    priority: ImprovementPriority = ImprovementPriority.MEDIUM
    status: ImprovementStatus = ImprovementStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QualityReview(BaseModel):
    """Reviewer verdict on a run/report (schema: quality_reviews).

    Read here (not written) -- owned by argus-quality-reviewer -- but
    modeled so the recorder can classify a verdict into learning events.
    """

    id: Optional[int] = None
    tenant_id: int
    run_id: Optional[str] = None
    review_type: Optional[str] = None
    status: QualityReviewStatus = QualityReviewStatus.PENDING
    findings: list[dict[str, Any]] = Field(default_factory=list)
    required_fixes: list[dict[str, Any]] = Field(default_factory=list)
    reviewed_at: Optional[datetime] = None


class FalseNegativeAudit(BaseModel):
    """Coverage-aware "was it really quiet?" check (schema: false_negative_audits)."""

    id: Optional[int] = None
    tenant_id: int
    run_id: Optional[str] = None
    quiet_period_days: Optional[int] = None
    coverage_score: Optional[float] = None
    audit_status: FalseNegativeAuditStatus = FalseNegativeAuditStatus.PENDING
    risk_reason: Optional[str] = None
    recommended_recheck: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
