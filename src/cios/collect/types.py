"""Shared data types for the collection layer.

Mirrors src/cios/db/schema.sql EVIDENCE COLLECTION + SEMANTIC LAYER tables:
intel_fetch_runs, source_snapshots, raw_findings, semantic_facts,
semantic_deltas. These are intermediate value objects produced by
fetcher/snapshot/extract; the runner and its injected repositories map them
onto the tenant-scoped DB rows (attaching real ids and evidence_ids).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FetchStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class ContentFetchResult(BaseModel):
    """Full-page fetch outcome (V0 fetch_url() shape).

    Distinct from cios.hunter.validator.FetchResult, which is a lightweight
    reachability probe used by discovery/validation -- this carries the full
    extracted page text used for snapshotting and extraction.
    """

    status: FetchStatus
    http_status: Optional[int] = None
    text: str = ""
    error: Optional[str] = None
    collector: str = "direct_http"
    duration_ms: Optional[int] = None


class SourceContext(BaseModel):
    """Lightweight source description passed into extraction. The extractor
    only needs identity + classification hints, not the full ledger row."""

    competitor_id: int
    competitor_name: str
    url: str
    source_type: Optional[str] = None
    priority: int = 3


class Snapshot(BaseModel):
    """Captured content per source per fetch run (schema: source_snapshots)."""

    id: Optional[int] = None
    tenant_id: int
    source_id: int
    fetch_run_id: Optional[int] = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: Optional[str] = None
    title: Optional[str] = None
    text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedFact(BaseModel):
    """A semantic fact extracted from a snapshot, pre-persistence (schema:
    semantic_facts once an evidence_ids reference is attached)."""

    id: Optional[int] = None
    competitor_id: int
    fact_type: str
    statement: str
    fact_json: dict[str, Any] = Field(default_factory=dict)
    evidence_text: Optional[str] = None
    evidence_url: str
    confidence: float = 0.6


class Delta(BaseModel):
    """A scored change between two snapshots' extracted facts, pre-
    persistence (schema: semantic_deltas)."""

    id: Optional[int] = None
    competitor_id: int
    delta_type: str
    materiality_score: float = 0.0
    what_changed: str
    why_it_matters: Optional[str] = None
    implication: Optional[str] = None
    recommended_action: Optional[str] = None
    evidence_urls: list[str] = Field(default_factory=list)
    quality_status: str = "draft"
    confidence: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FetchRunResult(BaseModel):
    """Outcome of one collection sweep (schema: intel_fetch_runs)."""

    id: Optional[int] = None
    tenant_id: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    status: str = "running"
    source_count: int = 0
    snapshot_count: int = 0
    finding_count: int = 0
    errors: list[str] = Field(default_factory=list)
