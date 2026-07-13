#!/usr/bin/env python3
"""CLI-compatible Scout shim backed by a hosted Scout HTTP service.

CI-OS product-surface execution expects a `scout extract ...` command. On the
Hermes host we keep the heavy Scout/Crawl4AI stack in its own service and use
this lightweight executable as the package boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scout-http-shim")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract")
    extract.add_argument("url")
    extract.add_argument("--schema", default="{}")
    extract.add_argument("--instruction", default="")
    extract.add_argument("--provider", default="ollama/llama3.2:3b")
    extract.add_argument("--timeout-seconds", type=float, default=120)
    extract.add_argument("--base-url", default=os.environ.get("SCOUT_HTTP_BASE_URL", "https://scout.chowmes.com"))
    extract.add_argument("--js", action="store_true")

    scrape = subparsers.add_parser("scrape")
    scrape.add_argument("url")
    scrape.add_argument("--timeout-seconds", type=float, default=120)
    scrape.add_argument("--base-url", default=os.environ.get("SCOUT_HTTP_BASE_URL", "https://scout.chowmes.com"))
    scrape.add_argument("--js", action="store_true")
    return parser.parse_args(argv)


def build_extract_payload(args: argparse.Namespace) -> dict[str, Any]:
    try:
        schema = json.loads(args.schema)
    except json.JSONDecodeError as exc:
        raise ValueError("--schema must be valid JSON") from exc
    if not isinstance(schema, dict):
        raise ValueError("--schema must decode to a JSON object")

    return {
        "url": args.url,
        "schema": schema,
        "instruction": args.instruction,
        "llm_provider": args.provider,
        "use_js": bool(args.js),
        "timeout_ms": int(float(args.timeout_seconds) * 1000),
    }


def build_scrape_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "url": args.url,
        "formats": ["markdown"],
        "use_js": bool(args.js),
        "timeout_ms": int(float(args.timeout_seconds) * 1000),
    }


def build_auth_headers() -> dict[str, str]:
    api_key = os.environ.get("SCOUT_HTTP_API_KEY") or os.environ.get("SCOUT_API_KEY")
    if not api_key:
        return {}
    return {"X-API-Key": api_key}


def run_extract(args: argparse.Namespace) -> dict[str, Any]:
    base_url = str(args.base_url).rstrip("/")
    timeout = float(args.timeout_seconds) + 5.0
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/extract", json=build_extract_payload(args), headers=build_auth_headers())
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Scout /extract returned non-object JSON")
    return data


def run_scrape(args: argparse.Namespace) -> dict[str, Any]:
    base_url = str(args.base_url).rstrip("/")
    timeout = float(args.timeout_seconds) + 5.0
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/scrape", json=build_scrape_payload(args), headers=build_auth_headers())
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Scout /scrape returned non-object JSON")
    return data


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.command == "extract":
            data = run_extract(args)
        elif args.command == "scrape":
            data = run_scrape(args)
        else:
            raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:  # noqa: BLE001 - command-line boundary
        print(f"Scout HTTP {args.command} failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(data, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
