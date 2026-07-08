"""Tests for the false-negative planted-miss audit harness: both directions
(caught -> pass row, missed -> fail row), and tenant scoping."""

from __future__ import annotations

from cios.learn.fn_audit import FalseNegativeAuditor, PlantedFixture
from cios.learn.types import FalseNegativeAuditStatus


class ScriptedHarness:
    def __init__(self, promoted: bool):
        self._promoted = promoted
        self.calls: list[PlantedFixture] = []

    def run(self, fixture: PlantedFixture) -> bool:
        self.calls.append(fixture)
        return self._promoted


def _fixture(signal_id="planted-1") -> PlantedFixture:
    return PlantedFixture(
        signal_id=signal_id,
        description="competitor announces a pricing change",
        payload={"claim": "Constructor cuts enterprise pricing 20%"},
    )


def test_planted_signal_promoted_records_clean_audit():
    harness = ScriptedHarness(promoted=True)
    auditor = FalseNegativeAuditor(harness)

    audit = auditor.run_planted_miss_test(tenant_id=1, run_id="run-1", fixture=_fixture())

    assert audit.audit_status == FalseNegativeAuditStatus.CLEAN
    assert audit.risk_reason is None
    assert audit.recommended_recheck == []
    assert len(harness.calls) == 1


def test_planted_signal_missed_records_failed_audit_with_reason():
    harness = ScriptedHarness(promoted=False)
    auditor = FalseNegativeAuditor(harness)

    audit = auditor.run_planted_miss_test(tenant_id=1, run_id="run-2", fixture=_fixture("planted-2"))

    assert audit.audit_status == FalseNegativeAuditStatus.FAILED
    assert audit.risk_reason is not None
    assert "planted-2" in audit.risk_reason
    assert audit.recommended_recheck == ["planted-2"]


def test_run_batch_produces_one_row_per_fixture():
    harness = ScriptedHarness(promoted=True)
    auditor = FalseNegativeAuditor(harness)
    fixtures = [_fixture("a"), _fixture("b"), _fixture("c")]

    audits = auditor.run_batch(tenant_id=1, run_id="run-3", fixtures=fixtures)

    assert len(audits) == 3
    assert all(a.audit_status == FalseNegativeAuditStatus.CLEAN for a in audits)
    assert len(harness.calls) == 3


def test_batch_with_one_miss_is_not_all_clean():
    class AlternatingHarness:
        def __init__(self):
            self._calls = 0

        def run(self, fixture):
            self._calls += 1
            return self._calls != 2  # second fixture is missed

    auditor = FalseNegativeAuditor(AlternatingHarness())
    fixtures = [_fixture("a"), _fixture("b"), _fixture("c")]

    audits = auditor.run_batch(tenant_id=1, run_id="run-4", fixtures=fixtures)

    statuses = [a.audit_status for a in audits]
    assert statuses == [
        FalseNegativeAuditStatus.CLEAN,
        FalseNegativeAuditStatus.FAILED,
        FalseNegativeAuditStatus.CLEAN,
    ]


def test_audits_are_tenant_scoped():
    harness = ScriptedHarness(promoted=True)
    auditor = FalseNegativeAuditor(harness)

    audit_1 = auditor.run_planted_miss_test(tenant_id=1, run_id="run-5", fixture=_fixture())
    audit_2 = auditor.run_planted_miss_test(tenant_id=2, run_id="run-5", fixture=_fixture())

    assert audit_1.tenant_id == 1
    assert audit_2.tenant_id == 2
