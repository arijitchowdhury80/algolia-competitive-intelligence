"""Postgres implementations of learn/recorder.py's repository Protocols."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from cios.db.session import tenant_context
from cios.learn.types import (
    ImprovementItem,
    ImprovementPriority,
    ImprovementStatus,
    LearningEvent,
    LearningEventStatus,
    LearningEventType,
)

_LEARNING_EVENT_COLUMNS = (
    "id, tenant_id, run_id, event_type, lesson, proposed_change, status, created_at"
)
_IMPROVEMENT_ITEM_COLUMNS = (
    "id, tenant_id, source, problem, proposed_fix, priority, status, created_at"
)


def _row_to_learning_event(row: dict[str, Any]) -> LearningEvent:
    return LearningEvent(
        id=row["id"],
        tenant_id=row["tenant_id"],
        run_id=row["run_id"],
        event_type=LearningEventType(row["event_type"]),
        lesson=row["lesson"],
        proposed_change=row["proposed_change"],
        status=LearningEventStatus(row["status"]),
        created_at=row["created_at"],
    )


def _row_to_improvement_item(row: dict[str, Any]) -> ImprovementItem:
    return ImprovementItem(
        id=row["id"],
        tenant_id=row["tenant_id"],
        source=row["source"],
        problem=row["problem"],
        proposed_fix=row["proposed_fix"],
        priority=ImprovementPriority(row["priority"]),
        status=ImprovementStatus(row["status"]),
        created_at=row["created_at"],
    )


class PgLearningEventRepository:
    """Implements learn.recorder.LearningEventRepository against `learning_events`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def insert(self, event: LearningEvent) -> LearningEvent:
        with tenant_context(self._conn, event.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO learning_events (
                        tenant_id, run_id, event_type, lesson, proposed_change, status, created_at
                    ) VALUES (%(tenant_id)s, %(run_id)s, %(event_type)s, %(lesson)s, %(proposed_change)s,
                              %(status)s, %(created_at)s)
                    RETURNING {_LEARNING_EVENT_COLUMNS}
                    """,
                    {
                        "tenant_id": event.tenant_id,
                        "run_id": event.run_id,
                        "event_type": event.event_type.value,
                        "lesson": event.lesson,
                        "proposed_change": event.proposed_change,
                        "status": event.status.value,
                        "created_at": event.created_at,
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_learning_event(row)


class PgImprovementQueueRepository:
    """Implements learn.recorder.ImprovementQueueRepository against `improvement_queue`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def insert(self, item: ImprovementItem) -> ImprovementItem:
        with tenant_context(self._conn, item.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO improvement_queue (
                        tenant_id, source, problem, proposed_fix, priority, status, created_at
                    ) VALUES (%(tenant_id)s, %(source)s, %(problem)s, %(proposed_fix)s, %(priority)s,
                              %(status)s, %(created_at)s)
                    RETURNING {_IMPROVEMENT_ITEM_COLUMNS}
                    """,
                    {
                        "tenant_id": item.tenant_id,
                        "source": item.source,
                        "problem": item.problem,
                        "proposed_fix": item.proposed_fix,
                        "priority": item.priority.value,
                        "status": item.status.value,
                        "created_at": item.created_at,
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_improvement_item(row)
