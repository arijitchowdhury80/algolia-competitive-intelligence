"""CI-OS argus-source-hunter: discover, validate, upsert, and retire sources.

Gate 2 skill (docs/planning/CI-OS-Fable-build-goal-spec.md). Covers:
discovery.py (candidate generation, no network), validator.py (candidate
validation + dedup against the source ledger, network abstracted behind
an injected fetcher Protocol), and lifecycle.py (upsert-not-duplicate,
missing-streak tracking, retire-after-3-missing-days, reactivation,
source_health_events emission).
"""

from cios.hunter.discovery import DiscoveryProvider, SourceDiscoverer
from cios.hunter.lifecycle import SourceLifecycle, SourceRepository, HealthEventSink
from cios.hunter.types import (
    Competitor,
    HealthEventType,
    ScanRunStatus,
    Source,
    SourceCandidate,
    SourceCandidateStatus,
    SourceHealthEvent,
    SourceScanRun,
    SourceStatus,
    ValidationResult,
)
from cios.hunter.validator import Fetcher, FetchResult, SourceValidator

__all__ = [
    "Competitor",
    "DiscoveryProvider",
    "Fetcher",
    "FetchResult",
    "HealthEventSink",
    "HealthEventType",
    "ScanRunStatus",
    "Source",
    "SourceCandidate",
    "SourceCandidateStatus",
    "SourceDiscoverer",
    "SourceHealthEvent",
    "SourceLifecycle",
    "SourceRepository",
    "SourceScanRun",
    "SourceStatus",
    "SourceValidator",
    "ValidationResult",
]
