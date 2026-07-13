"""Tests for the Hermes-callable product-surface export planner script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "plan_product_surface_exports.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("plan_product_surface_exports", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeProductSurfaceRepo:
    def get_active_targets(self, tenant_id: int):
        assert tenant_id == 1
        return [
            ProductSurfaceTarget(
                surface_id=11,
                tenant_id=1,
                company_id=20,
                company_name="Constructor",
                company_role="competitor",
                surface_family="changelog",
                url="https://constructor.com/changelog",
            ),
            ProductSurfaceTarget(
                surface_id=12,
                tenant_id=1,
                company_id=21,
                company_name="Coveo",
                company_role="competitor",
                surface_family="docs",
                url="https://www.coveo.com/en/docs",
            )
        ]


def test_plan_product_surface_exports_script_writes_json_plan(tmp_path, monkeypatch) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "surface-exports"

    monkeypatch.setattr(module, "get_connection", lambda: _null_connection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", lambda _conn: _FakeProductSurfaceRepo())

    code = module.main([
        "--tenant-id",
        "1",
        "--output-dir",
        str(output_dir),
        "--plan-output",
        str(plan_path),
        "--python-bin",
        "/usr/bin/python3",
        "--script-path",
        "/opt/cios/scripts/export_product_surface_with_scout.py",
        "--scout-bin",
        "scout",
        "--provider",
        "gemini/gemini-2.5-flash",
        "--timeout-seconds",
        "90",
        "--js",
    ])

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["tenant_id"] == 1
    assert payload["target_count"] == 2
    assert payload["items"][0]["output_path"] == str(output_dir / "000011-constructor-changelog.json")
    assert payload["items"][0]["target"]["company_name"] == "Constructor"
    assert payload["items"][0]["command"][0:2] == [
        "/usr/bin/python3",
        "/opt/cios/scripts/export_product_surface_with_scout.py",
    ]


def test_plan_product_surface_exports_script_applies_learning_plan_priority(tmp_path, monkeypatch) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    learning_plan = tmp_path / "next-sweep-learning-plan.json"
    output_dir = tmp_path / "surface-exports"
    learning_plan.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "instructions": [
                    {
                        "kind": "coverage_recheck",
                        "instruction": "Re-audit Coveo source coverage before ranking Constructor again.",
                        "source_improvement_ids": [202],
                    }
                ],
                "skipped": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "get_connection", lambda: _null_connection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", lambda _conn: _FakeProductSurfaceRepo())

    code = module.main([
        "--tenant-id",
        "1",
        "--output-dir",
        str(output_dir),
        "--plan-output",
        str(plan_path),
        "--learning-plan",
        str(learning_plan),
    ])

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert code == 0
    assert [item["target"]["company_name"] for item in payload["items"]] == ["Coveo", "Constructor"]
    assert payload["items"][0]["learning_priority"] == 100
    assert payload["items"][0]["learning_reasons"] == [
        "coverage_recheck: Re-audit Coveo source coverage before ranking Constructor again."
    ]


def test_plan_product_surface_exports_script_filters_targets_by_company_and_limit(tmp_path, monkeypatch) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "surface-exports"

    monkeypatch.setattr(module, "get_connection", lambda: _null_connection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", lambda _conn: _FakeProductSurfaceRepo())

    code = module.main(
        [
            "--tenant-id",
            "1",
            "--output-dir",
            str(output_dir),
            "--plan-output",
            str(plan_path),
            "--company-name",
            "Coveo",
            "--limit",
            "1",
        ]
    )

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["tenant_id"] == 1
    assert payload["target_count"] == 1
    assert [item["target"]["company_name"] for item in payload["items"]] == ["Coveo"]
    assert payload["items"][0]["output_path"] == str(output_dir / "000012-coveo-docs.json")


def test_plan_product_surface_exports_script_passes_focus_capability(tmp_path, monkeypatch) -> None:
    module = _load_module()
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "surface-exports"

    monkeypatch.setattr(module, "get_connection", lambda: _null_connection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", lambda _conn: _FakeProductSurfaceRepo())

    code = module.main(
        [
            "--tenant-id",
            "1",
            "--output-dir",
            str(output_dir),
            "--plan-output",
            str(plan_path),
            "--company-name",
            "Coveo",
            "--focus-capability",
            "Channel Assistant",
            "--limit",
            "1",
        ]
    )

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    command = payload["items"][0]["command"]
    assert code == 0
    assert payload["items"][0]["focus_capability"] == "Channel Assistant"
    assert command[command.index("--focus-capability") + 1] == "Channel Assistant"


class _null_connection:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return None
