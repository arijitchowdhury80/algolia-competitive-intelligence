#!/usr/bin/env python3
"""Build a deterministic Agent Studio Market Field dashboard fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.dashboard.cockpit_renderer import render_cockpit_html
from cios.dashboard.publisher import publish_to_file
from cios.dashboard.types import (
    ArgusRecommendationSummary,
    DemandSignalSummary,
    FeatureMatrixRow,
    ProductMarketPatternSummary,
)
from cios.dashboard.state_builder import DashboardStateBuilder


def build_agent_studio_state():
    pattern = ProductMarketPatternSummary(
        pattern_id=31,
        pattern_type="own_narrative_gap",
        capability_text="Agent Studio",
        summary=(
            "Agent Studio has shipped product proof, competitor AI-search conversation, "
            "and Audience Demand, but Algolia's market narrative is lagging."
        ),
        involved_companies=["Algolia", "Google Vertex AI Search"],
        confidence=0.78,
        evidence_refs=[
            {"source_url": "https://www.algolia.com/products/agent-studio"},
            {"source_url": "https://cloud.google.com/enterprise-search"},
        ],
    )
    recommendation = ArgusRecommendationSummary(
        recommendation_id=52,
        pattern_observation_id=31,
        owner="Product Marketing",
        action="Turn Agent Studio into an evidence-backed market narrative.",
        why_now="The demand window is cooling while competitor AI-search framing accelerates.",
        urgency="P1",
        confidence=0.74,
        evidence_refs=[
            {"source_url": "https://www.algolia.com/products/agent-studio"},
            {"source_url": "looker://algolia/ga4/agent-studio"},
        ],
    )
    demand = DemandSignalSummary(
        demand_signal_id=71,
        topic="Agent Studio",
        metric="engaged_sessions",
        value=480,
        change_pct=0.27,
        source_label="Looker Studio GA4 export",
        evidence_refs=[{"source_url": "looker://algolia/ga4/agent-studio"}],
    )
    feature_rows = [
        FeatureMatrixRow(
            company_name="Algolia",
            company_role="own",
            capability_text="Agent Studio",
            position_status="proven",
            summary="Algolia has shipped Agent Studio product proof.",
            confidence=0.84,
            evidence_refs=[{"source_url": "https://www.algolia.com/products/agent-studio"}],
        ),
        FeatureMatrixRow(
            company_name="Google Vertex AI Search",
            company_role="competitor",
            capability_text="Agent Studio",
            position_status="unknown",
            summary="Competitor positioning is visible, but exact Agent Studio parity is unresolved.",
            confidence=0.35,
            evidence_refs=[{"source_url": "https://cloud.google.com/enterprise-search"}],
        ),
    ]
    market_field = DashboardStateBuilder._build_market_field_state(
        patterns=[pattern],
        recommendations=[recommendation],
        demand_signals=[demand],
        feature_matrix=feature_rows,
    )
    from cios.dashboard.types import DashboardState

    return DashboardState(
        tenant_id=1,
        cadence="daily",
        market_field=market_field,
        product_market_patterns=[pattern],
        argus_recommendations=[recommendation],
        demand_signals=[demand],
        feature_matrix=feature_rows,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    state = build_agent_studio_state()
    html_path = args.out_dir / "argus-dashboard.html"
    json_path = args.out_dir / "argus-dashboard.json"
    manifest_path = args.out_dir / "agent-studio-market-field-fixture-manifest.json"
    html_path.write_text(render_cockpit_html(state), encoding="utf-8")
    publish_to_file(state, json_path)
    manifest = {
        "status": "built",
        "html": html_path.name,
        "json": json_path.name,
        "selected_hotspot": state.market_field.selected_hotspot.label if state.market_field.selected_hotspot else None,
        "node_types": sorted({node.node_type for node in state.market_field.nodes}),
        "proof_planes": sorted({item.plane for item in state.market_field.proof}),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
