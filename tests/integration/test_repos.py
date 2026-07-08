"""Round-trip tests for every Pg*Repository against a live Postgres.

Each repo is exercised through the `cios_app` role (the `app_conn` fixture)
-- the same RLS-bound role production code uses -- via the repo's own save/
upsert method, then read back via the repo's own read method (or a direct
SELECT through the superuser `pg_conn` when the repo has no read method).
"""

from __future__ import annotations

import uuid

import pytest

from cios.collect.types import Delta, ExtractedFact, FetchRunResult, Snapshot
from cios.db.repos.collect import (
    PgDeltaRepository,
    PgFactRepository,
    PgFetchRunRepository,
    PgSnapshotRepository,
)
from cios.db.repos.delivery import PgBotDeliveryRepository, PgDeliveryAttemptRepository
from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.repos.sources import PgSourceRepository
from cios.delivery.types import (
    BotDeliveryRecord,
    BotDeliveryStatus,
    Cadence,
    DeliveryAttemptRecord,
    DeliveryAttemptStatus,
)
from cios.hunter.types import Source, SourceStatus
from cios.learn.types import ImprovementItem, ImprovementPriority, LearningEvent, LearningEventType
from cios.platform.channels.types import Channel

pytestmark = pytest.mark.integration


@pytest.fixture()
def tenant_and_competitor(pg_conn):
    """Fresh tenant + competitor, created via the superuser connection
    (bypasses RLS) so every test gets isolated FK-valid ids."""
    unique = uuid.uuid4().hex
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug) VALUES (%s, %s) RETURNING id",
            (f"Test Tenant {unique}", f"test-tenant-{unique}"),
        )
        (tenant_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO competitors (tenant_id, name) VALUES (%s, %s) RETURNING id",
            (tenant_id, "Acme Co"),
        )
        (competitor_id,) = cur.fetchone()
    pg_conn.commit()
    return tenant_id, competitor_id


class TestPgSourceRepository:
    def test_upsert_then_get_by_normalized_url_round_trips(self, app_conn, tenant_and_competitor):
        tenant_id, competitor_id = tenant_and_competitor
        repo = PgSourceRepository(app_conn)
        source = Source(
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            source_family="blog",
            url="https://acme.example/blog",
            normalized_url="https://acme.example/blog",
            status=SourceStatus.ACTIVE,
        )

        saved = repo.upsert(source)
        fetched = repo.get_by_normalized_url(tenant_id, "https://acme.example/blog")

        assert saved.id is not None
        assert fetched is not None
        assert fetched.id == saved.id
        assert fetched.normalized_url == "https://acme.example/blog"
        assert fetched.status == SourceStatus.ACTIVE

    def test_upsert_is_not_a_duplicate_for_same_normalized_url(self, app_conn, tenant_and_competitor):
        tenant_id, competitor_id = tenant_and_competitor
        repo = PgSourceRepository(app_conn)
        base = Source(
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            source_family="blog",
            url="https://acme.example/dup",
            normalized_url="https://acme.example/dup",
        )
        first = repo.upsert(base)
        second = repo.upsert(base.model_copy(update={"title": "updated title"}))

        assert first.id == second.id
        assert second.title == "updated title"


class TestPgSnapshotAndFetchRunRepositories:
    def test_fetch_run_start_finish_round_trips(self, app_conn, tenant_and_competitor):
        tenant_id, _ = tenant_and_competitor
        repo = PgFetchRunRepository(app_conn)

        run = repo.start(tenant_id)
        assert run.id is not None
        assert run.status == "running"

        run.status = "completed"
        run.source_count = 3
        run.finished_at = run.started_at
        finished = repo.finish(run)

        assert finished.status == "completed"
        assert finished.source_count == 3
        assert finished.finished_at is not None

    def test_snapshot_save_then_latest_round_trips(self, app_conn, tenant_and_competitor):
        tenant_id, competitor_id = tenant_and_competitor
        source_repo = PgSourceRepository(app_conn)
        source = source_repo.upsert(
            Source(
                tenant_id=tenant_id,
                competitor_id=competitor_id,
                source_family="blog",
                url="https://acme.example/snap",
                normalized_url="https://acme.example/snap",
            )
        )

        snapshot_repo = PgSnapshotRepository(app_conn)
        snapshot = Snapshot(
            tenant_id=tenant_id,
            source_id=source.id,
            content_hash="abc123",
            title="Acme blog",
            text="Acme Corp launched a widget.",
        )
        saved = snapshot_repo.save(snapshot)
        latest = snapshot_repo.latest(tenant_id, source.id)

        assert saved.id is not None
        assert latest is not None
        assert latest.id == saved.id
        assert latest.text == "Acme Corp launched a widget."
        assert latest.content_hash == "abc123"


