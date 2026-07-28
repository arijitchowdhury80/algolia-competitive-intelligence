#!/usr/bin/env python3
"""Record Phase 8 pilot disposition evidence for an Argus recommendation.

This script deliberately writes an auditable artifact instead of mutating the
database. Phase 8 requires proof that a named team used, rejected, or amended a
recommendation in real work. A pending handoff is useful, but it is not exit
evidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


VALID_DECISIONS = {"pending", "used", "rejected", "amended"}
EXIT_DECISIONS = {"used", "rejected", "amended"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("review packet must be a JSON object")
    return data


def _clean(value: str | None, field: str, *, required: bool = True) -> str:
    cleaned = str(value or "").strip()
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _public_urls(values: Any) -> list[str]:
    urls: list[str] = []
    if not isinstance(values, list):
        return urls
    for value in values:
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value.startswith(("http://", "https://")) and value not in urls:
            urls.append(value)
    return urls


def _recommendation_status_to_set(decision: str) -> str | None:
    if decision == "used":
        return "done"
    if decision in {"rejected", "amended"}:
        return "dismissed"
    return None


def _learning_required(decision: str) -> bool:
    return decision in {"rejected", "amended"}


def _phase8_exit_evidence(decision: str, *, learning_required: bool, learning_event_id: int | None) -> bool:
    if decision == "used":
        return True
    if decision in {"rejected", "amended"}:
        return learning_required and learning_event_id is not None
    return False


def _next_required_action(decision: str, *, phase8_exit_evidence: bool) -> str:
    if phase8_exit_evidence:
        return "Run the next observation and verify the disposition remains visible in the Phase 8 record."
    if decision == "pending":
        return "Record a named-team use, rejection, or amendment before claiming Phase 8 exit."
    if decision in {"rejected", "amended"}:
        return "Record the amendment or rejection through the learning path, then preserve learning_event_id and improvement_id."
    return "Complete the missing disposition evidence before claiming Phase 8 exit."


def build_disposition(
    *,
    review_packet: Mapping[str, Any],
    decision: str,
    named_team: str,
    decided_by: str,
    use_case: str,
    reason: str,
    work_artifact_url: str | None = None,
    learning_event_id: int | None = None,
    improvement_id: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    decision = _clean(decision, "decision").lower()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of: {', '.join(sorted(VALID_DECISIONS))}")
    named_team = _clean(named_team, "named_team")
    decided_by = _clean(decided_by, "decided_by")
    reason = _clean(reason, "reason")
    use_case = _clean(use_case, "use_case", required=decision in EXIT_DECISIONS)

    recommendation = _dict_value(review_packet.get("recommendation"))
    evidence_summary = _dict_value(review_packet.get("evidence_summary"))
    recommendation_id = recommendation.get("recommendation_id")
    if recommendation_id in (None, "", 0):
        raise ValueError("review packet recommendation_id is required")

    work_artifact_url = _clean(work_artifact_url, "work_artifact_url", required=False)
    if work_artifact_url and not work_artifact_url.startswith(("http://", "https://")):
        raise ValueError("work_artifact_url must be http or https when provided")

    learning_needed = _learning_required(decision)
    exit_evidence = _phase8_exit_evidence(
        decision,
        learning_required=learning_needed,
        learning_event_id=learning_event_id,
    )
    learning_proof: dict[str, int] = {}
    if learning_event_id is not None:
        learning_proof["learning_event_id"] = int(learning_event_id)
    if improvement_id is not None:
        learning_proof["improvement_id"] = int(improvement_id)

    payload: dict[str, Any] = {
        "phase": "phase8_controlled_pilot",
        "generated_at": generated_at or _now(),
        "decision": decision,
        "phase8_exit_evidence": exit_evidence,
        "recommendation_status_to_set": _recommendation_status_to_set(decision),
        "learning_required": learning_needed,
        "next_required_action": _next_required_action(decision, phase8_exit_evidence=exit_evidence),
        "recommendation": {
            "recommendation_id": recommendation_id,
            "owner": recommendation.get("owner"),
            "urgency": recommendation.get("urgency"),
            "confidence": recommendation.get("confidence"),
            "action": recommendation.get("action"),
            "why_now": recommendation.get("top_insight"),
            "trace_status": recommendation.get("trace_status"),
        },
        "disposition": {
            "named_team": named_team,
            "decided_by": decided_by,
            "use_case": use_case,
            "reason": reason,
            "work_artifact_url": work_artifact_url or None,
        },
        "evidence_summary": {
            "recommendation_count": evidence_summary.get("recommendation_count"),
            "pattern_count": evidence_summary.get("pattern_count"),
            "demand_signal_count": evidence_summary.get("demand_signal_count"),
            "evidence_urls": _public_urls(evidence_summary.get("evidence_urls")),
            "confidence_limits": [
                item for item in review_packet.get("confidence_limits", []) if isinstance(item, str) and item.strip()
            ],
        },
    }
    if learning_proof:
        payload["learning_proof"] = learning_proof
    return payload


def write_payload(payload: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def _markdown(payload: Mapping[str, Any]) -> str:
    recommendation = _dict_value(payload.get("recommendation"))
    disposition = _dict_value(payload.get("disposition"))
    lines = [
        "# Phase 8 Pilot Recommendation Disposition",
        "",
        f"Decision: `{payload.get('decision')}`",
        f"Phase 8 exit evidence: `{str(payload.get('phase8_exit_evidence')).lower()}`",
        f"Generated at: `{payload.get('generated_at')}`",
        "",
        "## Recommendation",
        "",
        f"- ID: `{recommendation.get('recommendation_id')}`",
        f"- Owner: `{recommendation.get('owner')}`",
        f"- Action: {recommendation.get('action')}",
        "",
        "## Disposition",
        "",
        f"- Named team: `{disposition.get('named_team')}`",
        f"- Decided by: `{disposition.get('decided_by')}`",
        f"- Use case: {disposition.get('use_case') or 'Pending'}",
        f"- Reason: {disposition.get('reason')}",
        "",
        "## Next Required Action",
        "",
        str(payload.get("next_required_action") or ""),
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record Phase 8 pilot recommendation disposition evidence.")
    parser.add_argument("--review-packet", required=True, type=Path)
    parser.add_argument("--decision", required=True, choices=sorted(VALID_DECISIONS))
    parser.add_argument("--named-team", required=True)
    parser.add_argument("--decided-by", required=True)
    parser.add_argument("--use-case", default="")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--work-artifact-url")
    parser.add_argument("--learning-event-id", type=int)
    parser.add_argument("--improvement-id", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_disposition(
        review_packet=_load_json(args.review_packet),
        decision=args.decision,
        named_team=args.named_team,
        decided_by=args.decided_by,
        use_case=args.use_case,
        reason=args.reason,
        work_artifact_url=args.work_artifact_url,
        learning_event_id=args.learning_event_id,
        improvement_id=args.improvement_id,
    )
    write_payload(payload, args.output)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(_markdown(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
