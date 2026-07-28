#!/usr/bin/env python3
"""Run Scout against one product surface and write Argus-ready product rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.intelligence.scout_surface_exporter import (  # noqa: E402
    ProductSurfaceTarget,
    scout_extract_response_to_product_records,
)
from cios.brain.quality import extract_json_object  # noqa: E402
from cios.platform.models.providers.google import GoogleGeminiProvider  # noqa: E402
from cios.platform.models.types import ModelRequest  # noqa: E402


def product_change_schema() -> dict:
    """Schema Scout should use when extracting product-reality changes."""

    return {
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "capability": {"type": "string"},
                        "change_type": {
                            "type": "string",
                            "enum": [
                                "release",
                                "docs_update",
                                "pricing_change",
                                "integration",
                                "deprecation",
                            ],
                        },
                        "summary": {"type": "string"},
                        "excerpt": {"type": "string"},
                    },
                    "required": ["capability", "change_type", "summary"],
                },
            }
        },
        "required": ["changes"],
    }


def build_instruction(target: ProductSurfaceTarget, *, focus_capability: str | None = None) -> str:
    focus = _focus_instruction(focus_capability)
    return (
        f"Extract product reality proof for {target.company_name} from this "
        f"{target.surface_family} page. For changelog, release notes, and GitHub release "
        "pages, release entries, improvements, bug fixes, deprecations, and documented "
        "behavior changes count as product reality. For static product, docs, pricing, "
        "or integration pages, current documented capabilities, pricing/package changes, "
        "API behavior, and integration proof count as product reality even if they are "
        f"not phrased as a new launch. {focus}Return up to 12 concrete rows. Ignore generic "
        "marketing claims unless the page ties them to product documentation, release "
        "proof, pricing, integration, API, or changelog evidence."
    )


def _focus_instruction(focus_capability: str | None) -> str:
    focus = " ".join(str(focus_capability or "").split())
    if not focus:
        return ""
    return (
        f"Focus first on product proof for {focus}. If the page has no proof for {focus}, "
        "return other concrete product proof from the page and do not fabricate a match. "
    )


def build_scout_extract_command(
    target: ProductSurfaceTarget,
    *,
    scout_bin: str,
    provider: str,
    use_js: bool,
    focus_capability: str | None = None,
) -> list[str]:
    command = [
        scout_bin,
        "extract",
        target.url,
        "--schema",
        json.dumps(product_change_schema(), sort_keys=True),
        "--instruction",
        build_instruction(target, focus_capability=focus_capability),
        "--provider",
        provider,
    ]
    if use_js:
        command.append("--js")
    return command


def build_scout_scrape_command(
    target: ProductSurfaceTarget,
    *,
    scout_bin: str,
    use_js: bool,
) -> list[str]:
    command = [
        scout_bin,
        "scrape",
        target.url,
    ]
    if use_js:
        command.append("--js")
    return command


def _run_command(command: list[str], timeout_seconds: float) -> dict:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Scout product surface extraction timed out after {exc.timeout:g}s") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"Scout product surface extraction failed: {stderr}")
    try:
        return dict(json.loads(completed.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Scout product surface extraction returned invalid JSON") from exc


def _needs_argus_fallback(response: dict[str, Any]) -> bool:
    if response.get("success") is not False:
        return False
    error = str(response.get("error") or "").lower()
    return "no llm api key configured" in error


def _markdown_from_scrape_response(response: dict[str, Any]) -> str:
    if response.get("success") is False:
        raise RuntimeError(f"Scout product surface scrape failed: {response.get('error') or 'unknown error'}")
    markdown = (
        response.get("clean_markdown")
        or response.get("markdown")
        or response.get("raw_markdown")
        or ""
    )
    if not isinstance(markdown, str) or not markdown.strip():
        raise RuntimeError("Scout product surface scrape returned no markdown")
    return markdown


def _captured_at(response: dict[str, Any]) -> str:
    metadata = response.get("metadata")
    if isinstance(metadata, dict) and metadata.get("crawled_at"):
        return str(metadata["crawled_at"])
    return datetime.now(timezone.utc).isoformat()


def _model_id_from_provider(provider: str) -> str:
    provider = provider.strip()
    for prefix in ("gemini/", "google/"):
        if provider.startswith(prefix):
            return provider[len(prefix) :]
    return provider or "gemini-2.5-flash"


def _argus_extraction_prompt(
    markdown: str,
    target: ProductSurfaceTarget,
    *,
    focus_capability: str | None = None,
) -> str:
    clipped = markdown[:50000]
    focus = _focus_instruction(focus_capability)
    return (
        f"You are Argus inside CI-OS. Extract product reality proof for {target.company_name} "
        f"from this {target.surface_family} source.\n\n"
        "Return JSON matching the provided schema. Extract up to 12 rows. For changelog, "
        "release notes, and GitHub release pages, release entries, improvements, bug fixes, "
        "deprecations, and documented behavior changes count as product reality. For a "
        "static product, docs, pricing, or integration page, current documented capabilities, "
        "pricing/package details, API behavior, and integration proof count as product reality "
        f"even if they are not phrased as a new launch. {focus}Ignore generic marketing claims unless "
        "tied to release, docs, pricing, integration, API, or changelog proof. Each change "
        "must have capability, change_type, summary, and optional excerpt.\n\n"
        f"Source URL: {target.url}\n\n"
        f"Markdown:\n{clipped}"
    )


def extract_product_changes_with_argus(
    markdown: str,
    target: ProductSurfaceTarget,
    *,
    provider: Any = None,
    model_id: str,
    captured_at: str,
    focus_capability: str | None = None,
) -> dict[str, Any]:
    async def _extract() -> dict[str, Any]:
        model = provider or GoogleGeminiProvider(model_id=_model_id_from_provider(model_id), timeout_s=90.0)
        response = await model.generate(
            ModelRequest(
                task_profile="product_surface_extraction",
                capability_needs=["needs_json_mode"],
                prompt=_argus_extraction_prompt(markdown, target, focus_capability=focus_capability),
                json_schema=product_change_schema(),
                max_tokens=4000,
                tenant_id=str(target.tenant_id),
            )
        )
        data = response.parsed_json or extract_json_object(response.text) or {}
        if not isinstance(data, dict):
            data = {}
        return {
            "success": True,
            "url": target.url,
            "metadata": {"crawled_at": captured_at},
            "data": data,
        }

    return asyncio.run(_extract())


def _argus_response_from_scrape(
    target: ProductSurfaceTarget,
    *,
    scout_bin: str,
    use_js: bool,
    timeout_seconds: float,
    provider: str,
    focus_capability: str | None = None,
) -> dict[str, Any]:
    scrape_response = _run_command(
        build_scout_scrape_command(target, scout_bin=scout_bin, use_js=use_js),
        timeout_seconds,
    )
    kwargs: dict[str, Any] = {
        "provider": None,
        "model_id": provider,
        "captured_at": _captured_at(scrape_response),
    }
    if focus_capability and str(focus_capability).strip():
        kwargs["focus_capability"] = focus_capability
    return extract_product_changes_with_argus(
        _markdown_from_scrape_response(scrape_response),
        target,
        **kwargs,
    )


def github_release_rows(target: ProductSurfaceTarget, *, timeout_seconds: float) -> list[dict[str, Any]]:
    """Build product rows from public GitHub release notes when LLM extraction is empty."""
    api_url = _github_release_api_url(target.url)
    if not api_url:
        return []
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "cios-argus-product-surface",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=min(float(timeout_seconds), 30.0)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    if not isinstance(payload, list):
        return []

    rows: list[dict[str, Any]] = []
    for release in payload:
        if not isinstance(release, dict):
            continue
        tag = str(release.get("tag_name") or release.get("name") or "release").strip()
        source_url = str(release.get("html_url") or target.url).strip() or target.url
        captured_at = str(release.get("published_at") or datetime.now(timezone.utc).isoformat())
        body = str(release.get("body") or "").strip()
        for excerpt, capability in _release_body_items(body):
            rows.append(
                {
                    "company_id": target.company_id,
                    "company_name": target.company_name,
                    "company_role": target.company_role,
                    "capability": capability,
                    "change_type": _github_release_change_type(excerpt),
                    "summary": f"{target.company_name} {tag}: {excerpt}",
                    "source_url": source_url,
                    "captured_at": captured_at,
                    "excerpt": excerpt,
                    "method": "scout_changelog",
                    "surface_family": target.surface_family,
                }
            )
            if len(rows) >= 12:
                return rows
    return rows


def _github_release_api_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[2] != "releases":
        return None
    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        return None
    return f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=5"


def _release_body_items(body: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if not (
            stripped.startswith("- ")
            or stripped.startswith("* ")
            or re.match(r"^\d+[.)]\s+", stripped)
        ):
            continue
        text = _clean_release_line(stripped)
        if not text or _is_generic_release_line(text):
            continue
        capability = _capability_from_release_line(text)
        if not capability:
            continue
        items.append((text, capability))
    return items


def _clean_release_line(value: str) -> str:
    text = re.sub(r"^([-*]|\d+[.)])\s+", "", value.strip())
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"</?[^>]+>", "", text)
    text = re.sub(r"\s+by\s+@[A-Za-z0-9-]+(?:\s+in\s+https://\S+)?", "", text)
    text = re.sub(r"\s+in\s+https://github\.com/\S+", "", text)
    text = text.replace("`", "").replace("**", "").replace("__", "")
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _capability_from_release_line(text: str) -> str:
    capability = re.sub(r"^\[[^\]]+\]\s*", "", text).strip()
    capability = re.sub(
        r"^(fixed|fixes|fix|added|add|improved|improve|supports|support|removed|remove|deprecated|deprecates)\s+",
        "",
        capability,
        flags=re.IGNORECASE,
    ).strip()
    return capability[:120].rstrip()


def _is_generic_release_line(text: str) -> bool:
    lowered = text.lower()
    if lowered in {"full changelog", "what's changed", "whats changed"} or lowered.startswith("full changelog:"):
        return True
    internal_terms = (
        "unit test",
        "unit tests",
        "test file",
        "test files",
        "ci workflow",
        "lint",
        "refactor",
        "chore",
        "dependencies",
    )
    return any(term in lowered for term in internal_terms)


def _github_release_change_type(text: str) -> str:
    lowered = text.lower()
    if "deprecat" in lowered or "removed" in lowered:
        return "deprecation"
    if "pricing" in lowered or "plan" in lowered or "package" in lowered:
        return "pricing_change"
    if "integration" in lowered or "connector" in lowered:
        return "integration"
    return "release"


def _filter_product_surface_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if not _is_site_boilerplate_product_row(row)]


def _is_site_boilerplate_product_row(row: dict[str, Any]) -> bool:
    capability = _norm_text(row.get("capability"))
    summary = _norm_text(row.get("summary"))
    excerpt = _norm_text(row.get("excerpt"))
    haystack = f"{capability} {summary} {excerpt}".strip()
    if not haystack:
        return False

    boilerplate_capabilities = (
        "cookie consent",
        "cookie categorization",
        "strictly necessary cookie",
        "preference cookie",
        "statistical cookie",
        "marketing cookie",
        "user consent interface",
        "policy document integration",
        "privacy policy",
        "cookie policy",
    )
    if any(term in capability for term in boilerplate_capabilities):
        return True

    boilerplate_phrases = (
        "accept deny view preferences",
        "cookie policy privacy policy",
        "strictly necessary cookies",
        "functional preferences statistics marketing",
        "store and/or access device information",
        "technical storage or access",
    )
    return any(term in haystack for term in boilerplate_phrases)


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _target_from_args(args: argparse.Namespace) -> ProductSurfaceTarget:
    return ProductSurfaceTarget(
        tenant_id=args.tenant_id,
        company_id=args.company_id,
        company_name=args.company_name,
        company_role=args.company_role,
        surface_family=args.surface_family,
        url=args.url,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True, type=int)
    parser.add_argument("--company-id", required=True, type=int)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--company-role", default="competitor")
    parser.add_argument("--surface-family", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--provider", default="ollama/llama3.2:3b")
    parser.add_argument("--scout-bin", default="scout")
    parser.add_argument("--scout-command-json")
    parser.add_argument("--focus-capability")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--js", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    target = _target_from_args(args)
    command = (
        json.loads(args.scout_command_json)
        if args.scout_command_json
        else build_scout_extract_command(
            target,
            scout_bin=args.scout_bin,
            provider=args.provider,
            use_js=args.js,
            focus_capability=args.focus_capability,
        )
    )
    response = _run_command(command, args.timeout_seconds)
    used_argus_fallback = False
    if _needs_argus_fallback(response):
        response = _argus_response_from_scrape(
            target,
            scout_bin=args.scout_bin,
            use_js=args.js,
            timeout_seconds=args.timeout_seconds,
            provider=args.provider,
            focus_capability=args.focus_capability,
        )
        used_argus_fallback = True
    rows = _filter_product_surface_rows(scout_extract_response_to_product_records(response, target))
    if not rows and not used_argus_fallback:
        response = _argus_response_from_scrape(
            target,
            scout_bin=args.scout_bin,
            use_js=args.js,
            timeout_seconds=args.timeout_seconds,
            provider=args.provider,
            focus_capability=args.focus_capability,
        )
        rows = _filter_product_surface_rows(scout_extract_response_to_product_records(response, target))
    if not rows:
        rows = _filter_product_surface_rows(github_release_rows(target, timeout_seconds=args.timeout_seconds))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
