"""Serializes DashboardState to the JSON shape a dashboard UI consumes.

UI-CONTRACT UNKNOWN -- READ BEFORE WIRING TO THE LIVE UI
=========================================================
The existing dashboard UI Arijit built (live at ci.chowmes.com, source on the
VPS at /opt/data/apps/algolia-competitive-intelligence/apps/dashboard/) is not
available in this repo or workspace: docs/workspace/v0-reference/ has the V0
*collector* scripts (daily-research-run.py, ci_core.py, weekly-review.py), not
the dashboard app's frontend loader or its expected JSON field names. The
docs/planning UX spec describes screens and data elements, not a wire format.

Consequences of that gap, made explicit rather than silently guessed:
  1. This module does NOT reverse-engineer or guess the V0/existing UI's
     field names. Emitting a hand-waved "looks about right" shape and calling
     it compatible would be worse than an honest unknown -- it would silently
     break the live UI on first load.
  2. Instead, publish() emits a clean, versioned, self-describing contract:
     dashboard-state.v{DASHBOARD_STATE_SCHEMA_VERSION}.json. This is the
     payload cios.dashboard now guarantees.
  3. ADAPTER POINT (the actual unknown, name it don't hide it): before this
     wires into the live ci.chowmes.com UI, someone with access to
     apps/dashboard/'s data-loading code must either (a) confirm the existing
     loader can be repointed at this versioned JSON directly, or (b) write a small
     adapter in the dashboard app itself that maps
     dashboard-state.v{DASHBOARD_STATE_SCHEMA_VERSION}.json -> whatever internal shape its components
     already expect. That adapter does not belong in cios (the backend
     should not encode a specific frontend's internal prop names) -- it
     belongs in apps/dashboard/, reading FROM this file's output.
  4. Until that adapter exists, `dashboard_state.json_path` (schema.sql) can
     point at this file's output, but the live UI will keep rendering
     whatever it currently reads (do not assume this alone flips the site
     over).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import DASHBOARD_STATE_SCHEMA_VERSION, DashboardState


_REDACTED = object()
_LOCAL_PATH_PREFIXES = ("/root/", "/tmp/", "/Users/", "/app/")


def _is_local_artifact_path(value: str) -> bool:
    return value.startswith(_LOCAL_PATH_PREFIXES)


def _redact_local_artifact_paths(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            public_value = _redact_local_artifact_paths(item)
            if public_value is _REDACTED:
                continue
            redacted[key] = public_value
        return redacted
    if isinstance(value, list):
        public_items = []
        for item in value:
            public_value = _redact_local_artifact_paths(item)
            if public_value is _REDACTED:
                continue
            public_items.append(public_value)
        return public_items
    if isinstance(value, str) and _is_local_artifact_path(value):
        return _REDACTED
    return value


def to_json_dict(state: DashboardState) -> dict[str, Any]:
    """Stable, versioned JSON-serializable dict for one DashboardState.

    Stability contract for tests/consumers: key order follows model field
    declaration order (pydantic v2 preserves it) and is not alphabetized or
    otherwise reshuffled between calls for the same input.
    """
    payload = state.model_dump(mode="json")
    public_payload = {
        "schema_version": DASHBOARD_STATE_SCHEMA_VERSION,
        "is_quiet": state.is_quiet,
        "top_attention_level": state.top_attention_level.value,
        **payload,
    }
    return _redact_local_artifact_paths(public_payload)


def to_json_str(state: DashboardState, *, indent: int = 2) -> str:
    return json.dumps(to_json_dict(state), indent=indent, sort_keys=False)


def publish_to_file(state: DashboardState, path: str | Path) -> Path:
    """Writes dashboard-state.v{N}.json to disk and returns the path written.
    Caller is responsible for persisting `path` into dashboard_state.json_path."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(to_json_str(state), encoding="utf-8")
    return out_path


def default_filename(state: DashboardState) -> str:
    return f"dashboard-state.v{DASHBOARD_STATE_SCHEMA_VERSION}.{state.tenant_id}.{state.cadence}.json"
