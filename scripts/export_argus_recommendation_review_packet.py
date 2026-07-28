#!/usr/bin/env python3
"""Export a Phase 5 Argus recommendation review packet.

The packet is the auditable human-decision surface for Phase 5. It summarizes
the current live recommendation, evidence planes, confidence limits, and the
learning effect that must be proven after an accepted or challenged read.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACCEPTANCE_RUBRIC = [
    {
        "dimension": "accuracy",
        "question": "Does the recommendation accurately follow from the cited product, market, and demand evidence?",
        "required_for_pass": True,
    },
    {
        "dimension": "specificity",
        "question": "Is the recommended action concrete enough for a named team to execute?",
        "required_for_pass": True,
    },
    {
        "dimension": "novelty",
        "question": "Is the read more useful than a generic dashboard observation?",
        "required_for_pass": True,
    },
    {
        "dimension": "direct_team_usefulness",
        "question": "Can Marketing, Sales, Product, or Analyst Relations use this in the next operating cycle?",
        "required_for_pass": True,
    },
    {
        "dimension": "evidence_sufficiency",
        "question": "Are the confidence limits acceptable for a controlled pilot recommendation?",
        "required_for_pass": True,
    },
]

NAMED_TEAM_USES = [
    {
        "team": "Marketing",
        "use": "Turn Agent Studio proof into a sourced market narrative while audience demand is rising.",
    },
    {
        "team": "Sales",
        "use": "Use the Agent Studio demand signal to prioritize outbound angles and discovery questions.",
    },
    {
        "team": "Product Marketing",
        "use": "Connect shipped capability proof to positioning gaps and competitive narrative pressure.",
    },
    {
        "team": "Analyst Relations",
        "use": "Prepare evidence-backed briefing material on Agent Studio movement and market demand.",
    },
]

VALID_DECISIONS = {"awaiting_human_acceptance", "accepted", "rejected", "amended"}


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("dashboard payload must be a JSON object")
    return data


def _public_urls(values: Any) -> list[str]:
    urls: list[str] = []
    if not isinstance(values, list):
        return urls
    for value in values:
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value.startswith(("http://", "https://")):
            urls.append(value)
    return urls


def _brief(payload: dict[str, Any]) -> dict[str, Any]:
    product_market_run = payload.get("product_market_run") or {}
    if not isinstance(product_market_run, dict):
        product_market_run = {}
    brief = product_market_run.get("intelligence_brief") or {}
    if not isinstance(brief, dict):
        brief = {}
    return brief


def _product_market_run(payload: dict[str, Any]) -> dict[str, Any]:
    product_market_run = payload.get("product_market_run") or {}
    return product_market_run if isinstance(product_market_run, dict) else {}


def _current_open_recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    recommendations = payload.get("argus_recommendations")
    if not isinstance(recommendations, list):
        return {}
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        if str(recommendation.get("status") or "open").strip().lower() != "open":
            continue
        if str(recommendation.get("action") or "").strip():
            return recommendation
    return {}


def _trace(brief: dict[str, Any]) -> dict[str, Any]:
    trace = brief.get("demand_recommendation_trace") or {}
    return trace if isinstance(trace, dict) else {}


def _demand_topics(trace: dict[str, Any]) -> list[dict[str, Any]]:
    topics = trace.get("demand_topics")
    if not isinstance(topics, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        cleaned.append(
            {
                "topic": topic.get("topic"),
                "value": topic.get("value"),
                "metric": topic.get("metric"),
                "change_pct": topic.get("change_pct"),
                "signal_count": topic.get("signal_count"),
                "source_files": [
                    source for source in topic.get("source_files", []) if isinstance(source, str) and "/" not in source
                ],
                "evidence_urls": _public_urls(topic.get("evidence_urls")),
                "linked_evidence_urls": _public_urls(topic.get("linked_evidence_urls")),
                "scorecard_dimensions": [
                    dimension for dimension in topic.get("scorecard_dimensions", []) if isinstance(dimension, str)
                ],
                "recommendation_actions": [
                    action for action in topic.get("recommendation_actions", []) if isinstance(action, str)
                ],
            }
        )
    return cleaned


def build_review_packet(
    dashboard_path: Path,
    *,
    reviewed_by: str,
    decision: str = "awaiting_human_acceptance",
) -> dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of: {', '.join(sorted(VALID_DECISIONS))}")

    payload = _load_json(dashboard_path)
    product_market_run = _product_market_run(payload)
    brief = _brief(payload)
    trace = _trace(brief)
    current_recommendation = _current_open_recommendation(payload)
    topics = _demand_topics(trace)
    brief_primary_action = str(brief.get("primary_action") or "").strip()
    recommendation_action = str(current_recommendation.get("action") or "").strip()
    primary_action = brief_primary_action or recommendation_action
    action_source = "brief" if brief_primary_action else "current_recommendation" if recommendation_action else None
    scorecard = current_recommendation.get("scorecard") if current_recommendation else {}
    if not isinstance(scorecard, dict):
        scorecard = {}
    top_insight_candidates = (
        (current_recommendation.get("why_now"), scorecard.get("summary"), brief.get("top_insight"))
        if action_source == "current_recommendation"
        else (brief.get("top_insight"), current_recommendation.get("why_now"), scorecard.get("summary"))
    )
    top_insight = str(next((candidate for candidate in top_insight_candidates if candidate), "")).strip()
    if not primary_action:
        raise ValueError("dashboard intelligence brief has no primary_action")

    confidence_limits = brief.get("confidence_limits")
    if not isinstance(confidence_limits, list):
        confidence_limits = []
    confidence_limits = [item for item in confidence_limits if isinstance(item, str) and item.strip()]

    evidence_urls = _public_urls(trace.get("evidence_urls"))
    for evidence in current_recommendation.get("evidence_refs") or []:
        if not isinstance(evidence, dict):
            continue
        url = str(evidence.get("source_url") or "").strip()
        if url.startswith(("http://", "https://")) and url not in evidence_urls:
            evidence_urls.append(url)
    for topic in topics:
        for key in ("evidence_urls", "linked_evidence_urls"):
            for url in topic.get(key, []):
                if url not in evidence_urls:
                    evidence_urls.append(url)

    gate_status = decision
    learning_status = "ready_for_learning_proof" if decision in {"accepted", "amended", "rejected"} else "pending_acceptance_or_challenge"
    return {
        "phase": "phase5_argus_intelligence",
        "gate_status": gate_status,
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "recommendation": {
            **(
                {
                    "recommendation_id": current_recommendation.get("recommendation_id"),
                    "owner": current_recommendation.get("owner"),
                    "urgency": current_recommendation.get("urgency"),
                    "confidence": current_recommendation.get("confidence"),
                    "scorecard": current_recommendation.get("scorecard"),
                }
                if current_recommendation
                else {}
            ),
            "action": primary_action,
            "top_insight": top_insight,
            "trace_status": (
                "current_open_recommendation"
                if action_source == "current_recommendation"
                else trace.get("status")
            ),
        },
        "evidence_summary": {
            "recommendation_count": max(
                int(product_market_run.get("recommendation_count") or 0),
                int(trace.get("recommendation_count") or 0),
                1 if current_recommendation else 0,
            ),
            "pattern_count": product_market_run.get("pattern_count", trace.get("pattern_count")),
            "demand_signal_count": product_market_run.get("demand_signal_count", trace.get("demand_signal_count")),
            "rising_demand_topic_count": trace.get("rising_demand_topic_count"),
            "matched_demand_topic_count": trace.get("matched_demand_topic_count"),
            "evidence_urls": evidence_urls,
        },
        "demand_topics": topics,
        "confidence_limits": confidence_limits,
        "named_team_uses": NAMED_TEAM_USES,
        "acceptance_rubric": ACCEPTANCE_RUBRIC,
        "learning_effect": {
            "status": learning_status,
            "required_next_proof": (
                "Record the accepted, rejected, or amended read as learning, generate the next-sweep learning plan, "
                "build the gated apply plan, and prove the next successful run reflects the accepted instruction."
            ),
            "existing_package_hooks": [
                "scripts/record_recommendation_challenge.py",
                "scripts/build_next_sweep_learning_plan.py",
                "scripts/build_learning_apply_plan.py",
                "scripts/execute_learning_apply_plan.py",
            ],
        },
    }


def _markdown(packet: dict[str, Any]) -> str:
    recommendation = packet["recommendation"]
    evidence = packet["evidence_summary"]
    lines = [
        "# Phase 5 Argus Recommendation Review",
        "",
        f"Gate status: `{packet['gate_status']}`",
        f"Reviewed by: `{packet['reviewed_by']}`",
        f"Reviewed at: `{packet['reviewed_at']}`",
        "",
        "## Recommendation",
        "",
        recommendation["action"],
        "",
        "## Why Argus Is Saying This",
        "",
        recommendation.get("top_insight") or "No top insight supplied.",
        "",
        "## Evidence Summary",
        "",
        f"- Recommendations: {evidence.get('recommendation_count')}",
        f"- Product-market patterns: {evidence.get('pattern_count')}",
        f"- Audience demand signals: {evidence.get('demand_signal_count')}",
        f"- Rising demand topics: {evidence.get('rising_demand_topic_count')}",
        f"- Matched demand topics: {evidence.get('matched_demand_topic_count')}",
        "",
        "## Demand Topics",
        "",
    ]
    for topic in packet.get("demand_topics", []):
        lines.extend(
            [
                f"- {topic.get('topic')}: {topic.get('value')} {topic.get('metric')}, change {topic.get('change_pct')}",
            ]
        )
    if not packet.get("demand_topics"):
        lines.append("- None")
    lines.extend(["", "## Confidence Limits", ""])
    for limit in packet.get("confidence_limits", []):
        lines.append(f"- {limit}")
    if not packet.get("confidence_limits"):
        lines.append("- None")
    lines.extend(["", "## Acceptance Rubric", ""])
    for item in packet["acceptance_rubric"]:
        lines.append(f"- {item['dimension']}: {item['question']}")
    lines.extend(["", "## Learning Effect", "", packet["learning_effect"]["required_next_proof"], ""])
    return "\n".join(lines)


def export_review_packet(
    dashboard_path: Path,
    *,
    output: Path,
    markdown_output: Path | None,
    reviewed_by: str,
    decision: str,
) -> dict[str, Any]:
    packet = build_review_packet(dashboard_path, reviewed_by=reviewed_by, decision=decision)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(packet, indent=2, sort_keys=True)}\n", encoding="utf-8")
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_markdown(packet), encoding="utf-8")
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", required=True, type=Path, help="Path to argus-dashboard.json")
    parser.add_argument("--output", required=True, type=Path, help="Output review packet JSON path")
    parser.add_argument("--markdown-output", type=Path, help="Optional Markdown review packet path")
    parser.add_argument("--reviewed-by", default="codex")
    parser.add_argument("--decision", choices=sorted(VALID_DECISIONS), default="awaiting_human_acceptance")
    args = parser.parse_args(argv)

    export_review_packet(
        args.dashboard,
        output=args.output,
        markdown_output=args.markdown_output,
        reviewed_by=args.reviewed_by,
        decision=args.decision,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
