"""Collection layer: fetch -> snapshot -> delta/extract, ported from V0's
proven-in-prod ci_core.py collection logic (docs/workspace/v0-reference/).

Network access is confined to fetcher.py; every other module here is pure
orchestration or pure text processing, testable without a live network.
"""

from cios.collect.fetcher import ContentFetcher, HttpContentFetcher, ProbeFetcherAdapter
from cios.collect.runner import CollectionRunner, run_discovery_sweep
from cios.collect.types import (
    ContentFetchResult,
    Delta,
    ExtractedFact,
    FetchRunResult,
    FetchStatus,
    Snapshot,
    SourceContext,
)

__all__ = [
    "ContentFetcher",
    "HttpContentFetcher",
    "ProbeFetcherAdapter",
    "CollectionRunner",
    "run_discovery_sweep",
    "ContentFetchResult",
    "Delta",
    "ExtractedFact",
    "FetchRunResult",
    "FetchStatus",
    "Snapshot",
    "SourceContext",
]
