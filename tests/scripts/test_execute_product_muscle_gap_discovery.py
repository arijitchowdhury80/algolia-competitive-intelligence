from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.hunter.types import ValidationResult


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "execute_product_muscle_gap_discovery.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("execute_product_muscle_gap_discovery", SCRIPT_PATH)
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
    existing_normalized_urls: set[str] = set()

    def __init__(self, _conn) -> None:
        self.saved = []

    def get_by_normalized_url(self, tenant_id: int, normalized_url: str):
        assert tenant_id in {1, 42}
        if normalized_url in self.existing_normalized_urls:
            return {"id": 501, "normalized_url": normalized_url}
        return None

    def upsert_candidate_target(self, target, *, validation, discovery_source):
        self.saved.append((target, validation, discovery_source))
        return 77


class _FakeValidator:
    expected_tenant_id = 1

    def __init__(self, *, fetcher, existing_sources) -> None:
        self.fetcher = fetcher
        self.existing_sources = existing_sources

    def validate(self, tenant_id: int, url: str) -> ValidationResult:
        assert tenant_id == self.expected_tenant_id
        assert url == "https://athoscommerce.com/docs"
        return ValidationResult(
            accepted=True,
            reason="validated",
            url=url,
            normalized_url=url,
            source_family="docs",
            http_status=200,
        )


class _LookupAwareValidator:
    def __init__(self, *, fetcher, existing_sources) -> None:
        self.existing_sources = existing_sources

    def validate(self, tenant_id: int, url: str) -> ValidationResult:
        normalized_url = "https://athoscommerce.com/docs"
        if self.existing_sources.exists(tenant_id, normalized_url):
            return ValidationResult(
                accepted=False,
                reason="duplicate_normalized_url",
                url=url,
                normalized_url=normalized_url,
            )
        return ValidationResult(
            accepted=True,
            reason="validated",
            url=url,
            normalized_url=normalized_url,
            source_family="docs",
            http_status=200,
        )


