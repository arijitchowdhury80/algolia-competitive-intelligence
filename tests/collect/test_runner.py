"""Tests for CollectionRunner and run_discovery_sweep. All storage/network is
in-memory fakes -- no network, no mocking framework.
"""

from __future__ import annotations

from cios.collect.runner import CollectionRunner, run_discovery_sweep
from cios.collect.types import ContentFetchResult, Delta, ExtractedFact, FetchRunResult, FetchStatus, Snapshot, SourceContext
from cios.hunter.discovery import DiscoveredUrl, SourceDiscoverer
from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import Competitor, HealthEventType, Source, SourceHealthEvent, SourceStatus
from cios.hunter.validator import FetchResult, SourceValidator


class FakeContentFetcher:
    def __init__(self, results: dict[str, ContentFetchResult]):
        self._results = results

    def fetch_content(self, url: str) -> ContentFetchResult:
        return self._results.get(url, ContentFetchResult(status=FetchStatus.ERROR, error="not_stubbed"))


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self._latest: dict[tuple[int, int], Snapshot] = {}
        self.saved: list[Snapshot] = []

    def latest(self, tenant_id: int, source_id: int):
        return self._latest.get((tenant_id, source_id))

    def save(self, snapshot: Snapshot) -> Snapshot:
        snapshot = snapshot.model_copy(update={"id": len(self.saved) + 1})
        self.saved.append(snapshot)
        self._latest[(snapshot.tenant_id, snapshot.source_id)] = snapshot
        return snapshot


class FakeFactRepository:
    def __init__(self) -> None:
        self.saved: list[ExtractedFact] = []

    def save(self, fact: ExtractedFact) -> ExtractedFact:
        self.saved.append(fact)
        return fact


class FakeDeltaRepository:
    def __init__(self) -> None:
        self.saved: list[Delta] = []

    def save(self, delta: Delta) -> Delta:
        self.saved.append(delta)
        return delta


class FakeFetchRunRepository:
    def __init__(self) -> None:
        self.runs: list[FetchRunResult] = []

    def start(self, tenant_id: int) -> FetchRunResult:
        run = FetchRunResult(id=len(self.runs) + 1, tenant_id=tenant_id)
        self.runs.append(run)
        return run

    def finish(self, run: FetchRunResult) -> FetchRunResult:
        return run


def make_source(source_id: int, url: str) -> Source:
    return Source(
        id=source_id,
        tenant_id=1,
        competitor_id=1,
        source_family="blog",
        url=url,
        normalized_url=url,
        status=SourceStatus.ACTIVE,
    )


def make_context(competitor_id: int = 1, url: str = "https://coveo.com/customer-stories") -> SourceContext:
    return SourceContext(competitor_id=competitor_id, competitor_name="Coveo", url=url, source_type="case_study", priority=2)


def test_collection_runner_produces_snapshot_and_marks_run_completed():
    source = make_source(1, "https://coveo.com/customer-stories")
    context = make_context(url=source.url)
    fetcher = FakeContentFetcher({
        source.url: ContentFetchResult(status=FetchStatus.OK, http_status=200, text="Acme Corp uses Coveo."),
    })
    snapshots, facts, deltas, fetch_runs = FakeSnapshotRepository(), FakeFactRepository(), FakeDeltaRepository(), FakeFetchRunRepository()
    runner = CollectionRunner(fetcher, snapshots, facts, deltas, fetch_runs)

    result = runner.run(tenant_id=1, sources=[(source, context)])

    assert result.status == "completed"
    assert result.source_count == 1
    assert result.snapshot_count == 1
    assert len(snapshots.saved) == 1
    assert snapshots.saved[0].content_hash is not None


def test_collection_runner_extracts_facts_and_deltas_on_second_run_with_new_content():
    source = make_source(1, "https://coveo.com/customer-stories")
    context = make_context(url=source.url)
    snapshots, facts, deltas, fetch_runs = FakeSnapshotRepository(), FakeFactRepository(), FakeDeltaRepository(), FakeFetchRunRepository()

    fetcher_run1 = FakeContentFetcher({source.url: ContentFetchResult(status=FetchStatus.OK, text="Acme Corp uses Coveo.")})
    CollectionRunner(fetcher_run1, snapshots, facts, deltas, fetch_runs).run(tenant_id=1, sources=[(source, context)])

    fetcher_run2 = FakeContentFetcher({
        source.url: ContentFetchResult(
            status=FetchStatus.OK,
            text="Acme Corp uses Coveo.\nWidget Inc uses Coveo and saw a 40% increase in conversion after launch.",
        ),
    })
    result2 = CollectionRunner(fetcher_run2, snapshots, facts, deltas, fetch_runs).run(tenant_id=1, sources=[(source, context)])

    assert result2.finding_count > 0
    assert any(f.fact_json.get("customer_name") == "Widget Inc" for f in facts.saved)
    assert any(d.delta_type == "new_customer_proof" for d in deltas.saved)


