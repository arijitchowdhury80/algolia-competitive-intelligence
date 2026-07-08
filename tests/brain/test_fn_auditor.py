"""Tests for the semantic half of argus-false-negative-auditor
(src/cios/brain/fn_auditor.py)."""

from __future__ import annotations

from cios.brain.fn_auditor import PLANTED_MARKER_FIELD, SemanticFNAuditor
from cios.learn.types import FalseNegativeAuditStatus


class FakeRawObservations:
    def __init__(self, observations: dict[tuple[int, str], list[dict]]) -> None:
        self._observations = observations

    def get_observations(self, tenant_id, run_id):
        return self._observations.get((tenant_id, run_id), [])


class FakePromotedSignals:
    def __init__(self, signals: dict[tuple[int, str], list[dict]]) -> None:
        self._signals = signals

    def get_promoted_signals(self, tenant_id, run_id):
        return self._signals.get((tenant_id, run_id), [])


class FakeLLMClient:
    def __init__(self, verdict: dict) -> None:
        self.verdict = verdict
        self.calls: list = []

    def find_missed_signal(self, tenant_id, run_id, raw_observations, promoted_signals):
        self.calls.append((tenant_id, run_id, raw_observations, promoted_signals))
        return self.verdict


CLEAN_VERDICT = {
    "material_signal_missed": False,
    "description": "",
    "missed_source_reason": "",
    "recommended_recheck": [],
}


def test_clean_run_returns_clean_status():
    raw = FakeRawObservations({(1, "run-1"): [{"text": "routine update"}]})
    promoted = FakePromotedSignals({(1, "run-1"): [{"text": "routine update"}]})
    llm = FakeLLMClient(CLEAN_VERDICT)
    auditor = SemanticFNAuditor(raw, promoted, llm)

    result = auditor.audit(1, "run-1")

    assert result.audit_status == FalseNegativeAuditStatus.CLEAN
    assert result.risk_reason is None
    assert len(llm.calls) == 1


def test_llm_missed_signal_marks_at_risk():
    raw = FakeRawObservations({(1, "run-1"): [{"text": "competitor filed a patent"}]})
    promoted = FakePromotedSignals({(1, "run-1"): []})
    llm = FakeLLMClient(
        {
            "material_signal_missed": True,
            "description": "patent filing not promoted",
            "missed_source_reason": "source not in coverage lane",
            "recommended_recheck": ["patent-office-lane"],
        }
    )
    auditor = SemanticFNAuditor(raw, promoted, llm)

    result = auditor.audit(1, "run-1")

    assert result.audit_status == FalseNegativeAuditStatus.AT_RISK
    assert result.risk_reason == "source not in coverage lane"
    assert result.recommended_recheck == ["patent-office-lane"]


def test_planted_marker_guard_overrides_llm_clean_verdict():
    """Deterministic guard: a planted fixture present in raw but absent
    from promoted must FAIL even if the LLM claims nothing was missed."""
    raw = FakeRawObservations(
        {(1, "run-1"): [{"text": "planted signal", PLANTED_MARKER_FIELD: "fixture-abc"}]}
    )
    promoted = FakePromotedSignals({(1, "run-1"): []})
    llm = FakeLLMClient(CLEAN_VERDICT)
    auditor = SemanticFNAuditor(raw, promoted, llm)

    result = auditor.audit(1, "run-1")

    assert result.audit_status == FalseNegativeAuditStatus.FAILED
    assert "fixture-abc" in result.risk_reason
    assert result.recommended_recheck == ["fixture-abc"]
    assert llm.calls == []  # guard short-circuits before the LLM is even asked


def test_planted_marker_promoted_does_not_trigger_guard():
    raw = FakeRawObservations(
        {(1, "run-1"): [{"text": "planted signal", PLANTED_MARKER_FIELD: "fixture-abc"}]}
    )
    promoted = FakePromotedSignals(
        {(1, "run-1"): [{"text": "planted signal", PLANTED_MARKER_FIELD: "fixture-abc"}]}
    )
    llm = FakeLLMClient(CLEAN_VERDICT)
    auditor = SemanticFNAuditor(raw, promoted, llm)

    result = auditor.audit(1, "run-1")

    assert result.audit_status == FalseNegativeAuditStatus.CLEAN
    assert len(llm.calls) == 1


def test_tenant_scoping_only_reads_own_tenant_data():
    raw = FakeRawObservations(
        {
            (1, "run-1"): [{"text": "tenant 1 obs"}],
            (2, "run-1"): [{"text": "tenant 2 obs", PLANTED_MARKER_FIELD: "fixture-xyz"}],
        }
    )
    promoted = FakePromotedSignals({(1, "run-1"): [], (2, "run-1"): []})
    llm = FakeLLMClient(CLEAN_VERDICT)
    auditor = SemanticFNAuditor(raw, promoted, llm)

    result = auditor.audit(1, "run-1")

    assert result.audit_status == FalseNegativeAuditStatus.CLEAN
    assert llm.calls[0][0] == 1
    assert llm.calls[0][2] == [{"text": "tenant 1 obs"}]