class TestPgFactAndDeltaRepositories:
    def test_fact_save_round_trips_via_direct_select(self, pg_conn, app_conn, tenant_and_competitor):
        tenant_id, competitor_id = tenant_and_competitor
        repo = PgFactRepository(app_conn, tenant_id)
        fact = ExtractedFact(
            competitor_id=competitor_id,
            fact_type="new_customer_proof",
            statement="Widget Inc uses Acme.",
            evidence_url="https://acme.example/case-study",
            evidence_text="Widget Inc saw a 40% lift.",
            confidence=0.75,
        )

        saved = repo.save(fact)
        assert saved.id is not None

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, competitor_id, fact_type, statement, evidence_ids, confidence "
                "FROM semantic_facts WHERE id = %s",
                (saved.id,),
            )
            row = cur.fetchone()
        assert row[0] == tenant_id
        assert row[1] == competitor_id
        assert row[2] == "new_customer_proof"
        assert row[3] == "Widget Inc uses Acme."
        assert len(row[4]) == 1
        assert row[4][0]["url"] == "https://acme.example/case-study"
        assert float(row[5]) == pytest.approx(0.75)

    def test_delta_save_round_trips_via_direct_select(self, pg_conn, app_conn, tenant_and_competitor):
        tenant_id, competitor_id = tenant_and_competitor
        repo = PgDeltaRepository(app_conn, tenant_id)
        delta = Delta(
            competitor_id=competitor_id,
            delta_type="new_customer_proof",
            materiality_score=0.9,
            what_changed="New case study published.",
            evidence_urls=["https://acme.example/case-study"],
            quality_status="published",
        )

        saved = repo.save(delta)
        assert saved.id is not None

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, delta_type, what_changed, evidence_ids, quality_status "
                "FROM semantic_deltas WHERE id = %s",
                (saved.id,),
            )
            row = cur.fetchone()
        assert row[0] == tenant_id
        assert row[1] == "new_customer_proof"
        assert row[3] == ["https://acme.example/case-study"]
        assert row[4] == "published"


class TestPgDeliveryRepositories:
    def test_bot_delivery_save_round_trips_via_direct_select(self, pg_conn, app_conn, tenant_and_competitor):
        tenant_id, _ = tenant_and_competitor
        repo = PgBotDeliveryRepository(app_conn)
        record = BotDeliveryRecord(
            tenant_id=tenant_id,
            cadence=Cadence.DAILY,
            channel=Channel.TELEGRAM,
            recipient_redacted="****1234",
            status=BotDeliveryStatus.SENDING,
        )

        saved = repo.save(record)
        assert saved.id is not None

        updated = repo.save(saved.model_copy(update={"status": BotDeliveryStatus.SENT}))
        assert updated.status == BotDeliveryStatus.SENT

        with pg_conn.cursor() as cur:
            cur.execute("SELECT status, channel FROM bot_deliveries WHERE id = %s", (updated.id,))
            row = cur.fetchone()
        assert row[0] == "sent"
        assert row[1] == "telegram"

    def test_delivery_attempt_save_round_trips_via_direct_select(self, pg_conn, app_conn, tenant_and_competitor):
        tenant_id, _ = tenant_and_competitor
        repo = PgDeliveryAttemptRepository(app_conn)
        record = DeliveryAttemptRecord(
            tenant_id=tenant_id,
            channel=Channel.EMAIL,
            status=DeliveryAttemptStatus.SENT,
            delivery_ref="msg-123",
        )

        saved = repo.save(record)
        assert saved.id is not None

        with pg_conn.cursor() as cur:
            cur.execute("SELECT status, delivery_ref FROM delivery_attempts WHERE id = %s", (saved.id,))
            row = cur.fetchone()
        assert row[0] == "sent"
        assert row[1] == "msg-123"


class TestPgLearnRepositories:
    def test_learning_event_insert_round_trips_via_direct_select(self, pg_conn, app_conn, tenant_and_competitor):
        tenant_id, _ = tenant_and_competitor
        repo = PgLearningEventRepository(app_conn)
        event = LearningEvent(
            tenant_id=tenant_id,
            event_type=LearningEventType.FETCH_FAILURE,
            lesson="fetch failed for https://acme.example",
            proposed_change="raise retry count",
        )

        saved = repo.insert(event)
        assert saved.id is not None

        with pg_conn.cursor() as cur:
            cur.execute("SELECT event_type, lesson FROM learning_events WHERE id = %s", (saved.id,))
            row = cur.fetchone()
        assert row[0] == "fetch_failure"
        assert row[1] == "fetch failed for https://acme.example"

    def test_improvement_queue_insert_round_trips_via_direct_select(self, pg_conn, app_conn, tenant_and_competitor):
        tenant_id, _ = tenant_and_competitor
        repo = PgImprovementQueueRepository(app_conn)
        item = ImprovementItem(
            tenant_id=tenant_id,
            source="fetch_failure",
            problem="fetch timed out",
            proposed_fix="raise retry count",
            priority=ImprovementPriority.MEDIUM,
        )

        saved = repo.insert(item)
        assert saved.id is not None

        with pg_conn.cursor() as cur:
            cur.execute("SELECT problem, priority FROM improvement_queue WHERE id = %s", (saved.id,))
            row = cur.fetchone()
        assert row[0] == "fetch timed out"
        assert row[1] == "medium"
