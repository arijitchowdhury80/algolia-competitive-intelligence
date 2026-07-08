#!/usr/bin/env python3
"""CLI: render a dashboard-state.v2.*.json file into a local HTML preview.

Usage:
    python3 scripts/render_dashboard_preview.py <state.json> [output.html]

This is a LOCAL PREVIEW tool only. It does not deploy or publish anywhere --
it writes an HTML file to disk so Arijit can open it in a browser before any
decision to deploy to ci.chowmes.com or elsewhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cios.dashboard.html_renderer import render_dashboard_html  # noqa: E402
from cios.dashboard.types import DashboardState  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_json", type=Path, help="Path to a dashboard-state.v2.*.json file")
    parser.add_argument(
        "output_html",
        type=Path,
        nargs="?",
        default=None,
        help="Output HTML path (default: <state_json stem>.preview.html next to the input)",
    )
    args = parser.parse_args()

    if not args.state_json.exists():
        parser.error(f"state JSON not found: {args.state_json}")

    payload = json.loads(args.state_json.read_text(encoding="utf-8"))
    payload.pop("schema_version", None)
    payload.pop("is_quiet", None)
    payload.pop("top_attention_level", None)
    state = DashboardState.model_validate(payload)

    html_out = render_dashboard_html(state)

    output_path = args.output_html or args.state_json.with_suffix(".preview.html")
    output_path.write_text(html_out, encoding="utf-8")

    print(f"Rendered preview written to: {output_path}")
    print("This is a LOCAL PREVIEW only -- nothing was deployed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
