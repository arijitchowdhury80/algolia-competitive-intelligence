#!/usr/bin/env python3
"""Validate that a rendered CI-OS dashboard exposes a real Market Field story."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_NODE_TYPES = [
    "product_reality",
    "market_conversation",
    "audience_demand",
    "argus_action",
    "unknown_boundary",
]
REQUIRED_EDGE_TYPES = [
    "supports_story",
    "requires_action",
    "limits_confidence",
]
REQUIRED_PROOF_PLANES = [
    "product_reality",
    "market_conversation",
    "audience_demand",
    "argus_recommendation",
]


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _labels(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("label") or "") for item in items]


def validate_story_payload(payload: dict[str, Any], *, expected_hotspot: str = "Agent Studio") -> dict[str, Any]:
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    hotspots = payload.get("hotspots") if isinstance(payload.get("hotspots"), list) else []
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    proof = payload.get("proof") if isinstance(payload.get("proof"), list) else []

    selected_id = payload.get("selected_hotspot_id")
    selected_hotspot = next((item for item in hotspots if item.get("hotspot_id") == selected_id), None)
    selected_hotspot = selected_hotspot or (hotspots[0] if hotspots else None)
    _assert(selected_hotspot is not None, "Market Field has no selected hotspot")
    _assert(
        str(selected_hotspot.get("label") or "") == expected_hotspot,
        f"selected hotspot is not {expected_hotspot}: {_labels(hotspots)}",
    )
    _assert(str(selected_hotspot.get("argus_read") or "").strip(), "selected hotspot missing Argus read")
    _assert(selected_hotspot.get("unknowns"), "selected hotspot missing confidence boundaries")

    node_types = {str(node.get("node_type") or "") for node in nodes}
    edge_types = {str(edge.get("edge_type") or "") for edge in edges}
    proof_planes = {str(item.get("plane") or "") for item in proof}
    for node_type in REQUIRED_NODE_TYPES:
        _assert(node_type in node_types, f"Market Field story missing node type: {node_type}")
    for edge_type in REQUIRED_EDGE_TYPES:
        _assert(edge_type in edge_types, f"Market Field story missing edge type: {edge_type}")
    for plane in REQUIRED_PROOF_PLANES:
        _assert(plane in proof_planes, f"Market Field story missing proof plane: {plane}")

    _assert(actions, "Market Field story missing named-team action")
    owners = {str(action.get("owner") or "") for action in actions}
    _assert("Product Marketing" in owners, f"Market Field story missing Product Marketing owner: {sorted(owners)}")
    _assert(
        any("Agent Studio" in str(action.get("action") or "") for action in actions),
        "Market Field story missing Agent Studio action",
    )

    return {
        "status": "passed",
        "selected_hotspot": str(selected_hotspot.get("label") or ""),
        "required_node_types": REQUIRED_NODE_TYPES,
        "required_edge_types": REQUIRED_EDGE_TYPES,
        "required_proof_planes": REQUIRED_PROOF_PLANES,
        "action_owners": sorted(owners),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "proof_count": len(proof),
    }


def _playwright_sync_api():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is required. Install with: python -m pip install -e '.[e2e]' && python -m playwright install chromium"
        ) from exc
    return sync_playwright


def validate_browser_story(url: str, *, expected_hotspot: str = "Agent Studio") -> dict[str, Any]:
    sync_playwright = _playwright_sync_api()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(250)
        _assert(page.locator("#market-field-3d").count() == 1, "3D Market Field canvas missing")
        _assert(page.locator("#market-field-state").count() == 1, "Market Field state payload missing")
        payload = json.loads(page.locator("#market-field-state").text_content() or "{}")
        story = validate_story_payload(payload, expected_hotspot=expected_hotspot)
        canvas_nonblank = page.locator("#market-field-3d").evaluate(
            """canvas => {
                const ctx = canvas.getContext('2d');
                if (!ctx || canvas.width < 2 || canvas.height < 2) return false;
                const data = ctx.getImageData(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 24, 24).data;
                for (let index = 0; index < data.length; index += 4) {
                    if (data[index] || data[index + 1] || data[index + 2] || data[index + 3]) return true;
                }
                return false;
            }"""
        )
        _assert(canvas_nonblank, "3D Market Field canvas pixel probe is blank")
        _assert(not errors, f"browser console errors: {errors}")
        browser.close()
    return {**story, "url": url, "canvas_nonblank": True, "console_errors": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Dashboard URL or file:// URL to validate.")
    parser.add_argument("--expected-hotspot", default="Agent Studio")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence output path.")
    args = parser.parse_args(argv)

    try:
        result = validate_browser_story(args.url, expected_hotspot=args.expected_hotspot)
    except Exception as exc:  # noqa: BLE001 - CLI must return a readable gate failure.
        print(f"FAIL market_field_story_validation: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS market_field_story_validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
