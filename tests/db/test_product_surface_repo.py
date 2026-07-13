from __future__ import annotations

from contextlib import contextmanager

from cios.db.repos.product_surfaces import PgProductSurfaceRepository
from cios.hunter.types import ValidationResult
from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget


class _FakeCursor:
    def __init__(self, rows: list[dict] | None = None, row: dict | None = None) -> None:
        self.rows = rows
        self.row = row
        self.sql = ""
        self.params = None
        self.executed: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params) -> None:
        self.sql = sql
        self.params = params
        self.executed.append((sql, params))

    def fetchone(self) -> dict | None:
        return self.row

    def fetchall(self) -> list[dict]:
        return self.rows or []


class _FakeConnection:
    def __init__(self, rows: list[dict] | None = None, row: dict | None = None) -> None:
        self.cursor_obj = _FakeCursor(rows=rows, row=row)
        self.executed: list[tuple] = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, *args, **kwargs) -> None:
        self.executed.append((args, kwargs))
        return None

    def cursor(self, **_kwargs) -> _FakeCursor:
        return self.cursor_obj


def test_get_active_targets_reads_product_surfaces_as_scout_targets() -> None:
    conn = _FakeConnection(
        rows=[
            {
                "surface_id": 11,
                "tenant_id": 1,
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "surface_family": "changelog",
                "url": "https://constructor.com/changelog",
            }
        ]
    )

    targets = PgProductSurfaceRepository(conn).get_active_targets(tenant_id=1)

    assert len(targets) == 1
    assert targets[0].surface_id == 11
    assert targets[0].company_name == "Constructor"
    assert targets[0].surface_family == "changelog"
    assert targets[0].url == "https://constructor.com/changelog"
    assert "FROM product_surfaces" in conn.cursor_obj.sql
    assert "status = 'active'" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1,)


def test_get_by_normalized_url_dedupes_against_product_surfaces_only() -> None:
    conn = _FakeConnection(
        row={
            "id": 501,
            "tenant_id": 1,
            "normalized_url": "https://athoscommerce.com/docs",
            "status": "active",
            "company_name": "Athos Commerce",
            "company_role": "competitor",
            "surface_family": "docs",
            "url": "https://athoscommerce.com/docs",
        }
    )

    row = PgProductSurfaceRepository(conn).get_by_normalized_url(
        tenant_id=1,
        normalized_url="https://athoscommerce.com/docs",
    )

    assert row == {
        "id": 501,
        "tenant_id": 1,
        "normalized_url": "https://athoscommerce.com/docs",
        "status": "active",
        "company_name": "Athos Commerce",
        "company_role": "competitor",
        "surface_family": "docs",
        "url": "https://athoscommerce.com/docs",
    }
    assert "FROM product_surfaces" in conn.cursor_obj.sql
    assert "normalized_url = %s" in conn.cursor_obj.sql
    assert conn.cursor_obj.params == (1, "https://athoscommerce.com/docs")


def test_upsert_target_writes_product_surfaces_without_reactivating_existing_paused_rows() -> None:
    conn = _FakeConnection(row={"id": 44})
    target = ProductSurfaceTarget(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        surface_family="changelog",
        url="https://constructor.com/changelog",
    )

    surface_id = PgProductSurfaceRepository(conn).upsert_seed_target(target)

    assert surface_id == 44
    assert "INSERT INTO product_surfaces" in conn.cursor_obj.sql
    assert "ON CONFLICT" in conn.cursor_obj.sql
    assert "status = product_surfaces.status" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["competitor_id"] == 20
    assert conn.cursor_obj.params["surface_family"] == "changelog"


