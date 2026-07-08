"""False-negative audit scaffolding: planted-miss test harness.

Deterministic harness only -- this module injects a known-signal fixture
into a run and checks whether the pipeline promoted it, recording a
`false_negative_audits` row either way (manifesto doctrine: "a miss is a
failure event, not a quiet day" applies to the auditor itself -- an
undetected planted miss must never be silent). The LLM auditor described in
the manifesto (`argus-false-negative-auditor`'s semantic judgment over real
market events) is Gate 4 brain territory; `LLMAuditor` is the marked
extension point where it plugs in.
"""

from __future__ import annotations

from typing import Optional, Protocol

from cios.learn.types import FalseNegativeAudit, FalseNegativeAuditStatus


class PlantedFixture:
    """A known signal deliberately injected into a run so the pipeline's
    ability to find it can be verified. `signal_id` is the fixture's own
    identifier, not a DB row -- it never actually happened, so it cannot be
    confused with real signals in the tenant's data."""

    def __init__(self, signal_id: str, description: str, payload: dict) -> None:
        self.signal_id = signal_id
        self.description = description
        self.payload = payload


class RunHarness(Protocol):
    """Abstraction over "run the pipeline (or a stage of it) against this
    fixture and report whether the known signal was promoted." A real
    implementation drives the collector/synthesizer end to end; tests use
    an in-memory fake that returns a scripted verdict."""

    def run(self, fixture: PlantedFixture) -> bool: ...


class LLMAuditor(Protocol):
    """Extension point for the manifesto's semantic false-negative auditor
    (Gate 4 brain territory) -- judges "would Argus have found this" against
    real recent market events, not just planted fixtures. Not implemented
    here; the deterministic harness below does not depend on it."""

    def audit(self, tenant_id: int, run_id: str) -> Optional[FalseNegativeAudit]: ...


class FalseNegativeAuditor:
    """Runs planted-miss tests and records the result. Every call produces
    exactly one `FalseNegativeAudit` row -- caught or missed, never silent."""

    def __init__(self, harness: RunHarness) -> None:
        self._harness = harness

    def run_planted_miss_test(
        self,
        tenant_id: int,
        run_id: str,
        fixture: PlantedFixture,
        coverage_score: Optional[float] = None,
    ) -> FalseNegativeAudit:
        promoted = self._harness.run(fixture)

        if promoted:
            return FalseNegativeAudit(
                tenant_id=tenant_id,
                run_id=run_id,
                coverage_score=coverage_score,
                audit_status=FalseNegativeAuditStatus.CLEAN,
                risk_reason=None,
                recommended_recheck=[],
            )

        return FalseNegativeAudit(
            tenant_id=tenant_id,
            run_id=run_id,
            coverage_score=coverage_score,
            audit_status=FalseNegativeAuditStatus.FAILED,
            risk_reason=f"planted signal '{fixture.signal_id}' was not promoted: {fixture.description}",
            recommended_recheck=[fixture.signal_id],
        )

    def run_batch(
        self,
        tenant_id: int,
        run_id: str,
        fixtures: list[PlantedFixture],
        coverage_score: Optional[float] = None,
    ) -> list[FalseNegativeAudit]:
        """Run several planted fixtures against one run. Any single miss
        means the batch is not clean -- callers should treat a `failed` row
        in the result as blocking a green "quiet" verdict for that run."""
        return [
            self.run_planted_miss_test(tenant_id, run_id, fixture, coverage_score)
            for fixture in fixtures
        ]
