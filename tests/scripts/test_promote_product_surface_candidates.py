from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "promote_product_surface_candidates.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("promote_product_surface_candidates", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _NullConnection:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class _FakeTenantConnection:
    def __init__(self, tenant_rows: dict[str, dict]) -> None:
        self.tenant_rows = tenant_rows
        self.params = None
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self, row_factory=None):
        del row_factory
        return self

    def execute(self, _query: str, params: tuple[str]) -> None:
        self.params = params

    def fetchone(self):
        return self.tenant_rows.get(self.params[0])

    def commit(self) -> None:
        self.committed = True


class _FakeProductSurfaceRepository:
    expected_tenant_id = 1

    def __init__(self, _conn) -> None:
        pass

    def promote_validated_candidates(
        self,
        *,
        tenant_id: int,
        discovery_source: str,
        promoted_by: str,
        company_name: str | None = None,
        company_id: int | None = None,
        surface_family: str | None = None,
        limit: int | None,
    ):
        assert tenant_id == self.expected_tenant_id
        assert discovery_source == "product_muscle_gap_plan"
        assert promoted_by == "hermes"
        assert company_name == getattr(self, "expected_company_name", None)
        assert company_id == getattr(self, "expected_company_id", None)
        assert surface_family == getattr(self, "expected_surface_family", None)
        assert limit == 2
        return [
            ProductSurfaceTarget(
                surface_id=222,
                tenant_id=1,
                company_id=7,
                company_name="Athos Commerce",
                company_role="competitor",
                surface_family="pricing",
                url="https://athoscommerce.com/pricing",
            )
        ]


def test_promote_product_surface_candidates_script_writes_summary(tmp_path, monkeypatch) -> None:
    module = _load_module()
    output_json = tmp_path / "summary.json"
    monkeypatch.setattr(module, "get_connection", lambda: _NullConnection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)

    code = module.main([
        "--tenant-id",
        "1",
        "--discovery-source",
        "product_muscle_gap_plan",
        "--promoted-by",
        "hermes",
        "--limit",
        "2",
        "--output",
        str(output_json),
    ])

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert code == 0
    assert payload == {
        "status": "completed",
        "promoted_count": 1,
        "promoted_surfaces": [
            {
                "surface_id": 222,
                "tenant_id": 1,
                "company_id": 7,
                "company_name": "Athos Commerce",
                "company_role": "competitor",
                "surface_family": "pricing",
                "url": "https://athoscommerce.com/pricing",
            }
        ],
    }


def test_promote_product_surface_candidates_script_commits_promotions(tmp_path, monkeypatch) -> None:
    module = _load_module()
    output_json = tmp_path / "summary.json"
    conn = _NullConnection()
    monkeypatch.setattr(module, "get_connection", lambda: conn)
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)

    code = module.main([
        "--tenant-id",
        "1",
        "--discovery-source",
        "product_muscle_gap_plan",
        "--promoted-by",
        "hermes",
        "--limit",
        "2",
        "--output",
        str(output_json),
    ])

    assert code == 0
    assert conn.committed is True


def test_promote_product_surface_candidates_script_resolves_tenant_slug(tmp_path, monkeypatch) -> None:
    module = _load_module()
    output_json = tmp_path / "summary.json"
    _FakeProductSurfaceRepository.expected_tenant_id = 42
    monkeypatch.setattr(module, "get_connection", lambda: _FakeTenantConnection({"algolia": {"id": 42}}))
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)

    try:
        code = module.main([
            "--tenant",
            "algolia",
            "--discovery-source",
            "product_muscle_gap_plan",
            "--promoted-by",
            "hermes",
            "--limit",
            "2",
            "--output",
            str(output_json),
        ])
    finally:
        _FakeProductSurfaceRepository.expected_tenant_id = 1

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["promoted_count"] == 1


def test_promote_product_surface_candidates_script_passes_company_filters(tmp_path, monkeypatch) -> None:
    module = _load_module()
    output_json = tmp_path / "summary.json"
    _FakeProductSurfaceRepository.expected_company_name = "Klevu"
    _FakeProductSurfaceRepository.expected_company_id = 7
    _FakeProductSurfaceRepository.expected_surface_family = "docs"
    monkeypatch.setattr(module, "get_connection", lambda: _NullConnection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)

    try:
        code = module.main([
            "--tenant-id",
            "1",
            "--discovery-source",
            "product_muscle_gap_plan",
            "--promoted-by",
            "hermes",
            "--company-name",
            "Klevu",
            "--company-id",
            "7",
            "--surface-family",
            "docs",
            "--limit",
            "2",
            "--output",
            str(output_json),
        ])
    finally:
        _FakeProductSurfaceRepository.expected_company_name = None
        _FakeProductSurfaceRepository.expected_company_id = None
        _FakeProductSurfaceRepository.expected_surface_family = None

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["promoted_count"] == 1
