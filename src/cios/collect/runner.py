"""Collection runner.

Two responsibilities, both orchestration-only (no direct DB/network access;
everything is via injected protocols, mirroring hunter/lifecycle.py):

  1. `CollectionRunner.run()` -- fetch -> snapshot -> delta/extract per
     source, one `intel_fetch_runs` row per sweep. For index/blog-family
     sources, the index page is snapshotted for change detection only;
     facts/deltas are extracted per resolved article so their evidence
     carries the article URL, not the index URL (see article_resolver.py).
  2. `run_discovery_sweep()` -- the discovery -> validate -> lifecycle loop
     that Gate 2 deliberately left unwired: fan each competitor out to the
     hunter's discovery providers, validate each candidate, and upsert
     accepted candidates onto the source ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol

from cios.collect.article_resolver import resolve_article_links
from cios.collect.snapshot import build_snapshot, collector_changed
from cios.collect.extract import content_hash, semantic_diff
from cios.collect.fetcher import ContentFetcher
from cios.collect.types import (
    Delta,
    ExtractedFact,
    FetchRunResult,
    FetchStatus,
    Snapshot,
    SourceContext,
)
from cios.hunter.discovery import SourceDiscoverer
from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import Competitor, Source
from cios.hunter.validator import SourceValidator

# Source families that are index/listing pages rather than a single article:
# facts/deltas must cite the specific article, not the index page.
INDEX_SOURCE_FAMILIES = {"blog", "news"}
DEFAULT_ARTICLE_FETCH_CAP = 5


class SnapshotRepository(Protocol):
    def latest(self, tenant_id: int, source_id: int) -> Optional[Snapshot]: ...

    def save(self, snapshot: Snapshot) -> Snapshot: ...


class FactRepository(Protocol):
    def save(self, fact: ExtractedFact) -> ExtractedFact: ...


class DeltaRepository(Protocol):
    def save(self, delta: Delta) -> Delta: ...


class FetchRunRepository(Protocol):
    def start(self, tenant_id: int) -> FetchRunResult: ...

    def finish(self, run: FetchRunResult) -> FetchRunResult: ...


class CollectionRunner:
    """Fetches each active source once, snapshots it, and extracts facts and
    deltas against the tenant's prior snapshot for that source. One call to
    `run()` produces exactly one `intel_fetch_runs` row."""

    def __init__(
        self,
        content_fetcher: ContentFetcher,
        snapshots: SnapshotRepository,
        facts: FactRepository,
        deltas: DeltaRepository,
        fetch_runs: FetchRunRepository,
        article_fetch_cap: int = DEFAULT_ARTICLE_FETCH_CAP,
    ) -> None:
        self._content_fetcher = content_fetcher
        self._snapshots = snapshots
        self._facts = facts
        self._deltas = deltas
        self._fetch_runs = fetch_runs
        self._article_fetch_cap = article_fetch_cap

    def run(self, tenant_id: int, sources: list[tuple[Source, SourceContext]]) -> FetchRunResult:
        run = self._fetch_runs.start(tenant_id)
        errors: list[str] = []
        snapshot_count = 0
        finding_count = 0
        detected_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for source, context in sources:
            try:
                facts, deltas = self._collect_one(tenant_id, source, context, run.id, detected_date)
                snapshot_count += 1
                finding_count += len(facts) + len(deltas)
            except Exception as exc:  # noqa: BLE001 -- one source's failure must not abort the sweep
                errors.append(f"{source.url}: {exc}")

        run.finished_at = datetime.now(timezone.utc)
        run.status = "completed" if not errors else "failed"
        run.source_count = len(sources)
        run.snapshot_count = snapshot_count
        run.finding_count = finding_count
        run.errors = errors
        return self._fetch_runs.finish(run)

    def _collect_one(
        self,
        tenant_id: int,
        source: Source,
        context: SourceContext,
        fetch_run_id: Optional[int],
        detected_date: str,
    ) -> tuple[list[ExtractedFact], list[Delta]]:
        prior = self._snapshots.latest(tenant_id, source.id)
        old_text = prior.text if prior else ""

        fetch_result = self._content_fetcher.fetch_content(source.url)
        snapshot = build_snapshot(tenant_id, source.id, fetch_run_id, fetch_result, title=source.title)

        if fetch_result.status != FetchStatus.OK:
            self._snapshots.save(snapshot)
            return [], []

        article_urls: list[str] = []
        if source.source_family in INDEX_SOURCE_FAMILIES:
            article_urls = resolve_article_links(fetch_result.text, context.url)[: self._article_fetch_cap]

        if article_urls:
            # A genuine index/blog page: extract per resolved article so
            # facts/deltas cite the article URL, not the index page.
            facts, deltas, article_state = self._collect_articles(
                context, detected_date, article_urls=article_urls, prior=prior
            )
            snapshot.metadata["article_snapshots"] = article_state
        else:
            # Either not an index family, or the page had no resolvable
            # article links (e.g. a single-article page) -- diff it directly.
            facts, deltas = semantic_diff(
                context,
                old_text,
                fetch_result.text,
                detected_date,
                collector_changed=collector_changed(prior, snapshot),
            )

        self._snapshots.save(snapshot)

        for fact in facts:
            self._facts.save(fact)
        for delta in deltas:
            self._deltas.save(delta)

        return facts, deltas

    def _collect_articles(
        self,
        context: SourceContext,
        detected_date: str,
        article_urls: list[str],
        prior: Optional[Snapshot],
    ) -> tuple[list[ExtractedFact], list[Delta], dict[str, dict]]:
        """Fetch each resolved article (bounded by `article_fetch_cap`,
        already applied by the caller) and diff each against ITS OWN prior
        text (kept in the index snapshot's metadata, since source_snapshots
        is keyed one-per-source, not one-per-article) so facts/deltas cite
        the article URL as evidence. One article's fetch failure is isolated
        -- it neither kills the source nor discards that article's history."""
        prior_article_state: dict[str, dict] = dict((prior.metadata or {}).get("article_snapshots") or {}) if prior else {}

        all_facts: list[ExtractedFact] = []
        all_deltas: list[Delta] = []
        new_article_state: dict[str, dict] = {}

        for article_url in article_urls:
            try:
                article_result = self._content_fetcher.fetch_content(article_url)
            except Exception:  # noqa: BLE001 -- one article's failure must not abort the source
                article_result = None

            if article_result is None or article_result.status != FetchStatus.OK:
                if article_url in prior_article_state:
                    new_article_state[article_url] = prior_article_state[article_url]
                continue

            article_context = context.model_copy(update={"url": article_url})
            old_article_text = (prior_article_state.get(article_url) or {}).get("text", "")

            facts, deltas = semantic_diff(
                article_context,
                old_article_text,
                article_result.text,
                detected_date,
                collector_changed=False,
            )
            all_facts.extend(facts)
            all_deltas.extend(deltas)
            new_article_state[article_url] = {
                "content_hash": content_hash(article_result.text),
                "text": article_result.text,
            }

        return all_facts, all_deltas, new_article_state


def run_discovery_sweep(
    tenant_id: int,
    competitors: list[Competitor],
    discoverer: SourceDiscoverer,
    validator: SourceValidator,
    lifecycle: SourceLifecycle,
) -> list[Source]:
    """The discovery -> validate -> lifecycle loop Gate 2 deliberately left
    unwired: fan each competitor out across discovery providers, validate
    every candidate, and upsert accepted candidates onto the source ledger.
    Candidates that fail validation are dropped here (never auto-promoted --
    validator.py already enforces that; this just declines to act on a
    rejection)."""
    promoted: list[Source] = []
    for competitor in competitors:
        for candidate in discoverer.discover(competitor):
            result = validator.validate(tenant_id, candidate.url)
            if not result.accepted:
                continue
            promoted.append(lifecycle.upsert_validated(tenant_id, competitor.id, result))
    return promoted
