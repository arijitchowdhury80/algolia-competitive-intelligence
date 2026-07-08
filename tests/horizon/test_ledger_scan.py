"""Bucketing tests: 10/30/60-day windows, boundary correctness, evidence
filtering, tenant scoping."""

from __future__ import annotations

from datetime import date, timedelta

from cios.horizon.ledger_scan import LedgerRecord, bucket_boundaries, scan_all_horizons, scan_horizon
from cios.horizon.types import Horizon, ObservationOrigin


class FakeLedgerRepo:
    def __init__(self, records: list[LedgerRecord], seen_tenants: list[int] | None = None) -> None:
        self._records = records
        self.seen_tenants = seen_tenants if seen_tenants is not None else []

    def records_in_window(self, tenant_id: int, start: date, end: date) -> list[LedgerRecord]:
        self.seen_tenants.append(tenant_id)
        return [r for r in self._records if start <= r.observed_at <= end]


def _record(days_ago: int, as_of: date, source_url: str | None = "https://example.com/a") -> LedgerRecord:
    return LedgerRecord(
        competitor_id=1,
        observed_at=as_of - timedelta(days=days_ago),
        kind="event",
        summary=f"event {days_ago} days ago",
        source_url=source_url,
    )


def test_bucket_boundaries_are_inclusive() -> None:
    as_of = date(2026, 7, 8)
    start, end = bucket_boundaries(as_of, Horizon.D10)
    assert end == as_of
    assert start == date(2026, 6, 29)  # 10-day window inclusive: 9 days back
    assert (end - start).days == 9


def test_scan_horizon_includes_boundary_and_excludes_just_outside() -> None:
    as_of = date(2026, 7, 8)
    records = [
        _record(0, as_of),  # today: inside every horizon
        _record(9, as_of),  # exactly at the D10 boundary: inside D10
        _record(10, as_of),  # one day past D10 boundary: outside D10, inside D30
        _record(29, as_of),  # D30 boundary
        _record(30, as_of),  # outside D30, inside D60
        _record(59, as_of),  # D60 boundary
        _record(60, as_of),  # outside all horizons
    ]
    repo = FakeLedgerRepo(records)

    d10 = scan_horizon(repo, tenant_id=1, horizon=Horizon.D10, as_of=as_of)
    assert len(d10) == 2  # 0 and 9 days ago

    d30 = scan_horizon(repo, tenant_id=1, horizon=Horizon.D30, as_of=as_of)
    assert len(d30) == 4  # 0, 9, 10, 29 days ago

    d60 = scan_horizon(repo, tenant_id=1, horizon=Horizon.D60, as_of=as_of)
    assert len(d60) == 6  # everything except the 60-days-ago record


def test_scan_horizon_drops_records_missing_evidence() -> None:
    as_of = date(2026, 7, 8)
    records = [
        _record(1, as_of, source_url=None),
        _record(2, as_of, source_url="   "),
        _record(3, as_of, source_url="https://example.com/ok"),
    ]
    repo = FakeLedgerRepo(records)
    observations = scan_horizon(repo, tenant_id=1, horizon=Horizon.D10, as_of=as_of)
    assert len(observations) == 1
    assert observations[0].source_url == "https://example.com/ok"
    assert observations[0].origin is ObservationOrigin.LEDGER


def test_scan_horizon_is_tenant_scoped() -> None:
    as_of = date(2026, 7, 8)
    repo = FakeLedgerRepo([_record(1, as_of)])
    scan_horizon(repo, tenant_id=42, horizon=Horizon.D10, as_of=as_of)
    assert repo.seen_tenants == [42]


def test_scan_all_horizons_returns_all_three_buckets() -> None:
    as_of = date(2026, 7, 8)
    repo = FakeLedgerRepo([_record(5, as_of)])
    result = scan_all_horizons(repo, tenant_id=1, as_of=as_of)
    assert set(result.keys()) == {Horizon.D10, Horizon.D30, Horizon.D60}
    assert all(len(obs) == 1 for obs in result.values())