def test_upsert_candidate_target_writes_candidate_without_reactivating_operator_paused_rows() -> None:
    conn = _FakeConnection(row={"id": 55})
    target = ProductSurfaceTarget(
        tenant_id=1,
        company_id=7,
        company_name="Athos Commerce",
        company_role="competitor",
        surface_family="docs",
        url="https://athoscommerce.com/docs",
    )
    validation = ValidationResult(
        accepted=True,
        reason="validated",
        url="https://athoscommerce.com/docs",
        normalized_url="https://athoscommerce.com/docs",
        source_family="docs",
        http_status=200,
    )

    surface_id = PgProductSurfaceRepository(conn).upsert_candidate_target(
        target,
        validation=validation,
        discovery_source="product_muscle_gap_plan",
    )

    assert surface_id == 55
    assert "INSERT INTO product_surfaces" in conn.cursor_obj.sql
    assert "'candidate'" in conn.cursor_obj.sql
    assert "status = CASE" in conn.cursor_obj.sql
    assert "product_surfaces.status IN ('paused', 'retired')" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["competitor_id"] == 7
    assert conn.cursor_obj.params["surface_family"] == "docs"
    assert conn.cursor_obj.params["metadata"].obj["discovered_by"] == "product_muscle_gap_plan"
    assert conn.cursor_obj.params["metadata"].obj["validation"]["http_status"] == 200


def test_promote_validated_candidates_activates_only_discovery_candidates() -> None:
    conn = _FakeConnection(
        rows=[
            {
                "surface_id": 222,
                "tenant_id": 1,
                "company_id": 7,
                "company_name": "Athos Commerce",
                "company_role": "competitor",
                "surface_family": "pricing",
                "url": "https://athoscommerce.com/pricing",
            },
            {
                "surface_id": 223,
                "tenant_id": 1,
                "company_id": 10,
                "company_name": "Searchspring",
                "company_role": "competitor",
                "surface_family": "pricing",
                "url": "https://searchspring.com/pricing",
            },
        ]
    )

    promoted = PgProductSurfaceRepository(conn).promote_validated_candidates(
        tenant_id=1,
        discovery_source="product_muscle_gap_plan",
        promoted_by="hermes",
        limit=10,
    )

    assert [target.surface_id for target in promoted] == [222, 223]
    assert [target.company_name for target in promoted] == ["Athos Commerce", "Searchspring"]
    assert "UPDATE product_surfaces" in conn.cursor_obj.sql
    assert "status = 'candidate'" in conn.cursor_obj.sql
    assert "metadata->>'discovered_by' = %(discovery_source)s" in conn.cursor_obj.sql
    assert "(metadata->'validation'->>'http_status')::integer BETWEEN 200 AND 299" in conn.cursor_obj.sql
    assert "metadata = product_surfaces.metadata || %(metadata)s::jsonb" in conn.cursor_obj.sql
    assert "LIMIT %(limit)s" in conn.cursor_obj.sql
    assert "status = 'active'" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["discovery_source"] == "product_muscle_gap_plan"
    assert conn.cursor_obj.params["promoted_by"] == "hermes"
    assert conn.cursor_obj.params["limit"] == 10


def test_promote_validated_candidates_can_filter_to_one_company() -> None:
    conn = _FakeConnection(
        rows=[
            {
                "surface_id": 222,
                "tenant_id": 1,
                "company_id": 7,
                "company_name": "Klevu",
                "company_role": "competitor",
                "surface_family": "docs",
                "url": "https://docs.klevu.com/",
            }
        ]
    )

    promoted = PgProductSurfaceRepository(conn).promote_validated_candidates(
        tenant_id=1,
        discovery_source="product_muscle_gap_plan",
        promoted_by="argus",
        company_name="Klevu",
        company_id=7,
        surface_family="docs",
        limit=1,
    )

    assert [target.company_name for target in promoted] == ["Klevu"]
    assert "%(company_name)s::text IS NULL OR lower(company_name) = lower(%(company_name)s::text)" in conn.cursor_obj.sql
    assert "%(company_id)s::bigint IS NULL OR COALESCE(competitor_id, 0) = %(company_id)s::bigint" in conn.cursor_obj.sql
    assert "%(surface_family)s::text IS NULL OR surface_family = %(surface_family)s::text" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["company_name"] == "Klevu"
    assert conn.cursor_obj.params["company_id"] == 7
    assert conn.cursor_obj.params["surface_family"] == "docs"
