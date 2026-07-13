"""Tests for product-surface repair admin controls and history."""

from __future__ import annotations

import json
from pathlib import Path

from cios.admin.product_surface_repair import ProductSurfaceRepairHistoryStore


def test_product_surface_repair_history_reads_latest_admin_repair_summary(tmp_path) -> None:
    tenant_root = tmp_path / "algolia" / "product-surface-repairs"
    older = tenant_root / "20260712T010000Z"
    newer = tenant_root / "20260712T020000Z"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "repair-summary.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "selected": 1,
                "succeeded": 0,
                "failed": 1,
                "generated_at": "2026-07-12T01:00:00+00:00",
                "results": [
                    {
                        "status": "failed",
                        "target": {"company_name": "Coveo", "surface_id": 10},
                        "category": "no_markdown",
                        "error": "HTTP 403",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (newer / "admin-repair-summary.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "selected": 1,
                "succeeded": 1,
                "failed": 0,
                "generated_at": "2026-07-12T02:00:00+00:00",
                "scout_paths": ["/tmp/repair.json"],
                "argus_refresh": {"product_event_count": 1, "verdict": "watch"},
                "argus_read": {"top_insight": "Repair imported one product proof row."},
                "results": [
                    {
                        "status": "succeeded",
                        "target": {"company_name": "Coveo", "surface_id": 11},
                        "category": "no_markdown",
                        "row_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = ProductSurfaceRepairHistoryStore(work_root=tmp_path).status("algolia", limit=5)

    assert status["tenant_slug"] == "algolia"
    assert status["attempt_count"] == 2
    assert status["latest"]["status"] == "succeeded"
    assert status["latest"]["company_name"] == "Coveo"
    assert status["latest"]["surface_id"] == 11
    assert status["latest"]["category"] == "no_markdown"
    assert status["latest"]["row_count"] == 1
    assert status["latest"]["imported_product_event_count"] == 1
    assert status["latest"]["argus_top_insight"] == "Repair imported one product proof row."
    assert status["attempts"][1]["status"] == "failed"
    assert status["attempts"][1]["error"] == "HTTP 403"


def test_product_surface_repair_history_returns_empty_status_when_no_repairs_exist(tmp_path) -> None:
    status = ProductSurfaceRepairHistoryStore(work_root=tmp_path).status("algolia")

    assert status["tenant_slug"] == "algolia"
    assert status["attempt_count"] == 0
    assert status["latest"] is None
    assert status["attempts"] == []
