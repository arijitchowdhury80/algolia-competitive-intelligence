#!/usr/bin/env python3
"""Publish a Phase 8 recommendation work artifact to the public pilot surface."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


JSON_NAME = "argus-pmm-narrative-brief.json"
MARKDOWN_NAME = "argus-pmm-narrative-brief.md"
MANIFEST_NAME = "argus-phase8-work-artifacts.json"

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


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("work artifact must be a JSON object")
    return data


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _public_url(base_url: str, rel_path: str) -> str:
    return f"{base_url.rstrip('/')}/{rel_path.lstrip('/')}"


def _private_findings(text: str) -> list[str]:
    findings: list[str] = []
    for code, pattern in PRIVATE_REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(f"{code}:{match.group(0)}")
    return findings


def _validate_public_safe(path: Path) -> None:
    findings = _private_findings(path.read_text(encoding="utf-8", errors="ignore"))
    if findings:
        raise ValueError(f"{path.name} contains non-public reference: {findings[0]}")


def _validate_artifact(artifact: Mapping[str, Any]) -> None:
    if artifact.get("phase") != "phase8_controlled_pilot":
        raise ValueError("work artifact phase must be phase8_controlled_pilot")
    if artifact.get("artifact_type") != "named_team_recommendation_work_artifact":
        raise ValueError("work artifact type must be named_team_recommendation_work_artifact")
    if artifact.get("status") != "draft_for_named_team_review":
        raise ValueError("work artifact status must be draft_for_named_team_review")
    if artifact.get("phase8_exit_evidence") is not False:
        raise ValueError("public work artifact must not be Phase 8 exit evidence")
    recommendation = _dict_value(artifact.get("recommendation"))
    if recommendation.get("recommendation_id") in (None, "", 0):
        raise ValueError("work artifact recommendation_id is required")


def _manifest(artifact: Mapping[str, Any], *, base_url: str, generated_at: str) -> dict[str, Any]:
    recommendation = _dict_value(artifact.get("recommendation"))
    work_product = _dict_value(artifact.get("work_product"))
    return {
        "schema_version": 1,
        "phase": "phase8_controlled_pilot",
        "generated_at": generated_at,
        "status": "published",
        "phase8_exit_evidence": False,
        "items": [
            {
                "artifact_type": artifact.get("artifact_type"),
                "status": artifact.get("status"),
                "named_team": artifact.get("named_team"),
                "recommendation_id": recommendation.get("recommendation_id"),
                "owner": recommendation.get("owner"),
                "title": work_product.get("title"),
                "phase8_exit_evidence": False,
                "public_urls": {
                    "json": _public_url(base_url, f"data/phase8/{JSON_NAME}"),
                    "markdown": _public_url(base_url, f"data/phase8/{MARKDOWN_NAME}"),
                },
                "next_required_action": artifact.get("next_required_action"),
            }
        ],
    }


def _write_json(payload: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def publish_work_artifact(
    *,
    artifact_json: Path,
    artifact_markdown: Path,
    public_dir: Path,
    base_url: str,
    output: Path | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    _validate_public_safe(artifact_json)
    _validate_public_safe(artifact_markdown)
    artifact = _load_json(artifact_json)
    _validate_artifact(artifact)
    generated = generated_at or _now()

    primary_dir = public_dir / "data" / "phase8"
    v2_dir = public_dir / "v2" / "data" / "phase8"
    for target_dir in (primary_dir, v2_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact_json, target_dir / JSON_NAME)
        shutil.copyfile(artifact_markdown, target_dir / MARKDOWN_NAME)

    manifest = _manifest(artifact, base_url=base_url, generated_at=generated)
    for target_dir in (primary_dir, v2_dir):
        _write_json(manifest, target_dir / MANIFEST_NAME)

    recommendation = _dict_value(artifact.get("recommendation"))
    summary = {
        "gate": "phase8_work_artifact_publication",
        "generated_at": generated,
        "status": "published",
        "phase8_exit_evidence": False,
        "recommendation_id": recommendation.get("recommendation_id"),
        "named_team": artifact.get("named_team"),
        "public_urls": manifest["items"][0]["public_urls"],
        "manifest_url": _public_url(base_url, f"data/phase8/{MANIFEST_NAME}"),
        "v2_manifest_url": _public_url(base_url, f"v2/data/phase8/{MANIFEST_NAME}"),
    }
    if output:
        _write_json(summary, output)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-json", required=True, type=Path)
    parser.add_argument("--artifact-markdown", required=True, type=Path)
    parser.add_argument("--public-dir", required=True, type=Path)
    parser.add_argument("--base-url", default="https://ci.chowmes.com")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    summary = publish_work_artifact(
        artifact_json=args.artifact_json,
        artifact_markdown=args.artifact_markdown,
        public_dir=args.public_dir,
        base_url=args.base_url,
        output=args.output,
    )
    print(f"PASS phase8_work_artifact_publication: {summary['public_urls']['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
