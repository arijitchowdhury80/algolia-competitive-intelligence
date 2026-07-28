#!/usr/bin/env python3
"""Scan CI-OS public artifacts for private paths, secrets, and unsafe runtime refs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCANNED_SUFFIXES = {".html", ".js", ".json", ".css", ".txt", ".map"}
FORBIDDEN_RUNTIME_HOSTS = (
    "unpkg.com",
    "cdn.jsdelivr.net",
    "esm.sh",
    "skypack.dev",
    "raw.githubusercontent.com",
)

PRIVATE_PATH_PATTERNS = (
    re.compile(r"/root/(?:\.hermes|[^\"'<>\s]*)"),
    re.compile(r"/Users/[^\"'<>\s]+"),
    re.compile(r"/private/tmp/[^\"'<>\s]+"),
    re.compile(r"/tmp/[^\"'<>\s]+"),
    re.compile(r"/opt/cios/(?:app|public|private|out|tmp)[^\"'<>\s]*"),
)
FILE_URL_RE = re.compile(r"file://[^\"'<>\s]+")
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-(?:live|test|proj)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{24,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*[\"'][^\"']{16,}[\"']"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finding(path: Path, public_dir: Path, *, code: str, detail: str) -> dict[str, str]:
    try:
        rel = path.relative_to(public_dir)
    except ValueError:
        rel = path
    return {"file": str(rel), "code": code, "detail": detail}


def _scan_text(path: Path, public_dir: Path, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for pattern in PRIVATE_PATH_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(_finding(path, public_dir, code="private_path", detail=match.group(0)))
    for match in FILE_URL_RE.finditer(text):
        findings.append(_finding(path, public_dir, code="file_url", detail=match.group(0)))
    for pattern in SECRET_VALUE_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(_finding(path, public_dir, code="secret_like_value", detail=_redact(match.group(0))))
    for host in FORBIDDEN_RUNTIME_HOSTS:
        if host in text:
            findings.append(_finding(path, public_dir, code="external_runtime_host", detail=host))
    return findings


def _redact(value: str) -> str:
    if len(value) <= 12:
        return "[redacted]"
    return f"{value[:6]}...[redacted]...{value[-4:]}"


def _iter_public_files(public_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in public_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SCANNED_SUFFIXES
    )


def scan_public_artifacts(public_dir: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    if not public_dir.exists():
        return {
            "gate": "public_artifact_safety_scan",
            "generated_at": generated_at or _now(),
            "public_dir": str(public_dir),
            "status": "failed",
            "public_safe": False,
            "scanned_file_count": 0,
            "findings": [{"file": str(public_dir), "code": "missing_public_dir", "detail": "directory does not exist"}],
        }

    findings: list[dict[str, str]] = []
    files = _iter_public_files(public_dir)
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(_scan_text(path, public_dir, text))

    public_safe = not findings
    return {
        "gate": "public_artifact_safety_scan",
        "generated_at": generated_at or _now(),
        "public_dir": str(public_dir),
        "status": "passed" if public_safe else "failed",
        "public_safe": public_safe,
        "scanned_file_count": len(files),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON evidence output path.")
    args = parser.parse_args(argv)

    result = scan_public_artifacts(args.public_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{'PASS' if result['public_safe'] else 'FAIL'} public_artifact_safety_scan")
    return 0 if result["public_safe"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
