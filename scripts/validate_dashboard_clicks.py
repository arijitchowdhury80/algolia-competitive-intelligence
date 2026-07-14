#!/usr/bin/env python3
"""Playwright validation for the rebuilt CI-OS public dashboard UI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

if TYPE_CHECKING:
    from playwright.sync_api import Page


@dataclass
class CheckResult:
    name: str
    detail: str


def build_verdict(
    *,
    run_id: str,
    results: list[CheckResult],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the authoritative run-bound click-validation verdict."""
    return {
        "schema_version": 1,
        "gate": "dashboard_click_validation",
        "run_id": run_id,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass",
        "exit_code": 0,
        "checks": {result.name: True for result in results},
    }


def _playwright_sync_api() -> tuple[Any, type[Exception]]:
    try:
        from playwright.sync_api import Error, sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised through CLI preflight.
        raise RuntimeError(_dependency_help(["Python package `playwright` is not installed."])) from exc
    return sync_playwright, Error


def dependency_errors() -> list[str]:
    errors: list[str] = []
    if importlib.util.find_spec("playwright") is None:
        errors.append("Python package `playwright` is not installed.")
        return errors
    try:
        sync_playwright, playwright_error = _playwright_sync_api()
        with sync_playwright() as p:
            chromium_path = p.chromium.executable_path
        if not chromium_path or not Path(chromium_path).exists():
            errors.append("Playwright Chromium browser is not installed.")
    except Exception as exc:  # noqa: BLE001 - preflight must report dependency failures, not crash.
        errors.append(f"Playwright dependency check failed: {exc.__class__.__name__}: {exc}")
    return errors


