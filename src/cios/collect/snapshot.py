"""Snapshot construction and change detection.

Ports V0's save_snapshot()/latest_snapshot() semantics: a snapshot always
carries a sha256 content_hash (cios.collect.extract.content_hash -- same
algorithm, so hashes stay comparable against V0 history), and "did this
source change" is a hash comparison against the tenant's most recent
snapshot for that source, not a byte-for-byte text diff.
"""

from __future__ import annotations

from typing import Optional

from cios.collect.extract import content_hash
from cios.collect.types import ContentFetchResult, Snapshot


def build_snapshot(
    tenant_id: int,
    source_id: int,
    fetch_run_id: Optional[int],
    fetch_result: ContentFetchResult,
    title: Optional[str] = None,
) -> Snapshot:
    """Build the Snapshot row for one fetch outcome. A failed fetch still
    produces a snapshot (status/error recorded in metadata) -- a miss is a
    failure event, not a quiet day, per manifesto doctrine."""
    text = fetch_result.text or ""
    return Snapshot(
        tenant_id=tenant_id,
        source_id=source_id,
        fetch_run_id=fetch_run_id,
        content_hash=content_hash(text) if text else None,
        title=title,
        text=text,
        metadata={
            "status": fetch_result.status.value,
            "http_status": fetch_result.http_status,
            "error": fetch_result.error,
            "collector": fetch_result.collector,
            "duration_ms": fetch_result.duration_ms,
        },
    )


def has_changed(prior: Optional[Snapshot], current: Snapshot) -> bool:
    """True if `current` differs from the tenant's prior snapshot for this
    source by content hash. A prior snapshot with no hash (fetch failed, or
    this is the first-ever snapshot) counts as changed so extraction always
    runs against genuinely new content."""
    if prior is None or not prior.content_hash:
        return True
    return prior.content_hash != current.content_hash


def collector_changed(prior: Optional[Snapshot], current: Snapshot) -> bool:
    """True if the collector method differs between snapshots (V0's
    `collector_changed` signal into materiality_for_delta -- a delta driven
    by a collector swap is penalized, not treated as a genuine content
    change)."""
    if prior is None:
        return False
    prior_collector = (prior.metadata or {}).get("collector")
    current_collector = (current.metadata or {}).get("collector")
    return bool(prior_collector) and prior_collector != current_collector