def test_collection_runner_records_error_and_keeps_going_on_fetch_failure():
    ok_source = make_source(1, "https://coveo.com/ok")
    fail_source = make_source(2, "https://coveo.com/down")
    ok_context = make_context(url=ok_source.url)
    fail_context = make_context(url=fail_source.url)

    class RaisingFetcher:
        def fetch_content(self, url: str) -> ContentFetchResult:
            if url == fail_source.url:
                raise RuntimeError("boom")
            return ContentFetchResult(status=FetchStatus.OK, text="content")

    snapshots, facts, deltas, fetch_runs = FakeSnapshotRepository(), FakeFactRepository(), FakeDeltaRepository(), FakeFetchRunRepository()
    runner = CollectionRunner(RaisingFetcher(), snapshots, facts, deltas, fetch_runs)

    result = runner.run(tenant_id=1, sources=[(ok_source, ok_context), (fail_source, fail_context)])

    assert result.status == "failed"
    assert result.snapshot_count == 1
    assert len(result.errors) == 1
    assert "boom" in result.errors[0]


def test_collection_runner_snapshots_even_on_fetch_error_status():
    source = make_source(1, "https://coveo.com/broken")
    context = make_context(url=source.url)
    fetcher = FakeContentFetcher({source.url: ContentFetchResult(status=FetchStatus.ERROR, error="timeout")})
    snapshots, facts, deltas, fetch_runs = FakeSnapshotRepository(), FakeFactRepository(), FakeDeltaRepository(), FakeFetchRunRepository()
    runner = CollectionRunner(fetcher, snapshots, facts, deltas, fetch_runs)

    result = runner.run(tenant_id=1, sources=[(source, context)])

    assert result.snapshot_count == 1
    assert snapshots.saved[0].content_hash is None
    assert result.finding_count == 0


# ---------------------------------------------------------------------------
# run_discovery_sweep
# ---------------------------------------------------------------------------

class FakeProbeFetcher:
    def __init__(self, reachable: dict[str, FetchResult]):
        self._reachable = reachable

    def fetch(self, url: str) -> FetchResult:
        return self._reachable.get(url, FetchResult(reachable=False, error="not_stubbed"))


class FakeExistingSourceLookup:
    def exists(self, tenant_id: int, normalized_url: str) -> bool:
        return False


class FakeSourceRepository:
    def __init__(self) -> None:
        self._by_url: dict[str, Source] = {}
        self.saved: list[Source] = []

    def get_by_normalized_url(self, tenant_id: int, normalized_url: str):
        return self._by_url.get(normalized_url)

    def upsert(self, source: Source) -> Source:
        source = source.model_copy(update={"id": len(self.saved) + 1})
        self._by_url[source.normalized_url] = source
        self.saved.append(source)
        return source


def test_run_discovery_sweep_promotes_validated_candidates_end_to_end():
    competitor = Competitor(id=1, tenant_id=1, name="Coveo")
    discoverer = SourceDiscoverer(providers=[
        _StubProvider([DiscoveredUrl(url="https://coveo.com/blog", source_family="blog")])
    ])
    validator = SourceValidator(
        FakeProbeFetcher({"https://coveo.com/blog": FetchResult(reachable=True, http_status=200)}),
        FakeExistingSourceLookup(),
    )
    health_events: list[SourceHealthEvent] = []
    lifecycle = SourceLifecycle(FakeSourceRepository(), health_events.append)

    promoted = run_discovery_sweep(1, [competitor], discoverer, validator, lifecycle)

    assert len(promoted) == 1
    assert promoted[0].status == SourceStatus.ACTIVE
    assert promoted[0].normalized_url == "https://coveo.com/blog"


def test_run_discovery_sweep_drops_unreachable_candidates_without_promoting():
    competitor = Competitor(id=1, tenant_id=1, name="Coveo")
    discoverer = SourceDiscoverer(providers=[
        _StubProvider([DiscoveredUrl(url="https://coveo.com/dead")])
    ])
    validator = SourceValidator(
        FakeProbeFetcher({"https://coveo.com/dead": FetchResult(reachable=False, error="http_error")}),
        FakeExistingSourceLookup(),
    )
    lifecycle = SourceLifecycle(FakeSourceRepository(), lambda event: None)

    promoted = run_discovery_sweep(1, [competitor], discoverer, validator, lifecycle)

    assert promoted == []


class _StubProvider:
    def __init__(self, hits: list[DiscoveredUrl]):
        self._hits = hits

    def discover(self, competitor: Competitor) -> list[DiscoveredUrl]:
        return self._hits
