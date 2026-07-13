from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone

from cios.admin.repository import PgAdminRepository


class _FakeCursor:
    def __init__(self) -> None:
        self.sql_calls: list[str] = []
        self._fetchone_rows = [
            (1,),
            {
                "tenant_id": 1,
                "tenant_slug": "algolia",
                "report_id": 42,
                "report_date": date(2026, 7, 10),
                "cadence": "daily",
                "report_status": "rendered",
                "metadata": {
                    "product_market_summary": {
                        "status": "ran",
                        "next_sweep_plan_path": "/tmp/cios-product-market/algolia/next-sweep-learning-plan.json",
                        "learning_apply_plan_path": "/tmp/cios-product-market/algolia/learning-apply-plan.json",
                        "learning_apply_plan_summary": {
                            "action_count": 1,
                            "skipped_count": 0,
                            "targets": ["source_coverage_policy"],
                            "package_paths": ["config/source-coverage-policy.yaml"],
                        },
                        "product_surface_plan_summary": {
                            "target_count": 2,
                            "learning_prioritized_count": 1,
                            "prioritized_targets": [{"company_name": "Coveo"}],
                        },
                        "product_surface_execution_summary": {
                            "product_plane_status": "degraded",
                            "planned": 2,
                            "succeeded": 1,
                            "empty": 1,
                            "failed": 0,
                            "product_row_count": 7,
                            "empty_scout_paths": [
                                "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json"
                            ],
                            "empty_outputs": [
                                {
                                    "output_path": "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json",
                                    "company_name": "Coveo",
                                    "surface_family": "docs",
                                }
                            ],
                            "company_row_counts": {"Constructor": 7},
                            "surface_family_row_counts": {"changelog": 7},
                        },
                        "runner_summary": {
                            "verdict": "watch",
                            "learning_instruction_improvement_ids": [202],
                            "intelligence_brief": {
                                "top_insight": "Report metadata says recheck coverage.",
                            },
                        },
                        "ledger_refresh_status": "ran",
                        "ledger_refresh_summary": {
                            "verdict": "watch",
                            "learning_instruction_count": 1,
                            "learning_instruction_improvement_ids": [202],
                            "intelligence_brief": {
                                "top_insight": "Ledger replay says coverage gate held the action.",
                            },
                        },
                        "scout_paths": ["/tmp/cios-product-market/algolia/surface-exports/000030-coveo-docs.json"],
                    },
                    "run_errors": [],
                },
            },
        ]
        self._fetchall_rows = [
            [
                {
                    "id": 88,
                    "verdict": "watch",
                    "intelligence_brief": {
                        "top_insight": "Durable run intelligence says coverage gate held the action.",
                        "primary_action": None,
                        "confidence_limits": ["Coveo source coverage was degraded."],
                        "evidence_urls": ["https://constructor.com/changelog"],
                    },
                    "product_event_count": 2,
                    "conversation_theme_count": 1,
                    "demand_signal_count": 1,
                    "feature_position_count": 2,
                    "pattern_count": 1,
                    "recommendation_count": 0,
                    "learning_instruction_count": 1,
                    "learning_instruction_improvement_ids": [202],
                    "created_at": datetime(2026, 7, 10, 5, 13, tzinfo=timezone.utc),
                }
            ]
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql: str, _params=None) -> None:
        self.sql_calls.append(sql)

    def fetchone(self):
        return self._fetchone_rows.pop(0)

    def fetchall(self):
        return self._fetchall_rows.pop(0)


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, *_args, **_kwargs) -> None:
        return None

    def cursor(self, **_kwargs) -> _FakeCursor:
        return self.cursor_obj


def test_latest_run_status_reads_product_market_summary_from_latest_report_metadata() -> None:
    conn = _FakeConnection()

    status = PgAdminRepository(conn).latest_run_status("algolia")

    assert status.report_id == 42
    assert status.product_market_status == "ran"
    assert status.next_sweep_plan_path.endswith("next-sweep-learning-plan.json")
    assert status.learning_apply_plan_path.endswith("learning-apply-plan.json")
    assert status.learning_apply_plan_summary["targets"] == ["source_coverage_policy"]
    assert status.product_surface_plan_summary["learning_prioritized_count"] == 1
    assert status.product_surface_plan_summary["prioritized_targets"][0]["company_name"] == "Coveo"
    assert status.product_surface_execution_summary["product_plane_status"] == "degraded"
    assert status.product_surface_execution_summary["product_row_count"] == 7
    assert status.product_surface_execution_summary["empty_outputs"][0]["company_name"] == "Coveo"
    assert status.runner_summary["learning_instruction_improvement_ids"] == [202]
    assert status.ledger_refresh_status == "ran"
    assert status.ledger_refresh_summary["learning_instruction_improvement_ids"] == [202]
    assert status.ledger_refresh_summary["intelligence_brief"]["top_insight"].startswith("Ledger replay")
    assert status.latest_intelligence_brief["top_insight"].startswith("Durable run intelligence")
    assert status.run_intelligence_history[0].run_intelligence_id == 88
    assert status.run_intelligence_history[0].top_insight.startswith("Durable run intelligence")
    assert status.run_intelligence_history[0].learning_instruction_improvement_ids == [202]
    assert any("FROM reports" in sql for sql in conn.cursor_obj.sql_calls)
    assert any("FROM product_market_run_intelligence" in sql for sql in conn.cursor_obj.sql_calls)
