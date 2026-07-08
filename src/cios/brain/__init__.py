"""Argus semantic brain (Gate 4) -- the differentiator.

Three engines over injected, tenant-scoped inputs:
  - Synthesizer: delta -> materiality -> signal, evidence-or-silence,
    coverage-before-quiet, materiality-before-urgency.
  - ClaimLedger: evidence-backed claim registry, supersedence, contradictions.
  - ThesisEngine: living, non-destructive competitor theses.

All LLM access goes through the injected BrainModel (routed to the judgment
tier -> Claude Opus by the ModelRouter). No DB or network in this package.
"""

from .claim_ledger import ClaimEvidenceError, ClaimLedger
from .synthesizer import (
    DEFAULT_MATERIALITY_FLOOR,
    MalformedSynthesisOutput,
    Synthesizer,
)
from .thesis import ThesisEngine, ThesisEvidenceError
from .verify_panel import PanelReport, SignalVerdict, VerifyPanel
from .types import (
    BrainEvent,
    BrainEventType,
    BrainModel,
    Claim,
    Contradiction,
    CoverageReport,
    LaneStatus,
    Signal,
    SynthesisInput,
    SynthesisResult,
    Thesis,
    ThesisHistoryEntry,
    Verdict,
)

__all__ = [
    "Synthesizer",
    "MalformedSynthesisOutput",
    "DEFAULT_MATERIALITY_FLOOR",
    "ClaimLedger",
    "ClaimEvidenceError",
    "ThesisEngine",
    "ThesisEvidenceError",
    "VerifyPanel",
    "PanelReport",
    "SignalVerdict",
    "BrainModel",
    "BrainEvent",
    "BrainEventType",
    "Claim",
    "Contradiction",
    "CoverageReport",
    "LaneStatus",
    "Signal",
    "SynthesisInput",
    "SynthesisResult",
    "Thesis",
    "ThesisHistoryEntry",
    "Verdict",
]
