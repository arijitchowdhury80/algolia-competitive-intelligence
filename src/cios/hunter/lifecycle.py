"""Source lifecycle: upsert-not-duplicate, missing-streak tracking, retire-
after-3-missing-days, reactivation.

Storage access is via injected repository protocols only -- no direct DB
access here (tests use in-memory fakes). Every state transition that
matters for coverage (retire, recover) emits a `SourceHealthEvent` via an
injected sink so a miss is always a recorded failure event, never a silent
gap (manifesto doctrine: "a miss is a failure event, not a quiet day").
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from cios.hunter.types import (
    RETIREMENT_MISSING_STREAK_DAYS,
    HealthEventType,
    Source,
    SourceHealthEvent,
    SourceStatus,
    ValidationResult,
)


class SourceRepository(Protocol):
    def get_by_normalized_url(self, tenant_id: int, normalized_url: str) -> Optional[Source]: ...

    def upsert(self, source: Source) -> Source: ...


# Callable sink rather than a class protocol: callers may pass a plain
# function, a bound method, or list.append in tests (mirrors acl.py's
# AuditSink pattern).
HealthEventSink = Callable[[SourceHealthEvent], None]


class SourceLifecycle:
    """Applies validated candidates and scan outcomes to the source ledger."""

    def __init__(self, sources: SourceRepository, health_events: HealthEventSink) -> None:
        self._sources = sources
        self._health_events = health_events

    def upsert_validated(
        self, tenant_id: int, competitor_id: int, result: ValidationResult
    ) -> Source:
        """Insert-or-update a source by its canonical (tenant, normalized_url)
        key -- the schema's UNIQUE (tenant_id, normalized_url) natural key.
        Never creates a duplicate row for a URL already on the ledger."""
        if not result.accepted:
            raise ValueError(f"cannot upsert an unaccepted validation result: {result.reason}")

        now = datetime.now(timezone.utc)
        existing = self._sources.get_by_normalized_url(tenant_id, result.normalized_url)

        if existing is None:
            source = Source(
                tenant_id=tenant_id,
                competitor_id=competitor_id,
                source_family=result.source_family or "unclassified",
                url=result.url,
                normalized_url=result.normalized_url,
                status=SourceStatus.ACTIVE,
                first_seen_at=now,
                last_seen_at=now,
                last_checked_at=now,
                missing_streak_days=0,
            )
            return self._sources.upsert(source)

        was_missing_or_retired = existing.status in (SourceStatus.MISSING, SourceStatus.RETIRED)
        updated = existing.model_copy(
            update={
                "url": result.url,
                "source_family": result.source_family or existing.source_family,
                "status": SourceStatus.ACTIVE,
                "last_seen_at": now,
                "last_checked_at": now,
                "missing_streak_days": 0,
                "retired_at": None,
            }
        )
        saved = self._sources.upsert(updated)

        if was_missing_or_retired:
            self._emit(saved, HealthEventType.RECOVERED, detail="source reappeared on scan")

        return saved

    def record_scan_outcome(self, source: Source, seen: bool) -> Source:
        """Update a source's missing-streak state for one scan-run outcome.

        seen=True resets the streak (and reactivates if previously
        missing/retired, emitting a `recovered` event). seen=False
        increments the streak and retires the source once the streak
        reaches RETIREMENT_MISSING_STREAK_DAYS (3): 2 consecutive misses
        keeps it, 3 retires it (gate acceptance boundary).
        """
        now = datetime.now(timezone.utc)

        if seen:
            was_missing_or_retired = source.status in (SourceStatus.MISSING, SourceStatus.RETIRED)
            updated = source.model_copy(
                update={
                    "status": SourceStatus.ACTIVE,
                    "last_seen_at": now,
                    "last_checked_at": now,
                    "missing_streak_days": 0,
                    "retired_at": None,
                }
            )
            saved = self._sources.upsert(updated)
            if was_missing_or_retired:
                self._emit(saved, HealthEventType.RECOVERED, detail="source reappeared on scan")
            else:
                self._emit(saved, HealthEventType.OK)
            return saved

        new_streak = source.missing_streak_days + 1
        if new_streak >= RETIREMENT_MISSING_STREAK_DAYS:
            updated = source.model_copy(
                update={
                    "status": SourceStatus.RETIRED,
                    "last_checked_at": now,
                    "missing_streak_days": new_streak,
                    "retired_at": now,
                }
            )
            saved = self._sources.upsert(updated)
            self._emit(
                saved,
                HealthEventType.RETIRED,
                detail=f"retired after {new_streak} consecutive missing days",
            )
            return saved

        updated = source.model_copy(
            update={
                "status": SourceStatus.MISSING,
                "last_checked_at": now,
                "missing_streak_days": new_streak,
            }
        )
        saved = self._sources.upsert(updated)
        self._emit(saved, HealthEventType.EMPTY, detail=f"missing streak day {new_streak}")
        return saved

    def _emit(self, source: Source, event_type: HealthEventType, detail: Optional[str] = None) -> None:
        self._health_events(
            SourceHealthEvent(
                tenant_id=source.tenant_id,
                source_id=source.id,
                event_type=event_type,
                detail=detail,
            )
        )
