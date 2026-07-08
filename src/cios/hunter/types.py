"""Shared data types for the argus-source-hunter skill.

Mirrors src/cios/db/schema.sql: competitors, sources, source_scan_runs,
source_candidates, source_health_events. `source_observations` and
`competitor_scan_rollups` are out of scope for this module (owned by the
intel collector / rollup job); the hunter only writes the tables listed
above per docs/planning/Argus-skill-build-matrix.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# Per spec (CI-OS-Fable-build-goal-spec.md Gate 2 acceptance): a source is
# retired once its missing streak reaches this many consecutive scan days.
RETIREMENT_MISSING_STREAK_DAYS = 3


class SourceStatus(str, Enum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    BLOCKED = "blocked"
    MISSING = "missing"
    RETIRED = "retired"
    NEEDS_CREDENTIALS = "needs_credentials"
    NOT_APPLICABLE = "not_applicable"


class SourceCandidateStatus(str, Enum):
    PENDING = "pending"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class ScanRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HealthEventType(str, Enum):
    OK = "ok"
    FETCH_ERROR = "fetch_error"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    EMPTY = "empty"
    RECOVERED = "recovered"
    RETIRED = "retired"


class Competitor(BaseModel):
    """Per-tenant competitor registry entry (schema: competitors)."""

    id: int
    tenant_id: int
    name: str
    domain: Optional[str] = None
    category: Optional[str] = None
    priority: int = 3
    status: str = "active"
    known_products: list[str] = Field(default_factory=list)
    known_executives: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """Monitored source ledger row (schema: sources).

    `normalized_url` is the natural key for upsert-not-duplicate
    (UNIQUE (tenant_id, normalized_url) in schema.sql).
    """

    id: Optional[int] = None
    tenant_id: int
    competitor_id: int
    source_family: str
    url: str
    normalized_url: str
    title: Optional[str] = None
    status: SourceStatus = SourceStatus.CANDIDATE
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    missing_streak_days: int = 0
    retired_at: Optional[datetime] = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class SourceCandidate(BaseModel):
    """Discovered-but-unpromoted source URL (schema: source_candidates)."""

    id: Optional[int] = None
    tenant_id: int
    competitor_id: int
    url: str
    source_family: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    status: SourceCandidateStatus = SourceCandidateStatus.PENDING
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    promoted_at: Optional[datetime] = None


class SourceScanRun(BaseModel):
    """One row per source-hunter sweep (schema: source_scan_runs)."""

    id: Optional[int] = None
    tenant_id: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    status: ScanRunStatus = ScanRunStatus.RUNNING
    competitors_scanned: int = 0
    sources_found: int = 0
    sources_added: int = 0
    sources_retired: int = 0
    errors: list[str] = Field(default_factory=list)


class SourceHealthEvent(BaseModel):
    """Fetch failure / recovery / retirement event (schema: source_health_events).

    A miss is a failure event, not a quiet day (manifesto doctrine).
    """

    id: Optional[int] = None
    tenant_id: int
    source_id: int
    fetch_run_id: Optional[int] = None
    event_type: HealthEventType
    http_status: Optional[int] = None
    detail: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Outcome of validating a single candidate URL."""

    accepted: bool
    reason: str
    url: str
    normalized_url: str
    source_family: Optional[str] = None
    http_status: Optional[int] = None
