#!/usr/bin/env python3
"""
Parallel CLI Monitor Setup
===========================
Creates monitors for all Tier 1-2 competitor blogs, changelogs, and press pages.
Monitors push alerts when content changes.

Usage:
  python3 scripts/setup-monitors.py
  python3 scripts/setup-monitors.py --dry-run  # show commands without executing
"""

import argparse
import subprocess
import sys
import yaml
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SOURCES_FILE = SKILL_DIR / "references" / "sources.yaml"

MONITORED_TYPES = {
    "blog",
    "changelog",
    "press",
    "product",
    "roadmap",
    "case_study",
    "docs",
    "pricing",
    "protocol",
    "news",
}


def load_monitor_urls():
    """Derive monitor targets from sources.yaml so registry and monitors stay aligned."""
    config = yaml.safe_load(SOURCES_FILE.read_text())
    urls = []
    for key, value in (config.get("sources") or {}).items():
        if key in {"industry", "community"}:
            for item in value or []:
                if item.get("type") in MONITORED_TYPES and item.get("url"):
                    urls.append((item.get("name") or item["url"], item["url"]))
            continue
        if not isinstance(value, dict):
            continue
        company = value.get("company", key)
        for item in value.get("urls", []) or []:
            if item.get("type") in MONITORED_TYPES and item.get("url"):
                urls.append(("%s %s" % (company, item.get("type")), item["url"]))
    seen = set()
    deduped = []
    for name, url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append((name, url))
    return deduped


def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return result."""
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def setup_monitors(dry_run: bool = False):
    """Create Parallel CLI monitors for all target URLs."""
    created = []
    failed = []

    for name, url in load_monitor_urls():
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Setting up monitor: {name}")
        print(f"  URL: {url}")

        cmd = [
            "parallel-cli", "monitor", "create",
            "--url", url,
            "--name", name,
            "--json"
        ]

        if dry_run:
            print(f"  CMD: {' '.join(cmd)}")
            created.append((name, url))
            continue

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(f"  [OK] Monitor created: {name}")
                created.append((name, url))
            else:
                print(f"  [FAIL] {result.stderr[:200]}")
                failed.append((name, url, result.stderr[:200]))
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {name}")
            failed.append((name, url, "timeout"))
        except FileNotFoundError:
            print(f"  [FATAL] parallel-cli not found. Install: npm install -g parallel-web-cli")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Monitors created: {len(created)}")
    print(f"Monitors failed: {len(failed)}")
    if failed:
        print("\nFailed monitors:")
        for name, url, error in failed:
            print(f"  - {name}: {error[:100]}")


def list_monitors():
    """List existing monitors."""
    try:
        result = subprocess.run(
            ["parallel-cli", "monitor", "list", "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            import json
            monitors = json.loads(result.stdout)
            if isinstance(monitors, list):
                print(f"\nExisting monitors ({len(monitors)}):")
                for m in monitors:
                    print(f"  - {m.get('name', m.get('url', 'unknown'))}")
            elif isinstance(monitors, dict):
                ml = monitors.get("monitors", [])
                print(f"\nExisting monitors ({len(ml)}):")
                for m in ml:
                    print(f"  - {m.get('name', m.get('url', 'unknown'))}")
    except Exception as e:
        print(f"Could not list monitors: {e}")


def main():
    parser = argparse.ArgumentParser(description="Setup Parallel CLI monitors")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
    parser.add_argument("--list", action="store_true", help="List existing monitors only")
    args = parser.parse_args()

    if args.list:
        list_monitors()
        return

    print("=== Parallel CLI Monitor Setup ===\n")
    setup_monitors(dry_run=args.dry_run)
    print("\nDone. Use 'parallel-cli monitor list --json' to verify.")


if __name__ == "__main__":
    main()
