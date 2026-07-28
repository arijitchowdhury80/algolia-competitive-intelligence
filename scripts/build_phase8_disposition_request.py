#!/usr/bin/env python3
"""Build the Phase 8 named-team disposition request.

This artifact is the auditable handoff between a published PMM work artifact
and the final Phase 8 exit evidence. It deliberately is not exit evidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DECISION_OPTIONS = ("used", "rejected", "amended")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _require_public_url(value: str, field: str) -> str:
    cleaned = _clean(value)
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError(f"{field} must be a public http or https URL")
    return cleaned


def _require_relative_path(value: str, field: str) -> str:
    cleaned = _clean(value)
    if not cleaned:
        raise ValueError(f"{field} is required")
    if cleaned.startswith(("/", "file://")) or ".." in Path(cleaned).parts:
        raise ValueError(f"{field} must be a relative package path")
    return cleaned


def _validate_work_artifact(artifact: Mapping[str, Any]) -> None:
    if artifact.get("phase") != "phase8_controlled_pilot":
        raise ValueError("work artifact phase must be phase8_controlled_pilot")
    if artifact.get("artifact_type") != "named_team_recommendation_work_artifact":
        raise ValueError("work artifact type must be named_team_recommendation_work_artifact")
    if artifact.get("phase8_exit_evidence") is not False:
        raise ValueError("disposition request can only be built from non-exit work artifacts")
    recommendation = _dict_value(artifact.get("recommendation"))
    if recommendation.get("recommendation_id") in (None, "", 0):
        raise ValueError("work artifact recommendation_id is required")


def _sample_command(*, review_packet_path: str, work_artifact_url: str) -> str:
    return (
        "python scripts/record_pilot_recommendation_disposition.py "
        f"--review-packet {review_packet_path} "
        "--decision used "
        '--named-team "Product Marketing" '
        '--decided-by "<name-or-team>" '
        '--use-case "<where the recommendation was used>" '
        '--reason "<why this disposition is true>" '
        f"--work-artifact-url {work_artifact_url} "
        "--output out/phase8/argus-recommendation-disposition-final.json "
        "--markdown-output out/phase8/argus-recommendation-disposition-final.md"
    )


def build_disposition_request(
    work_artifact: Mapping[str, Any],
    *,
    work_artifact_url: str,
    manifest_url: str,
    review_packet_path: str = "out/phase8/argus-recommendation-review-packet.json",
    generated_at: str | None = None,
) -> dict[str, Any]:
    _validate_work_artifact(work_artifact)
    work_artifact_url = _require_public_url(work_artifact_url, "work_artifact_url")
    manifest_url = _require_public_url(manifest_url, "manifest_url")
    review_packet_path = _require_relative_path(review_packet_path, "review_packet_path")

    recommendation = _dict_value(work_artifact.get("recommendation"))
    work_product = _dict_value(work_artifact.get("work_product"))
    named_team = _clean(work_artifact.get("named_team")) or "Product Marketing"

    return {
        "phase": "phase8_controlled_pilot",
        "artifact_type": "named_team_disposition_request",
        "generated_at": generated_at or _now(),
        "status": "awaiting_named_team_disposition",
        "phase8_exit_evidence": False,
        "named_team": named_team,
        "recommendation_id": recommendation.get("recommendation_id"),
        "owner": recommendation.get("owner"),
        "urgency": recommendation.get("urgency"),
        "confidence": recommendation.get("confidence"),
        "recommendation_action": recommendation.get("action"),
        "work_artifact": {
            "title": work_product.get("title"),
            "public_url": work_artifact_url,
            "manifest_url": manifest_url,
        },
        "decision_required": {
            "question": (
                f"Did {named_team} use, reject, or amend this recommendation in a real planning or execution workflow?"
            ),
            "options": [
                {
                    "decision": "used",
                    "phase8_exit_evidence_when": (
                        "A named team, named use case, reason, and public work artifact URL are recorded."
                    ),
                    "requires_learning_proof": False,
                },
                {
                    "decision": "rejected",
                    "phase8_exit_evidence_when": (
                        "A rejection reason is recorded and the learning path preserves learning_event_id."
                    ),
                    "requires_learning_proof": True,
                },
                {
                    "decision": "amended",
                    "phase8_exit_evidence_when": (
                        "The amended use is recorded and the learning path preserves learning_event_id."
                    ),
                    "requires_learning_proof": True,
                },
            ],
        },
        "next_required_action": (
            "Product Marketing must select used, rejected, or amended and record the final disposition before "
            "Phase 8 can pass."
        ),
        "sample_record_command": _sample_command(
            review_packet_path=review_packet_path,
            work_artifact_url=work_artifact_url,
        ),
    }


def _markdown(payload: Mapping[str, Any]) -> str:
    work_artifact = _dict_value(payload.get("work_artifact"))
    decision_required = _dict_value(payload.get("decision_required"))
    lines = [
        "# Phase 8 PMM Disposition Request",
        "",
        f"Status: `{payload.get('status')}`",
        f"Phase 8 exit evidence: `{str(payload.get('phase8_exit_evidence')).lower()}`",
        f"Named team: `{payload.get('named_team')}`",
        f"Recommendation ID: `{payload.get('recommendation_id')}`",
        "",
        "## Recommendation",
        "",
        str(payload.get("recommendation_action") or ""),
        "",
        "## Work Artifact",
        "",
        f"- Title: {work_artifact.get('title')}",
        f"- Public brief: {work_artifact.get('public_url')}",
        f"- Manifest: {work_artifact.get('manifest_url')}",
        "",
        "## Decision Required",
        "",
        str(decision_required.get("question") or ""),
        "",
    ]
    for option in decision_required.get("options", []):
        if not isinstance(option, dict):
            continue
        lines.extend(
            [
                f"### {option.get('decision')}",
                "",
                str(option.get("phase8_exit_evidence_when") or ""),
                f"Requires learning proof: `{str(option.get('requires_learning_proof')).lower()}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Next Required Action",
            "",
            str(payload.get("next_required_action") or ""),
            "",
            "## Sample Record Command",
            "",
            "```bash",
            str(payload.get("sample_record_command") or ""),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(payload: Mapping[str, Any], *, output: Path, markdown_output: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_markdown(payload), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-artifact", required=True, type=Path)
    parser.add_argument("--work-artifact-url", required=True)
    parser.add_argument("--manifest-url", required=True)
    parser.add_argument("--review-packet-path", default="out/phase8/argus-recommendation-review-packet.json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    payload = build_disposition_request(
        _load_json(args.work_artifact),
        work_artifact_url=args.work_artifact_url,
        manifest_url=args.manifest_url,
        review_packet_path=args.review_packet_path,
    )
    write_outputs(payload, output=args.output, markdown_output=args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