def _dependency_help(errors: list[str]) -> str:
    bullet_lines = "\n".join(f"- {error}" for error in errors)
    return (
        "dashboard click validation dependencies missing\n"
        f"{bullet_lines}\n"
        "Install with:\n"
        "  python -m pip install -e '.[e2e]'\n"
        "  python -m playwright install chromium"
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _text(locator) -> str:
    return " ".join(locator.inner_text(timeout=5000).split())


def _status_ok(page: Page, url: str) -> None:
    response = page.request.get(url, timeout=20000)
    _assert(200 <= response.status < 400, f"{url} returned HTTP {response.status}")


def validate_structure(page: Page) -> CheckResult:
    for selector in (
        "#today-read",
        "#intelligence-spine",
        "#market-timeline",
        "#semantic-layer",
        "#priority-moves",
        "#selected-competitor",
        "#role-implications",
        "#evidence-coverage",
    ):
        _assert(page.locator(selector).count() == 1, f"{selector} missing")
    _assert(page.locator(".argus-mark").count() == 1, "Argus logo mark missing")
    _assert(page.locator(".editorial-image").count() == 1, "Argus editorial image missing")
    today = page.locator("#today-read").evaluate("el => el.compareDocumentPosition(document.querySelector('#priority-moves'))")
    _assert(today & 4, "today read does not precede priority moves")
    return CheckResult("structure", "Read, timeline, semantic layer, priority moves, selected competitor, role implications, evidence sections, and Argus assets present")


def validate_nav_targets(page: Page) -> CheckResult:
    expected = {
        "Today": "today-read",
        "Proof": "intelligence-spine",
        "Timeline": "market-timeline",
        "Patterns": "semantic-layer",
        "Priority moves": "priority-moves",
        "Role implications": "role-implications",
        "Evidence": "evidence-coverage",
    }
    scrolls: dict[str, int] = {}
    for label, target_id in expected.items():
        link = page.locator(f'.brief-nav a[data-nav-link="{target_id}"]')
        _assert(link.count() == 1, f"{label} nav link missing explicit target")
        link.click()
        page.wait_for_timeout(250)
        _assert(page.evaluate("location.hash") == f"#{target_id}", f"{label} nav did not update hash")
        _assert(link.get_attribute("aria-current") == "page", f"{label} nav did not become current")
        top = page.locator(f"#{target_id}").evaluate("el => Math.round(el.getBoundingClientRect().top)")
        _assert(top >= -20 and top <= 170, f"{label} target is not in the reading position: top={top}")
        scrolls[label] = page.evaluate("Math.round(scrollY)")
    _assert(scrolls["Timeline"] != scrolls["Patterns"], "Timeline and Patterns nav land at the same scroll position")
    _assert(scrolls["Role implications"] != scrolls["Evidence"], "Role and Evidence nav land at the same scroll position")
    _assert(page.locator("#evidence-coverage details[open]").count() == 2, "Evidence nav target is still collapsed")
    return CheckResult("nav_targets", "Top nav updates hash/current state and lands on distinct sections")


def validate_timeline(page: Page) -> CheckResult:
    timeline = page.locator("#market-timeline")
    _assert(timeline.count() == 1, "market timeline missing")
    _assert(page.locator("#history-calendar").count() == 1, "history calendar missing")
    _assert(page.locator("#history-selector").count() == 1, "history selector missing")
    text = _text(timeline)
    text_lower = text.lower()
    for phrase in ("Holistic daily coverage", "Why this priority", "Last 7 days", "Last 30 days"):
        _assert(phrase.lower() in text_lower, f"timeline missing {phrase}")
    coverage_rows = timeline.locator(".coverage-row")
    _assert(coverage_rows.count() >= 5, f"expected broad holistic coverage, found {coverage_rows.count()} rows")
    return CheckResult("timeline", "History controls, holistic coverage, and priority rationale are visible")


def validate_semantic_layer(page: Page) -> CheckResult:
    semantic = page.locator("#semantic-layer")
    _assert(semantic.count() == 1, "semantic layer missing")
    selector = page.locator("#partner-selector")
    _assert(selector.count() == 1, "partner selector missing")
    option_count = selector.locator("option").count()
    _assert(option_count >= 10, f"expected broad partner selector, found {option_count} options")
    _assert(semantic.locator("[data-heat-map]").count() == 1, "semantic heat map missing")
    _assert(semantic.locator("[data-heat-cell]").count() > 0, "semantic heat cells missing")
    text = _text(semantic)
    for phrase in ("Pattern across partners", "Where the market is heading", "Argus recommendation", "Confidence rubric"):
        _assert(phrase in text, f"semantic layer missing {phrase}")
    _validate_confidence_rubric_text(text)
    option_values = selector.locator("option").evaluate_all(
        """options => options.map((option) => ({value: option.value, label: option.textContent.trim()}))"""
    )
    quiet = next((option for option in option_values if option["label"] not in {"Constructor", "Elastic", "Algonomy"}), None)
    target = quiet or option_values[-1]
    selector.select_option(target["value"])
    page.wait_for_timeout(150)
    _assert(page.evaluate("location.hash") == f"#competitor-{target['value']}", "partner selector did not update competitor hash")
    panel = page.locator(f'[data-competitor-panel="{target["value"]}"]')
    _assert(panel.count() == 1 and panel.is_visible(), "partner selector did not show selected competitor panel")
    _assert(target["label"] in _text(panel), "selected competitor panel does not match partner selector")
    return CheckResult("semantic_layer", f"Selector, heat map, recommendation, and confidence rubric validated with {target['label']}")


def _validate_confidence_rubric_text(text: str) -> None:
    if "Not scored" in text:
        _assert(
            "No backend recommendation scorecard exists" in text,
            "semantic layer missing backend scorecard blocker",
        )
        return
    backend_dimensions = (
        "Product reality",
        "Market conversation",
        "Audience demand",
        "Own response gap",
        "Evidence breadth",
    )
    _assert(
        any(dimension in text for dimension in backend_dimensions),
        "semantic confidence rubric must come from a backend scorecard or explicitly render Not scored",
    )


def validate_priority_selection(page: Page) -> CheckResult:
    buttons = page.locator("[data-select-competitor]")
    count = buttons.count()
    if count == 0:
        text = _text(page.locator("body"))
        _assert("No new material moves were promoted today." in text, "no priority moves and no quiet-run explanation")
        _assert("Act on the top signal" not in text, "quiet run still shows current-action label")
        return CheckResult(
            "priority_selection",
            "Quiet current run has no priority buttons and shows the no-new-material-moves state",
        )
    target = page.locator('[data-select-competitor][data-competitor-name="Elastic"]')
    if target.count() == 0:
        target = buttons.nth(0)
    name = target.get_attribute("data-competitor-name") or "selected competitor"
    cid = target.get_attribute("data-select-competitor") or ""
    target.click()
    _assert("is-active" in (target.get_attribute("class") or ""), "selected priority move did not become active")
    label = _text(page.locator("#active-focus-label"))
    _assert(name in label, "focus label did not name selected competitor")
    panel = page.locator(f'[data-competitor-panel="{cid}"]')
    _assert(panel.count() == 1 and panel.is_visible(), "selected competitor panel did not show")
    _assert(name in _text(panel), "selected competitor panel does not match selected move")
    role_set = page.locator(f'[data-role-set="{cid}"]')
    _assert(role_set.count() == 1 and role_set.is_visible(), "role implications did not update to selected competitor")
    _assert(name in _text(role_set), "role implications do not name selected competitor")
    return CheckResult("priority_selection", f"{name} selection updates selected panel and role implications")


def validate_brief_routing(page: Page, base_url: str) -> CheckResult:
    checked: list[str] = []
    for name in ("Constructor", "Elastic", "Algonomy"):
        button = page.locator(f'[data-select-competitor][data-competitor-name="{name}"]')
        if button.count() > 0:
            cid = button.get_attribute("data-select-competitor") or ""
            button.click()
        else:
            option = page.locator("#partner-selector option").filter(has_text=name)
            if option.count() == 0:
                continue
            cid = option.first.get_attribute("value") or ""
            page.locator("#partner-selector").select_option(cid)
            page.wait_for_timeout(150)
        panel = page.locator(f'[data-competitor-panel="{cid}"]')
        link = panel.locator('a.open-brief[href*="/briefs/"], a.open-brief[href^="./briefs/"]').first
        _assert(link.count() == 1, f"{name} selected panel has no competitor brief link")
        href = link.get_attribute("href") or ""
        _assert(name.lower().split()[0].replace("/", "") in href.lower(), f"{name} href looks wrong: {href}")
        url = urljoin(base_url, href)
        _status_ok(page, url)
        html = page.request.get(url, timeout=20000).text()
        _assert(name in html, f"{name} brief does not contain its own name")
        checked.append(name)
    _assert(checked, "no competitor-specific brief routes checked")
    return CheckResult("brief_routing", "Checked " + ", ".join(checked))


def validate_appendices(page: Page, base_url: str) -> CheckResult:
    coverage = page.locator("details.appendix").filter(has_text="Market coverage")
    evidence = page.locator("details.appendix").filter(has_text="Evidence and source health")
    _assert(coverage.count() == 1, "market coverage appendix missing")
    _assert(evidence.count() == 1, "evidence appendix missing")
    if not coverage.evaluate("el => el.open"):
        coverage.locator(":scope > summary").click()
    if not evidence.evaluate("el => el.open"):
        evidence.locator(":scope > summary").click()
    coverage_text = _text(coverage).lower()
    evidence_text = _text(evidence).lower()
    _assert("active sources" in coverage_text, "coverage appendix missing source counts")
    _assert("fetch_error" in evidence_text or "http_error" in evidence_text or "timeout" in evidence_text, "evidence appendix missing failed source")
    links = coverage.locator('a[href*="/briefs/"], a[href^="./briefs/"]')
    _assert(links.count() >= 10, f"expected broad competitor brief links, found {links.count()}")
    for index in range(min(links.count(), 8)):
        _status_ok(page, urljoin(base_url, links.nth(index).get_attribute("href") or ""))
    return CheckResult("appendices", "Coverage and evidence appendices open and expose brief/source details")


def validate_responsive(base_url: str, viewports: list[tuple[int, int]]) -> list[CheckResult]:
    results: list[CheckResult] = []
    sync_playwright, _ = _playwright_sync_api()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width, height in viewports:
            page = browser.new_page(viewport={"width": width, "height": height}, ignore_https_errors=True)
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            _assert(page.locator("#today-read").count() == 1, f"today read missing at {width}px")
            _assert(page.locator("#intelligence-spine").count() == 1, f"intelligence spine missing at {width}px")
            _assert(page.locator("#market-timeline").count() == 1, f"market timeline missing at {width}px")
            _assert(page.locator("#semantic-layer").count() == 1, f"semantic layer missing at {width}px")
            _assert(page.locator("#partner-selector").count() == 1, f"partner selector missing at {width}px")
            has_priority = page.locator("[data-select-competitor]").count() > 0
            text = _text(page.locator("body"))
            has_quiet_state = "No new material moves were promoted today." in text
            _assert(has_priority or has_quiet_state, f"priority moves or quiet state missing at {width}px")
            _assert(page.locator("#role-implications").count() == 1, f"role implications missing at {width}px")
            _assert(not errors, f"page errors at {width}px: {errors}")
            results.append(CheckResult(f"viewport_{width}", f"{width}x{height} loaded rebuilt dashboard"))
            page.close()
        browser.close()
    return results


def _run_validation(base_url: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    sync_playwright, _ = _playwright_sync_api()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        _assert("Argus Competitive Intelligence Cockpit" in page.title(), "unexpected page title")
        results.append(validate_structure(page))
        results.append(validate_nav_targets(page))
        results.append(validate_timeline(page))
        results.append(validate_semantic_layer(page))
        results.append(validate_priority_selection(page))
        results.append(validate_brief_routing(page, base_url))
        results.append(validate_appendices(page, base_url))
        browser.close()
    results.extend(validate_responsive(base_url, [(390, 844), (768, 1024), (1280, 900)]))
    return results


def _write_failure_verdict(output: Path, *, run_id: str, check: str) -> None:
    payload = {
        "schema_version": 1,
        "gate": "dashboard_click_validation",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "fail",
        "exit_code": 2,
        "checks": {check: False},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://ci.chowmes.com/")
    parser.add_argument("--tenant", help=argparse.SUPPRESS)
    parser.add_argument("--check-dependencies", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.output and not args.run_id:
        parser.error("--run-id is required with --output")
    errors = dependency_errors()
    if args.check_dependencies:
        if errors:
            print(_dependency_help(errors), file=sys.stderr)
            return 2
        print("PASS dashboard_click_dependencies")
        return 0
    if errors:
        if args.output:
            _write_failure_verdict(args.output, run_id=args.run_id, check="dependencies")
        print(_dependency_help(errors), file=sys.stderr)
        return 2

    base_url = args.url if args.url.endswith("/") else args.url + "/"
    try:
        results = _run_validation(base_url)
    except Exception as exc:  # noqa: BLE001 - emit a terminal structured verdict.
        if args.output:
            _write_failure_verdict(args.output, run_id=args.run_id, check="dashboard_clicks")
        print(f"dashboard click validation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    for result in results:
        print(f"PASS {result.name}: {result.detail}")
    print("PASS dashboard_click_validation")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{json.dumps(build_verdict(run_id=args.run_id, results=results), indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
