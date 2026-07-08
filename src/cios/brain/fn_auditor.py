"""argus-false-negative-auditor (semantic half): "would Argus have found
this" over real market events, not just planted fixtures.

src/cios/learn/fn_audit.py already owns the deterministic planted-miss
harness (FalseNegativeAuditor/RunHarness) and marks `LLMAuditor` as the Gate
4 brain extension point. This module implements that Protocol: given a
day's raw observations and the signals actually promoted, it asks an LLM
"what material signal is present in the raw data but missing from the
promoted set" (manifesto's argus-false-negative-auditor) and folds the
answer into a `FalseNegativeAudit` row.

The deterministic planted-fixture guard stays load-bearing here too --
per manifesto doctrine ("a miss is a failure event, not a quiet day") a
planted marker present in raw data but absent from promoted signals is a
FAIL regardless of what the LLM concludes about it. LLM judgment augments
the deterministic harness; it never overrides a caught planted miss.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from cios.learn.types import FalseNegativeAudit, FalseNegativeAuditStatus

# Fixtures injected by the deterministic harness (src/cios/learn/fn_audit.py
# PlantedFixture) carry this field on the raw observation so the semantic
# auditor can recognize them without needing to know fixture internals.
PLANTED_MARKER_FIELD = "fixture_marker"


class RawObservationsProvider(Protocol):
    """Fetches the day's raw (pre-promotion) observations for a run --
    everything the collector saw, before synthesis filtered it down."""

    def get_observations(self, tenant_id: int, run_id: str) -> list[dict[str, Any]]: ...


class PromotedSignalsProvider(Protocol):
    """Fetches the signals the pipeline actually promoted for a run."""

    def get_promoted_signals(self, tenant_id: int, run_id: str) -> list[dict[str, Any]]: ...


class FNSemanticLLMClient(Protocol):
    """Extension point for the LLM call itself -- routed via
    src/cios/platform/models/router.py's quality tier in production (see
    quality.py's QualityLLMReviewer docstring for the async/sync adapter
    note; the same rationale applies here). Tests inject a fake."""

    def find_missed_signal(
        self,
        tenant_id: int,
        run_id: str,
        raw_observations: list[dict[str, Any]],
        promoted_signals: list[dict[str, Any]],
    ) -> dict:
        """Must return a structured verdict:
        {
            "material_signal_missed": bool,
            "description": str,
            "missed_source_reason": str,
            "recommended_recheck": list[str],
        }
        """
        ...


def _find_planted_marker_miss(
    raw_observations: list[dict[str, Any]], promoted_signals: list[dict[str, Any]]
) -> Optional[str]:
    """Returns the marker id of a planted fixture present in raw data but
    absent from promoted signals, or None if no such miss exists."""
    promoted_markers = {
        signal.get(PLANTED_MARKER_FIELD)
        for signal in promoted_signals
        if signal.get(PLANTED_MARKER_FIELD)
    }
    for obs in raw_observations:
        marker = obs.get(PLANTED_MARKER_FIELD)
        if marker and marker not in promoted_markers:
            return marker
    return None


class SemanticFNAuditor:
    """Implements learn.fn_audit.LLMAuditor: semantic false-negative
    judgment over a run's real observations, with a deterministic planted-
    marker guard that overrides the LLM's opinion."""

    def __init__(
        self,
        raw_observations: RawObservationsProvider,
        promoted_signals: PromotedSignalsProvider,
        llm_client: FNSemanticLLMClient,
    ) -> None:
        self._raw_observations = raw_observations
        self._promoted_signals = promoted_signals
        self._llm_client = llm_client

    def audit(self, tenant_id: int, run_id: str) -> Optional[FalseNegativeAudit]:
        raw_observations = self._raw_observations.get_observations(tenant_id, run_id)
        promoted_signals = self._promoted_signals.get_promoted_signals(tenant_id, run_id)

        planted_miss = _find_planted_marker_miss(raw_observations, promoted_signals)
        if planted_miss is not None:
            return FalseNegativeAudit(
                tenant_id=tenant_id,
                run_id=run_id,
                audit_status=FalseNegativeAuditStatus.FAILED,
                risk_reason=(
                    f"planted signal '{planted_miss}' present in raw observations "
                    "but not promoted"
                ),
                recommended_recheck=[planted_miss],
            )

        verdict = self._llm_client.find_missed_signal(
            tenant_id, run_id, raw_observations, promoted_signals
        )

        if verdict.get("material_signal_missed"):
            reason = verdict.get("missed_source_reason") or verdict.get("description") or ""
            recheck = list(verdict.get("recommended_recheck") or [])
            return FalseNegativeAudit(
                tenant_id=tenant_id,
                run_id=run_id,
                audit_status=FalseNegativeAuditStatus.AT_RISK,
                risk_reason=reason or verdict.get("description"),
                recommended_recheck=recheck,
            )

        return FalseNegativeAudit(
            tenant_id=tenant_id,
            run_id=run_id,
            audit_status=FalseNegativeAuditStatus.CLEAN,
            risk_reason=None,
            recommended_recheck=[],
        )

