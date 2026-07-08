from __future__ import annotations

import json

from cios.dashboard.publisher import (
    default_filename,
    publish_to_file,
    to_json_dict,
    to_json_str,
)
from cios.dashboard.state_builder import DashboardStateBuilder

from .conftest import (
    FakeCoverageRepository,
    FakeRunRepository,
    FakeSignalsRepository,
    FakeThesesRepository,
    delta,
    full_coverage,
)


def _sample_state(tenant_id: int = 7):
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({tenant_id: [delta(id=1, materiality_score=0.6)]}),
        theses=FakeThesesRepository({}),
        coverage=FakeCoverageRepository({tenant_id: full_coverage()}),
        runs=FakeRunRepository({}),
    )
    return builder.build(tenant_id=tenant_id, cadence="daily")


def test_to_json_dict_includes_schema_version_and_quiet_flag():
    state = _sample_state()
    payload = to_json_dict(state)
    assert payload["schema_version"] == 2
    assert payload["is_quiet"] is False
    assert payload["tenant_id"] == 7
    assert payload["top_attention_level"] == "watch"


def test_serialization_is_stable_across_calls():
    state = _sample_state()
    first = to_json_str(state)
    second = to_json_str(state)
    assert first == second


def test_serialization_is_json_parseable_and_round_trips_key_fields():
    state = _sample_state()
    parsed = json.loads(to_json_str(state))
    assert parsed["competitor_cards"][0]["competitor_id"] == 1
    assert parsed["coverage"]["lanes"]


def test_publish_to_file_writes_readable_json(tmp_path):
    state = _sample_state()
    out = publish_to_file(state, tmp_path / "sub" / default_filename(state))
    assert out.exists()
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == 2


def test_default_filename_is_versioned_and_tenant_scoped():
    state = _sample_state(tenant_id=42)
    name = default_filename(state)
    assert "v2" in name
    assert "42" in name
    assert "daily" in name
