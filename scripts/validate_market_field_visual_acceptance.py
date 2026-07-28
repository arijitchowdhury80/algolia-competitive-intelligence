#!/usr/bin/env python3
"""Validate the Phase 6 Market Field visual acceptance surface.

This verifier is deliberately stricter than the story-payload validator but it
does not declare final Phase 6 visual acceptance while the UI/UX design
authority is missing or unwaived. A passing run means the rendered dashboard is
usable enough to inspect: the 3D field is nonblank, the core story is visible,
click-to-reveal controls work, and critical controls do not clip across the
required viewports.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_VIEWPORTS = (
    ("mobile", 390, 844),
    ("tablet", 768, 1024),
    ("desktop", 1280, 900),
)

REQUIRED_TERMS = (
    "Agent Studio",
    "Product reality",
    "Market conversation",
    "Audience Demand",
    "Product Marketing",
    "Confidence boundaries",
)

CRITICAL_SELECTORS = (
    "#market-field",
    "#market-field-3d",
    "[data-selected-hotspot-title]",
    "[data-selected-hotspot-read]",
    "#action-layer",
    "[data-market-action]",
    "[data-proof-drawer-toggle]",
    "#evidence-lab",
    "#admin",
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_visual_acceptance_result(
    *,
    url: str,
    expected_hotspot: str,
    viewport_results: list[dict[str, Any]],
    console_errors: list[str],
    design_authority_status: str,
) -> dict[str, Any]:
    _assert(viewport_results, "no viewport results were recorded")
    _assert(not console_errors, f"browser console errors: {console_errors}")
    for result in viewport_results:
        label = str(result.get("viewport") or "unknown")
        _assert(result.get("canvas_nonblank") is True, f"{label} canvas is blank")
        _assert(
            result.get("selected_hotspot") == expected_hotspot,
            f"{label} selected hotspot is not {expected_hotspot}",
        )
        clipped = result.get("clipped_selectors") or []
        _assert(not clipped, f"{label} has clipped critical selectors: {clipped}")
        visible_terms = set(result.get("visible_terms") or [])
        missing = [term for term in REQUIRED_TERMS if term not in visible_terms]
        _assert(not missing, f"{label} is missing visible story terms: {missing}")

    final_visual_acceptance = design_authority_status == "approved"
    return {
        "status": "passed" if final_visual_acceptance else "passed_with_design_authority_gap",
        "url": url,
        "expected_hotspot": expected_hotspot,
        "design_authority_status": design_authority_status,
        "final_visual_acceptance": final_visual_acceptance,
        "viewport_count": len(viewport_results),
        "viewports": viewport_results,
        "console_errors": console_errors,
    }


def _playwright_sync_api():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is required. Install with: python -m pip install -e '.[e2e]' && python -m playwright install chromium"
        ) from exc
    return sync_playwright


def _canvas_nonblank(page) -> bool:
    return bool(
        page.locator("#market-field-3d").evaluate(
            """canvas => {
                const ctx = canvas.getContext('2d');
                if (!ctx || canvas.width < 2 || canvas.height < 2) return false;
                const points = [
                  [0.25, 0.25], [0.50, 0.50], [0.75, 0.75],
                  [0.25, 0.75], [0.75, 0.25], [0.50, 0.25], [0.50, 0.75]
                ];
                for (const [x, y] of points) {
                  const left = Math.max(0, Math.floor(canvas.width * x) - 8);
                  const top = Math.max(0, Math.floor(canvas.height * y) - 8);
                  const data = ctx.getImageData(left, top, 16, 16).data;
                  for (let index = 0; index < data.length; index += 4) {
                    if (data[index] || data[index + 1] || data[index + 2] || data[index + 3]) return true;
                  }
                }
                return false;
            }"""
        )
    )


def _visible_terms(page) -> list[str]:
    body_text = page.locator("body").inner_text(timeout=5000)
    return [term for term in REQUIRED_TERMS if term in body_text]


def _clipped_selectors(page, *, width: int, height: int) -> list[str]:
    clipped: list[str] = []
    for selector in CRITICAL_SELECTORS:
        locator = page.locator(selector).first
        if locator.count() == 0:
            clipped.append(f"{selector}:missing")
            continue
        if not locator.is_visible():
            clipped.append(f"{selector}:hidden")
            continue
        locator.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(50)
        box = locator.bounding_box()
        if not box:
            clipped.append(f"{selector}:no_box")
            continue
        if box["width"] <= 1 or box["height"] <= 1:
            clipped.append(f"{selector}:zero_size")
            continue
        if box["x"] < -2 or box["x"] + box["width"] > width + 2:
            clipped.append(f"{selector}:horizontal")
            continue
        if box["y"] + box["height"] < 1 or box["y"] > height - 1:
            clipped.append(f"{selector}:vertical")
    return clipped


def _validate_viewport(page, *, label: str, width: int, height: int, expected_hotspot: str) -> dict[str, Any]:
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_timeout(250)

    for selector in ("#market-field", "#market-field-3d", "#market-field-state", "[data-market-hotspot]"):
        _assert(page.locator(selector).count() >= 1, f"{label} missing {selector}")

    field_before_evidence = page.locator("#market-field").evaluate(
        """el => {
            const evidence = document.querySelector('#evidence-coverage');
            return evidence ? Boolean(el.compareDocumentPosition(evidence) & Node.DOCUMENT_POSITION_FOLLOWING) : true;
        }"""
    )
    _assert(field_before_evidence, f"{label} Market Field is not before raw evidence")

    hotspot = page.locator(f'[data-hotspot-label="{expected_hotspot}"]').first
    _assert(hotspot.count() == 1, f"{label} missing expected hotspot {expected_hotspot}")
    hotspot.click()
    page.wait_for_timeout(200)
    _assert(hotspot.get_attribute("aria-pressed") == "true", f"{label} hotspot did not become selected")

    time_button = page.locator('[data-time-window="30d"]')
    _assert(time_button.count() == 1, f"{label} missing 30D time control")
    time_button.click()
    page.wait_for_timeout(150)
    _assert(
        page.locator("#market-field").get_attribute("data-selected-time-window") == "30d",
        f"{label} 30D time control did not update field state",
    )

    proof_button = page.locator("[data-proof-drawer-toggle]")
    proof_button.click()
    page.wait_for_timeout(150)
    _assert(proof_button.get_attribute("aria-expanded") == "true", f"{label} proof drawer did not open")
    _assert(page.locator("[data-proof-drawer-panel]").is_visible(), f"{label} proof drawer panel is hidden")

    selected_hotspot = page.locator("[data-selected-hotspot-title]").inner_text(timeout=5000).strip()
    _assert(selected_hotspot == expected_hotspot, f"{label} selected title is {selected_hotspot}")

    return {
        "viewport": label,
        "width": width,
        "height": height,
        "canvas_nonblank": _canvas_nonblank(page),
        "selected_hotspot": selected_hotspot,
        "visible_terms": _visible_terms(page),
        "clipped_selectors": _clipped_selectors(page, width=width, height=height),
    }


def validate_browser_visual_acceptance(
    url: str,
    *,
    expected_hotspot: str = "Agent Studio",
    design_authority_status: str = "missing_or_unwaived",
) -> dict[str, Any]:
    sync_playwright = _playwright_sync_api()
    console_errors: list[str] = []
    viewport_results: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(ignore_https_errors=True)
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        for label, width, height in DEFAULT_VIEWPORTS:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            viewport_results.append(
                _validate_viewport(page, label=label, width=width, height=height, expected_hotspot=expected_hotspot)
            )
        browser.close()
    return build_visual_acceptance_result(
        url=url,
        expected_hotspot=expected_hotspot,
        viewport_results=viewport_results,
        console_errors=console_errors,
        design_authority_status=design_authority_status,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Dashboard URL or file:// URL to validate.")
    parser.add_argument("--expected-hotspot", default="Agent Studio")
    parser.add_argument("--design-authority-status", default="missing_or_unwaived")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence output path.")
    args = parser.parse_args(argv)

    try:
        result = validate_browser_visual_acceptance(
            args.url,
            expected_hotspot=args.expected_hotspot,
            design_authority_status=args.design_authority_status,
        )
    except Exception as exc:  # noqa: BLE001 - CLI must return a readable gate failure.
        print(f"FAIL market_field_visual_acceptance: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS market_field_visual_acceptance: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
