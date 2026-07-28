#!/usr/bin/env python3
"""Export a Phase 8 named-team work artifact from the current Argus read.

This script creates a concrete Product Marketing review brief from the current
recommendation. It deliberately does not create Phase 8 exit evidence: a real
named team still has to use, reject, or amend the artifact and record that
disposition.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("review packet must be a JSON object")
    return data


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _public_urls(values: Any) -> list[str]:
    urls: list[str] = []
    if not isinstance(values, list):
        return urls
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned.startswith(("http://", "https://")) and cleaned not in urls:
            urls.append(cleaned)
    return urls


def _demand_signal(demand_topics: list[dict[str, Any]]) -> str:
    if not demand_topics:
        return "No named audience-demand topic was linked to this recommendation."
    topic = demand_topics[0]
    label = _clean_text(topic.get("topic")) or "The linked demand topic"
    value = topic.get("value")
    metric = _clean_text(topic.get("metric")) or "signals"
    change = topic.get("change_pct")
    parts = [f"{label} registered {value} {metric}" if value is not None else f"{label} is the linked demand topic"]
    if change is not None:
        parts.append(f"with change_pct={change}")
    return ", ".join(parts) + "."


def _merge_evidence_urls(evidence_summary: Mapping[str, Any], demand_topics: list[dict[str, Any]]) -> list[str]:
    urls = _public_urls(evidence_summary.get("evidence_urls"))
    for topic in demand_topics:
        for key in ("evidence_urls", "linked_evidence_urls"):
            for url in _public_urls(topic.get(key)):
                if url not in urls:
                    urls.append(url)
    return urls


def _title_from_topics(demand_topics: list[dict[str, Any]]) -> str:
    if demand_topics:
        topic = _clean_text(demand_topics[0].get("topic"))
        if topic:
            return f"{topic} PMM Narrative Brief"
    return "Argus PMM Narrative Brief"


def _positioning_thesis(action: str, why_now: str) -> str:
    if why_now:
        return f"{action} The PMM story should lead with the verified gap: {why_now}"
    return f"{action} The PMM story should stay bounded to the cited evidence and avoid uncited market claims."


def build_work_artifact(
    review_packet: Mapping[str, Any],
    *,
    generated_by: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    recommendation = _dict_value(review_packet.get("recommendation"))
    evidence_summary = _dict_value(review_packet.get("evidence_summary"))
    scorecard = _dict_value(recommendation.get("scorecard"))
    recommendation_id = recommendation.get("recommendation_id")
    if recommendation_id in (None, "", 0):
        raise ValueError("review packet recommendation_id is required")

    action = _clean_text(recommendation.get("action"))
    if not action:
        raise ValueError("review packet recommendation action is required")
    owner = _clean_text(recommendation.get("owner")) or "PMM"
    named_team = "Product Marketing" if owner == "PMM" else owner
    why_now = _clean_text(recommendation.get("top_insight"))
    confidence_limits = [
        _clean_text(item) for item in review_packet.get("confidence_limits", []) if _clean_text(item)
    ]
    demand_topics = [
        topic for topic in review_packet.get("demand_topics", []) if isinstance(topic, dict)
    ]
    evidence_urls = _merge_evidence_urls(evidence_summary, demand_topics)
    scorecard_summary = _clean_text(scorecard.get("summary"))
    proof_signal = scorecard_summary or why_now or "The recommendation is bounded to the current Argus evidence packet."

    payload: dict[str, Any] = {
        "phase": "phase8_controlled_pilot",
        "artifact_type": "named_team_recommendation_work_artifact",
        "generated_at": generated_at or _now(),
        "generated_by": _clean_text(generated_by) or "codex",
        "named_team": named_team,
        "status": "draft_for_named_team_review",
        "phase8_exit_evidence": False,
        "next_required_action": (
            f"{named_team} must use, reject, or amend this artifact and record a final Phase 8 disposition."
        ),
        "recommendation": {
            "recommendation_id": recommendation_id,
            "owner": owner,
            "urgency": recommendation.get("urgency"),
            "confidence": recommendation.get("confidence"),
            "action": action,
            "why_now": why_now,
            "scorecard": scorecard,
        },
        "work_product": {
            "title": _title_from_topics(demand_topics),
            "positioning_thesis": _positioning_thesis(action, why_now),
            "brief_sections": {
                "product_proof": proof_signal,
                "audience_demand_signal": _demand_signal(demand_topics),
                "conversation_gap": why_now or "Argus did not capture enough public conversation to justify a broader claim.",
                "confidence_boundary": (
                    "Use this as a controlled-pilot PMM draft, not as final public positioning, until the named team "
                    "accepts or amends it."
                ),
            },
            "recommended_next_moves": [
                "Draft a sourced PMM narrative that connects shipped Agent Studio proof to the current demand signal.",
                "Pull one customer-proof or product-proof quote from an approved public source before external reuse.",
                "Record whether Product Marketing used, rejected, or amended the recommendation in the Phase 8 disposition artifact.",
            ],
        },
        "evidence_summary": {
            "recommendation_count": evidence_summary.get("recommendation_count"),
            "pattern_count": evidence_summary.get("pattern_count"),
            "demand_signal_count": evidence_summary.get("demand_signal_count"),
            "evidence_urls": evidence_urls,
            "confidence_limits": confidence_limits,
        },
    }
    return payload


def _markdown(payload: Mapping[str, Any]) -> str:
    recommendation = _dict_value(payload.get("recommendation"))
    work_product = _dict_value(payload.get("work_product"))
    sections = _dict_value(work_product.get("brief_sections"))
    evidence = _dict_value(payload.get("evidence_summary"))
    lines = [
        f"# {work_product.get('title')}",
        "",
        f"Status: `{payload.get('status')}`",
        f"Phase 8 exit evidence: `{str(payload.get('phase8_exit_evidence')).lower()}`",
        f"Named team: `{payload.get('named_team')}`",
        f"Generated at: `{payload.get('generated_at')}`",
        "",
        "## Recommendation",
        "",
        str(recommendation.get("action") or ""),
        "",
        "## Positioning Thesis",
        "",
        str(work_product.get("positioning_thesis") or ""),
        "",
        "## Proof Signals",
        "",
        f"- Product proof: {sections.get('product_proof')}",
        f"- Audience demand: {sections.get('audience_demand_signal')}",
        f"- Conversation gap: {sections.get('conversation_gap')}",
        "",
        "## Recommended Next Moves",
        "",
    ]
    for move in work_product.get("recommended_next_moves", []):
        lines.append(f"- {move}")
    lines.extend(["", "## Confidence Boundary", "", str(sections.get("confidence_boundary") or ""), ""])
    limits = evidence.get("confidence_limits") or []
    if limits:
        lines.extend(["## Confidence Limits", ""])
        for limit in limits:
            lines.append(f"- {limit}")
        lines.append("")
    urls = evidence.get("evidence_urls") or []
    if urls:
        lines.extend(["## Evidence URLs", ""])
        for url in urls:
            lines.append(f"- {url}")
        lines.append("")
    lines.extend(["## Next Required Action", "", str(payload.get("next_required_action") or ""), ""])
    return "\n".join(lines)


def export_work_artifact(
    review_packet_path: Path,
    *,
    output: Path,
    markdown_output: Path | None,
    generated_by: str,
) -> dict[str, Any]:
    payload = build_work_artifact(_load_json(review_packet_path), generated_by=generated_by)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_markdown(payload), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a Phase 8 named-team recommendation work artifact.")
    parser.add_argument("--review-packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--generated-by", default="codex")
    args = parser.parse_args(argv)

    export_work_artifact(
        args.review_packet,
        output=args.output,
        markdown_output=args.markdown_output,
        generated_by=args.generated_by,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
