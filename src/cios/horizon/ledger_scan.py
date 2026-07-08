"""Deterministic half: scan the tenant's own accumulated ledger into
horizon-bucketed IndustryObservation sets.

Pure functions over injected data -- no network, no DB. Actual retrieval of
semantic_deltas / semantic_facts / signal rows lives in injected repo
Protocols outside this package (same pattern as cios.brain.cadence's
DailySignalLedger); this module only buckets what it is handed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol

from cios.horizon.types import Horizon, IndustryObservation, ObservationOrigin


@dataclass
class LedgerRecord:
    """A single ledger row, already flattened to the fields the horizon
    scanner needs. Callers build this from semantic_deltas / semantic_facts
    / signal rows -- this module does not know the source table."""

    competitor_id: Optional[int]
    observed_at: date
    kind: str
    summary: str
    source_url: Optional[str]


class LedgerRepo(Protocol):
    """Injected repo: the tenant's own ledger rows in a date window. The
    caller maps this onto semantic_deltas / semantic_facts / signals tables;
    this module never queries a database directly."""

    def records_in_window(
        self, tenant_id: int, start: date, end: date
    ) -> list[LedgerRecord]: ...


def bucket_boundaries(as_of: date, horizon: Horizon) -> tuple[date, date]:
    """Inclusive [start, end] window for a horizon as of a given date.

    D10 = the 10 days ending on as_of (inclusive), D30 = 30 days, D60 = 60
    days. Boundaries are inclusive on both ends: a record dated exactly
    `horizon.days - 1` days before as_of is the oldest one still in-window.
    """
    from datetime import timedelta

    start = as_of - timedelta(days=horizon.days - 1)
    return start, as_of


def _to_observation(record: LedgerRecord) -> Optional[IndustryObservation]:
    if not record.summary or not record.summary.strip():
        return None
    if not record.source_url or not record.source_url.strip():
        return None
    return IndustryObservation(
        competitor_id=record.competitor_id,
        observed_at=record.observed_at,
        kind=record.kind,
        summary=record.summary.strip(),
        source_url=record.source_url,
        origin=ObservationOrigin.LEDGER,
    )


def scan_horizon(
    repo: LedgerRepo, tenant_id: int, horizon: Horizon, as_of: date
) -> list[IndustryObservation]:
    """Return the tenant's own ledger observations falling inside one
    horizon's window, evidence-rule filtered (no summary or no source_url
    means the record is silently dropped, not fabricated into evidence)."""
    start, end = bucket_boundaries(as_of, horizon)
    records = repo.records_in_window(tenant_id, start, end)
    observations: list[IndustryObservation] = []
    for record in records:
        if not (start <= record.observed_at <= end):
            # Defensive: a repo implementation that over-fetches should not
            # leak out-of-window rows into a horizon bucket.
            continue
        obs = _to_observation(record)
        if obs is not None:
            observations.append(obs)
    return observations


def scan_all_horizons(
    repo: LedgerRepo, tenant_id: int, as_of: date
) -> dict[Horizon, list[IndustryObservation]]:
    """Convenience: bucket the ledger into all three horizons at once. Note
    the windows nest (D60 is a superset of D30 is a superset of D10) --
    callers doing cross-horizon dedup should be aware observations repeat
    across buckets by design (the same event is "recent" from every
    horizon that still covers its date)."""
    return {horizon: scan_horizon(repo, tenant_id, horizon, as_of) for horizon in Horizon}
