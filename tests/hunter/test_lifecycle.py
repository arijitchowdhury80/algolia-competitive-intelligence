"""Tests for source lifecycle: upsert-not-duplicate, retire-after-3-missing-
days boundary, reactivation, health event emission.
"""

from __future__ import annotations

from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import HealthEventType, Source, SourceStatus, ValidationResult


class FakeSourceRepository:
    def __init__(self):
        self._next_id = 1
        self._by_id: dict[int, Source] = {}

    def get_by_normalized_url(self, tenant_id, normalized_url):
        for source in self._by_id.values():
            if source.tenant_id == tenant_id and source.normalized_url == normalized_url:
                return source
        return None

    def upsert(self, source: Source) -> Source:
        if source.id is None:
            saved = source.model_copy(update={"id": self._next_id})
            self._next_id += 1
        else:
            saved = source
        self._by_id[saved.id] = saved
        return saved


def _validated(url="https://example.com/blog", family="blog") -> ValidationResult:
    return ValidationResult(accepted=True, reason="validated", url=url, normalized_url=url, source_family=family)


def test_upsert_validated_creates_new_active_source():
    repo = FakeSourceRepository()
    events = []
    lifecycle = SourceLifecycle(repo, events.append)

    source = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())

    assert source.id is not None
    assert source.status == SourceStatus.ACTIVE
    assert repo.get_by_normalized_url(1, source.normalized_url) is not None


def test_upsert_validated_does_not_create_duplicate_for_same_normalized_url():
    repo = FakeSourceRepository()
    lifecycle = SourceLifecycle(repo, lambda e: None)

    first = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())
    second = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())

    assert first.id == second.id
    assert len(repo._by_id) == 1


def test_record_scan_outcome_two_misses_keeps_source_active_status_missing_not_retired():
    repo = FakeSourceRepository()
    lifecycle = SourceLifecycle(repo, lambda e: None)
    source = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())

    source = lifecycle.record_scan_outcome(source, seen=False)
    assert source.status == SourceStatus.MISSING
    assert source.missing_streak_days == 1

    source = lifecycle.record_scan_outcome(source, seen=False)
    assert source.status == SourceStatus.MISSING
    assert source.missing_streak_days == 2
    assert source.retired_at is None


def test_record_scan_outcome_three_misses_retires_source():
    repo = FakeSourceRepository()
    events = []
    lifecycle = SourceLifecycle(repo, events.append)
    source = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())

    for _ in range(2):
        source = lifecycle.record_scan_outcome(source, seen=False)
    source = lifecycle.record_scan_outcome(source, seen=False)

    assert source.status == SourceStatus.RETIRED
    assert source.missing_streak_days == 3
    assert source.retired_at is not None
    assert events[-1].event_type == HealthEventType.RETIRED


def test_record_scan_outcome_reactivates_missing_source_on_reappearance():
    repo = FakeSourceRepository()
    events = []
    lifecycle = SourceLifecycle(repo, events.append)
    source = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())
    source = lifecycle.record_scan_outcome(source, seen=False)

    source = lifecycle.record_scan_outcome(source, seen=True)

    assert source.status == SourceStatus.ACTIVE
    assert source.missing_streak_days == 0
    assert events[-1].event_type == HealthEventType.RECOVERED


def test_record_scan_outcome_reactivates_retired_source_on_reappearance():
    repo = FakeSourceRepository()
    events = []
    lifecycle = SourceLifecycle(repo, events.append)
    source = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())
    for _ in range(3):
        source = lifecycle.record_scan_outcome(source, seen=False)
    assert source.status == SourceStatus.RETIRED

    source = lifecycle.record_scan_outcome(source, seen=True)

    assert source.status == SourceStatus.ACTIVE
    assert source.missing_streak_days == 0
    assert source.retired_at is None
    assert events[-1].event_type == HealthEventType.RECOVERED


def test_upsert_validated_on_previously_retired_source_reactivates_and_emits_recovered():
    repo = FakeSourceRepository()
    events = []
    lifecycle = SourceLifecycle(repo, events.append)
    source = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())
    for _ in range(3):
        source = lifecycle.record_scan_outcome(source, seen=False)
    assert source.status == SourceStatus.RETIRED

    reactivated = lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=_validated())

    assert reactivated.id == source.id
    assert reactivated.status == SourceStatus.ACTIVE
    assert events[-1].event_type == HealthEventType.RECOVERED


def test_upsert_validated_rejects_unaccepted_result():
    repo = FakeSourceRepository()
    lifecycle = SourceLifecycle(repo, lambda e: None)
    bad = ValidationResult(accepted=False, reason="unreachable", url="x", normalized_url="x")

    try:
        lifecycle.upsert_validated(tenant_id=1, competitor_id=1, result=bad)
        assert False, "expected ValueError"
    except ValueError:
        pass
