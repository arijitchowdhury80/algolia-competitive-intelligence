#!/usr/bin/env python3
"""Redact internal filesystem references from staged CI-OS public artifacts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCANNED_SUFFIXES = {".html", ".js", ".json", ".css", ".txt", ".map"}
REPLACEMENT = "[redacted-internal-path]"

PRIVATE_REFERENCE_PATTERNS = (
    ("private_path", re.compile(r"/root/(?:\.hermes|[^\"'<>\s]*)")),
    ("private_path", re.compile(r"/Users/[^\"'<>\s]+")),
    ("private_path", re.compile(r"/private/tmp/[^\"'<>\s]+")),
    ("private_path", re.compile(r"/tmp/[^\"'<>\s]+")),
    ("private_path", re.compile(r"/opt/cios/(?:app|public|private|out|tmp)[^\"'<>\s]*")),
    ("file_url", re.compile(r"file://[^\"'<>\s]+")),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iter_public_files(public_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in public_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SCANNED_SUFFIXES
    )


def _relative(path: Path, public_dir: Path) -> str:
    try:
        return str(path.relative_to(public_dir))
    except ValueError:
        return path.name


def _redact_text(text: str) -> tuple[str, list[dict[str, str]]]:
    redactions: list[dict[str, str]] = []
    updated = text
    for code, pattern in PRIVATE_REFERENCE_PATTERNS:
        updated, count = pattern.subn(REPLACEMENT, updated)
        for _ in range(count):
            redactions.append({"code": code, "replacement": REPLACEMENT})
    return updated, redactions


def redact_public_artifacts(public_dir: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    if not public_dir.exists():
        return {
            "gate": "public_artifact_redaction",
            "generated_at": generated_at or _now(),
            "public_dir": ".",
            "status": "failed",
            "public_safe_for_scan": False,
            "scanned_file_count": 0,
            "redacted_file_count": 0,
            "redaction_count": 0,
            "redactions": [
                {
                    "file": public_dir.name,
                    "code": "missing_public_dir",
                    "replacement": "",
                }
            ],
        }

    files = _iter_public_files(public_dir)
    redacted_file_count = 0
    redactions: list[dict[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        updated, file_redactions = _redact_text(text)
        if not file_redactions:
            continue
        path.write_text(updated, encoding="utf-8")
        redacted_file_count += 1
        rel = _relative(path, public_dir)
        redactions.extend({"file": rel, **redaction} for redaction in file_redactions)

    status = "redacted" if redactions else "clean"
    return {
        "gate": "public_artifact_redaction",
        "generated_at": generated_at or _now(),
        "public_dir": ".",
        "status": status,
        "public_safe_for_scan": True,
        "scanned_file_count": len(files),
        "redacted_file_count": redacted_file_count,
        "redaction_count": len(redactions),
        "redactions": redactions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON evidence output path.")
    args = parser.parse_args(argv)

    result = redact_public_artifacts(args.public_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{'FAIL' if result['status'] == 'failed' else 'PASS'} public_artifact_redaction: {result['status']}")
    return 0 if result["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
