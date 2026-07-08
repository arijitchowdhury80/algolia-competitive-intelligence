"""CI-OS argus-learning-loop: capture, classify, and propose fixes from
every run's outcomes.

Gate 5 skill, learning half (docs/planning/CI-OS-Fable-build-goal-spec.md;
dashboard half is separate). Covers: recorder.py (run outcomes ->
learning_events + improvement_queue classification), feedback.py
(improvement_queue -> evidence-linked config-adjustment proposals, never
auto-applied), and fn_audit.py (deterministic planted-miss test harness ->
false_negative_audits). LLM-driven improvement synthesis and the semantic
false-negative auditor are Gate 4 brain territory -- both leave a marked
Protocol extension point (`ImprovementSynthesizer`, `LLMAuditor`).
"""

from cios.learn.feedback import (
    FeedbackLoop,
    FeedbackProposal,
    ImprovementSynthesizer,
    ProposalKind,
)
from cios.learn.fn_audit import FalseNegativeAuditor, LLMAuditor, PlantedFixture, RunHarness
from cios.learn.recorder import (
    ImprovementQueueRepository,
    LearningEventRepository,
    LearningRecorder,
)
from cios.learn.types import (
    FalseNegativeAudit,
    FalseNegativeAuditStatus,
    ImprovementItem,
    ImprovementPriority,
    ImprovementStatus,
    LearningEvent,
    LearningEventStatus,
    LearningEventType,
    QualityReview,
    QualityReviewStatus,
)

__all__ = [
    "FalseNegativeAudit",
    "FalseNegativeAuditStatus",
    "FalseNegativeAuditor",
    "FeedbackLoop",
    "FeedbackProposal",
    "ImprovementItem",
    "ImprovementPriority",
    "ImprovementQueueRepository",
    "ImprovementStatus",
    "ImprovementSynthesizer",
    "LLMAuditor",
    "LearningEvent",
    "LearningEventRepository",
    "LearningEventStatus",
    "LearningEventType",
    "LearningRecorder",
    "PlantedFixture",
    "ProposalKind",
    "QualityReview",
    "QualityReviewStatus",
    "RunHarness",
]