def test_execute_product_muscle_gap_discovery_script_reads_dashboard_json_and_writes_summary(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    dashboard_json = tmp_path / "semantic-dashboard.json"
    output_json = tmp_path / "summary.json"
    dashboard_json.write_text(
        json.dumps(
            {
                "product_market_run": {
                    "product_muscle_gap_plan": {
                        "missing_companies": [
                            {
                                "competitor_id": 7,
                                "company_name": "Athos Commerce",
                                "candidate_surface_urls": [
                                    {"surface_family": "docs", "url": "https://athoscommerce.com/docs"}
                                ],
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "get_connection", lambda: _NullConnection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)
    monkeypatch.setattr(module, "HttpContentFetcher", lambda timeout, retries: object())
    monkeypatch.setattr(module, "ProbeFetcherAdapter", lambda fetcher: object())
    monkeypatch.setattr(module, "SourceValidator", _FakeValidator)

    code = module.main([
        "--tenant-id",
        "1",
        "--gap-plan",
        str(dashboard_json),
        "--output",
        str(output_json),
    ])

    summary = json.loads(output_json.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["status"] == "completed"
    assert summary["candidate_url_count"] == 1
    assert summary["validated_count"] == 1
    assert summary["stored_candidates"] == [
        {
            "surface_id": 77,
            "company_name": "Athos Commerce",
            "surface_family": "docs",
            "url": "https://athoscommerce.com/docs",
            "http_status": 200,
        }
    ]


def test_execute_product_muscle_gap_discovery_script_commits_candidate_writes(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    gap_plan = tmp_path / "gap-plan.json"
    output_json = tmp_path / "summary.json"
    gap_plan.write_text(
        json.dumps(
            {
                "missing_companies": [],
                "empty_surface_targets": [
                    {
                        "competitor_id": 7,
                        "company_name": "Athos Commerce",
                        "failed_surface_family": "docs",
                        "heuristic_surface_probes": [
                            {"surface_family": "docs", "url": "https://athoscommerce.com/docs"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    conn = _NullConnection()
    monkeypatch.setattr(module, "get_connection", lambda: conn)
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)
    monkeypatch.setattr(module, "HttpContentFetcher", lambda timeout, retries: object())
    monkeypatch.setattr(module, "ProbeFetcherAdapter", lambda fetcher: object())
    monkeypatch.setattr(module, "SourceValidator", _FakeValidator)

    code = module.main([
        "--tenant-id",
        "1",
        "--gap-plan",
        str(gap_plan),
        "--output",
        str(output_json),
    ])

    assert code == 0
    assert conn.committed is True


def test_execute_product_muscle_gap_discovery_dedupes_against_product_surfaces_not_generic_sources(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    gap_plan = tmp_path / "gap-plan.json"
    output_json = tmp_path / "summary.json"
    gap_plan.write_text(
        json.dumps(
            {
                "missing_companies": [
                    {
                        "competitor_id": 7,
                        "company_name": "Athos Commerce",
                        "candidate_surface_urls": [
                            {"surface_family": "docs", "url": "https://athoscommerce.com/docs"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _FakeProductSurfaceRepository.existing_normalized_urls = set()
    monkeypatch.setattr(module, "get_connection", lambda: _NullConnection())
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)
    monkeypatch.setattr(module, "HttpContentFetcher", lambda timeout, retries: object())
    monkeypatch.setattr(module, "ProbeFetcherAdapter", lambda fetcher: object())
    monkeypatch.setattr(module, "SourceValidator", _LookupAwareValidator)

    try:
        code = module.main([
            "--tenant-id",
            "1",
            "--gap-plan",
            str(gap_plan),
            "--output",
            str(output_json),
        ])
    finally:
        _FakeProductSurfaceRepository.existing_normalized_urls = set()

    summary = json.loads(output_json.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["validated_count"] == 1
    assert summary["stored_candidate_count"] == 1
    assert summary["duplicate_source_count"] == 0


def test_execute_product_muscle_gap_discovery_script_resolves_tenant_slug(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    dashboard_json = tmp_path / "semantic-dashboard.json"
    output_json = tmp_path / "summary.json"
    dashboard_json.write_text(
        json.dumps(
            {
                "product_market_run": {
                    "product_muscle_gap_plan": {
                        "feature_unknown_collection_targets": [
                            {
                                "competitor_id": 7,
                                "company_name": "Athos Commerce",
                                "capability_text": "AI Shopping Agent",
                                "candidate_surface_urls": [
                                    {"surface_family": "docs", "url": "https://athoscommerce.com/docs"}
                                ],
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    _FakeValidator.expected_tenant_id = 42
    monkeypatch.setattr(module, "get_connection", lambda: _FakeTenantConnection({"algolia": {"id": 42}}))
    monkeypatch.setattr(module, "PgProductSurfaceRepository", _FakeProductSurfaceRepository)
    monkeypatch.setattr(module, "HttpContentFetcher", lambda timeout, retries: object())
    monkeypatch.setattr(module, "ProbeFetcherAdapter", lambda fetcher: object())
    monkeypatch.setattr(module, "SourceValidator", _FakeValidator)

    try:
        code = module.main([
            "--tenant",
            "algolia",
            "--gap-plan",
            str(dashboard_json),
            "--output",
            str(output_json),
        ])
    finally:
        _FakeValidator.expected_tenant_id = 1

    summary = json.loads(output_json.read_text(encoding="utf-8"))
    assert code == 0
    assert summary["validated_count"] == 1


def test_execute_product_muscle_gap_discovery_script_accepts_bare_unknown_cell_plan(tmp_path) -> None:
    module = _load_module()
    gap_plan = tmp_path / "gap-plan.json"
    gap_plan.write_text(
        json.dumps(
            {
                "feature_unknown_collection_targets": [
                    {
                        "competitor_id": 7,
                        "company_name": "Athos Commerce",
                        "candidate_surface_urls": [
                            {"surface_family": "docs", "url": "https://athoscommerce.com/docs"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert module._load_gap_plan(gap_plan) == {
        "feature_unknown_collection_targets": [
            {
                "competitor_id": 7,
                "company_name": "Athos Commerce",
                "candidate_surface_urls": [
                    {"surface_family": "docs", "url": "https://athoscommerce.com/docs"}
                ],
            }
        ]
    }
