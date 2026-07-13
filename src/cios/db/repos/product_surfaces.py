"""Postgres repository for product-surface acquisition targets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.db.repos.collect import _postgres_safe
from cios.db.session import tenant_context
from cios.hunter.types import ValidationResult
from cios.hunter.validator import normalize_url
from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget


class PgProductSurfaceRepository:
    """Read product-reality surfaces that Scout should inspect."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_active_targets(self, tenant_id: int) -> list[ProductSurfaceTarget]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id AS surface_id,
                        tenant_id,
                        COALESCE(competitor_id, 0) AS company_id,
                        company_name,
                        company_role,
                        surface_family,
                        url
                    FROM product_surfaces
                    WHERE tenant_id = %s
                      AND status = 'active'
                    ORDER BY company_role ASC, company_name ASC, surface_family ASC, id ASC
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return [ProductSurfaceTarget(**dict(row)) for row in rows]

    def get_by_normalized_url(self, tenant_id: int, normalized_url: str) -> dict[str, Any] | None:
        """Return an existing product surface by normalized URL, if present."""

        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        tenant_id,
                        normalized_url,
                        status,
                        company_name,
                        company_role,
                        surface_family,
                        url
                    FROM product_surfaces
                    WHERE tenant_id = %s
                      AND normalized_url = %s
                    LIMIT 1
                    """,
                    (tenant_id, normalized_url),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def upsert_seed_target(self, target: ProductSurfaceTarget) -> int:
        """Seed a product surface without overriding operator lifecycle state.

        Seed files are defaults. If an operator has paused or retired an
        existing surface, this upsert refreshes descriptive fields but preserves
        the existing status.
        """

        normalized = normalize_url(target.url)
        with tenant_context(self._conn, target.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO product_surfaces (
                        tenant_id, competitor_id, company_name, company_role,
                        surface_family, url, normalized_url, title, status,
                        metadata, updated_at
                    ) VALUES (
                        %(tenant_id)s, %(competitor_id)s, %(company_name)s, %(company_role)s,
                        %(surface_family)s, %(url)s, %(normalized_url)s, %(title)s, 'active',
                        %(metadata)s, now()
                    )
                    ON CONFLICT (tenant_id, normalized_url) DO UPDATE SET
                        competitor_id = EXCLUDED.competitor_id,
                        company_name = EXCLUDED.company_name,
                        company_role = EXCLUDED.company_role,
                        surface_family = EXCLUDED.surface_family,
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        status = product_surfaces.status,
                        metadata = product_surfaces.metadata || EXCLUDED.metadata,
                        updated_at = now()
                    RETURNING id
                    """,
                    {
                        "tenant_id": target.tenant_id,
                        "competitor_id": None if target.company_role == "own" else target.company_id,
                        "company_name": _postgres_safe(target.company_name),
                        "company_role": target.company_role,
                        "surface_family": target.surface_family,
                        "url": target.url,
                        "normalized_url": normalized,
                        "title": f"{target.company_name} {target.surface_family}",
                        "metadata": Json({"seeded_by": "ci-os-config"}),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def upsert_candidate_target(
        self,
        target: ProductSurfaceTarget,
        *,
        validation: ValidationResult,
        discovery_source: str,
    ) -> int:
        """Store a validated discovery candidate without overriding operators.

        Product-muscle gap discovery is a proposal generator. A validated URL
        earns a `candidate` product surface, but an operator-paused or retired
        row stays paused/retired until a human or separate lifecycle action
        promotes it.
        """

        if not validation.accepted:
            raise ValueError(f"cannot store rejected product surface candidate: {validation.reason}")

        normalized = normalize_url(target.url)
        metadata = {
            "discovered_by": discovery_source,
            "validation": {
                "reason": validation.reason,
                "http_status": validation.http_status,
                "normalized_url": validation.normalized_url,
            },
        }
        with tenant_context(self._conn, target.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO product_surfaces (
                        tenant_id, competitor_id, company_name, company_role,
                        surface_family, url, normalized_url, title, status,
                        metadata, updated_at
                    ) VALUES (
                        %(tenant_id)s, %(competitor_id)s, %(company_name)s, %(company_role)s,
                        %(surface_family)s, %(url)s, %(normalized_url)s, %(title)s, 'candidate',
                        %(metadata)s, now()
                    )
                    ON CONFLICT (tenant_id, normalized_url) DO UPDATE SET
                        competitor_id = EXCLUDED.competitor_id,
                        company_name = EXCLUDED.company_name,
                        company_role = EXCLUDED.company_role,
                        surface_family = EXCLUDED.surface_family,
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        status = CASE
                            WHEN product_surfaces.status IN ('paused', 'retired')
                            THEN product_surfaces.status
                            ELSE EXCLUDED.status
                        END,
                        metadata = product_surfaces.metadata || EXCLUDED.metadata,
                        updated_at = now()
                    RETURNING id
                    """,
                    {
                        "tenant_id": target.tenant_id,
                        "competitor_id": None if target.company_role == "own" else target.company_id,
                        "company_name": _postgres_safe(target.company_name),
                        "company_role": target.company_role,
                        "surface_family": target.surface_family,
                        "url": target.url,
                        "normalized_url": normalized,
                        "title": f"{target.company_name} {target.surface_family}",
                        "metadata": Json(metadata),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def promote_validated_candidates(
        self,
        *,
        tenant_id: int,
        discovery_source: str,
        promoted_by: str,
        company_name: str | None = None,
        company_id: int | None = None,
        surface_family: str | None = None,
        limit: int | None = None,
    ) -> list[ProductSurfaceTarget]:
        """Promote validated candidate surfaces into active Scout targets."""

        limit_sql = "LIMIT %(limit)s" if limit is not None else ""
        promotion_metadata = {
            "promoted_by": promoted_by,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "promotion_source": discovery_source,
        }
        sql = f"""
            WITH eligible AS (
                SELECT id
                FROM product_surfaces
                WHERE tenant_id = %(tenant_id)s
                  AND status = 'candidate'
                  AND metadata->>'discovered_by' = %(discovery_source)s
                  AND (metadata->'validation'->>'http_status')::integer BETWEEN 200 AND 299
                  AND (%(company_name)s::text IS NULL OR lower(company_name) = lower(%(company_name)s::text))
                  AND (%(company_id)s::bigint IS NULL OR COALESCE(competitor_id, 0) = %(company_id)s::bigint)
                  AND (%(surface_family)s::text IS NULL OR surface_family = %(surface_family)s::text)
                ORDER BY updated_at ASC, id ASC
                {limit_sql}
            )
            UPDATE product_surfaces
            SET
                status = 'active',
                metadata = product_surfaces.metadata || %(metadata)s::jsonb,
                updated_at = now()
            FROM eligible
            WHERE product_surfaces.id = eligible.id
              AND product_surfaces.tenant_id = %(tenant_id)s
            RETURNING
                product_surfaces.id AS surface_id,
                product_surfaces.tenant_id,
                COALESCE(product_surfaces.competitor_id, 0) AS company_id,
                product_surfaces.company_name,
                product_surfaces.company_role,
                product_surfaces.surface_family,
                product_surfaces.url
            """
        params = {
            "tenant_id": tenant_id,
            "discovery_source": discovery_source,
            "promoted_by": promoted_by,
            "company_name": _postgres_safe(company_name) if company_name else None,
            "company_id": company_id,
            "surface_family": surface_family,
            "metadata": Json(promotion_metadata),
            "limit": limit,
        }
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [ProductSurfaceTarget(**dict(row)) for row in rows]


__all__ = ["PgProductSurfaceRepository"]
