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

from cios.learn.apply import (
    LearningApplyExecutionResult,
    LearningApplyExecutor,
    LearningApplyProposalResult,
    load_approved_policy_instructions,
)
from cios.learn.feedback import (
    FeedbackLoop,
    FeedbackProposal,
    ImprovementSynthesizer,
    LearningApplyAction,
    LearningApplyPlan,
    LearningApplyPlanner,
    NextSweepInstruction,
    NextSweepPlan,
    NextSweepPlanner,
    ProposalKind,
)
from cios.learn.fn_audit import FalseNegativeAuditor, LLMAuditor, PlantedFixture, RunHarness
from cios.learn.recorder import (
    ImprovementQueueRepository,
    LearningEventRepository,
    LearningRecorder,
)
from cios.learn.recommendation_challenge import (
    RecommendationChallengeCategory,
    RecommendationChallengeRecorder,
    RecommendationChallengeResult,
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
    "LearningApplyAction",
    "LearningApplyExecutionResult",
    "LearningApplyExecutor",
    "LearningApplyPlan",
    "LearningApplyPlanner",
    "LearningApplyProposalResult",
    "LearningEvent",
    "LearningEventRepository",
    "LearningEventStatus",
    "LearningEventType",
    "LearningRecorder",
    "NextSweepInstruction",
    "NextSweepPlan",
    "NextSweepPlanner",
    "PlantedFixture",
    "ProposalKind",
    "QualityReview",
    "QualityReviewStatus",
    "RecommendationChallengeCategory",
    "RecommendationChallengeRecorder",
    "RecommendationChallengeResult",
    "RunHarness",
    "load_approved_policy_instructions",
]
