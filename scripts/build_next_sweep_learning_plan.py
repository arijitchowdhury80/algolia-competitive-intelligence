#!/usr/bin/env python3
"""Build the Hermes-facing next-sweep learning plan.

This command is intentionally part of the CI-OS package, not Hermes core.
Hermes can call it before a daily sweep to turn approved Argus learning items
into a machine-readable instruction artifact. It does not auto-apply code,
source, threshold, or prompt changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.db.session import get_dsn, tenant_context
from cios.learn.apply import load_approved_policy_instructions
from cios.learn.feedback import NextSweepInstruction, NextSweepPlan, NextSweepPlanner
from cios.learn.types import ImprovementItem, ImprovementPriority, ImprovementStatus


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    return int(row["id"])


def _improvement_from_row(row) -> ImprovementItem:
    return ImprovementItem(
        id=int(row["id"]),
        tenant_id=int(row["tenant_id"]),
        source=row["source"],
        problem=row["problem"],
        proposed_fix=row["proposed_fix"],
        priority=ImprovementPriority(row["priority"] or ImprovementPriority.MEDIUM.value),
        status=ImprovementStatus(row["status"]),
        created_at=row["created_at"],
    )


def load_approved_improvements(conn, tenant_id: int) -> list[ImprovementItem]:
    with tenant_context(conn, tenant_id):
        rows = conn.execute(
            """
            SELECT id, tenant_id, source, problem, proposed_fix, priority, status, created_at
            FROM improvement_queue
            WHERE tenant_id = %s
              AND status = 'approved'
            ORDER BY
              CASE priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
              END,
              id
            """,
            (tenant_id,),
        ).fetchall()
    return [_improvement_from_row(row) for row in rows]


def load_learning_evidence_ids(conn, tenant_id: int, items: list[ImprovementItem]) -> dict[int, list[int]]:
    evidence_by_item: dict[int, list[int]] = {}
    for item in items:
        if item.id is None:
            continue
        with tenant_context(conn, tenant_id):
            rows = conn.execute(
                """
                SELECT id
                FROM learning_events
                WHERE tenant_id = %s
                  AND lesson = %s
                  AND proposed_change IS NOT DISTINCT FROM %s
                ORDER BY id
                """,
                (tenant_id, item.problem, item.proposed_fix),
            ).fetchall()
        evidence_by_item[item.id] = [int(row["id"]) for row in rows]
    return evidence_by_item


def build_learning_plan_payload(
    *,
    tenant_id: int,
    items: list[ImprovementItem],
    evidence_by_item: dict[int, list[int]],
    policy_instructions: list[dict] | None = None,
) -> dict:
    plan = NextSweepPlanner().build(
        tenant_id=tenant_id,
        items=items,
        evidence_by_item=evidence_by_item,
    )
    instructions = list(plan.instructions)
    skipped = list(plan.skipped)
    seen = {_instruction_key(instruction) for instruction in instructions}
    metadata = {
        "db_instruction_count": len(instructions),
        "approved_policy_count": 0,
        "policy_instruction_count": 0,
        "duplicate_policy_instruction_count": 0,
        "skipped_policy_instruction_count": 0,
        "policy_sources": [],
    }

    for raw_instruction in policy_instructions or []:
        instruction = NextSweepInstruction.model_validate(raw_instruction)
        policy_source = _policy_source(raw_instruction, status="loaded")
        metadata["approved_policy_count"] += 1
        if instruction.tenant_id != tenant_id:
            skipped.append(
                {
                    "source_improvement_ids": list(instruction.source_improvement_ids),
                    "reason": "policy instruction tenant_id does not match plan tenant_id",
                }
            )
            policy_source["status"] = "skipped_tenant_mismatch"
            metadata["skipped_policy_instruction_count"] += 1
            metadata["policy_sources"].append(policy_source)
            continue
        key = _instruction_key(instruction)
        if key in seen:
            policy_source["status"] = "duplicate_existing_instruction"
            metadata["duplicate_policy_instruction_count"] += 1
            metadata["policy_sources"].append(policy_source)
            continue
        seen.add(key)
        instructions.append(instruction)
        metadata["policy_instruction_count"] += 1
        metadata["policy_sources"].append(policy_source)

    merged = NextSweepPlan(
        tenant_id=tenant_id,
        instructions=instructions,
        skipped=skipped,
        metadata=metadata,
    )
    return merged.model_dump(mode="json")


def _instruction_key(instruction: NextSweepInstruction) -> tuple:
    return (
        instruction.kind.value,
        tuple(instruction.source_improvement_ids),
        tuple(instruction.evidence_event_ids),
    )


def _policy_source(raw_instruction: dict, *, status: str) -> dict:
    return {
        "action_id": raw_instruction.get("policy_action_id"),
        "target": raw_instruction.get("policy_target"),
        "package_path": raw_instruction.get("policy_package_path"),
        "approved_by": raw_instruction.get("policy_approved_by"),
        "kind": str(raw_instruction.get("kind") or ""),
        "summary": str(raw_instruction.get("summary") or ""),
        "status": status,
        "evidence_event_ids": _int_list(raw_instruction.get("evidence_event_ids")),
        "source_improvement_ids": _int_list(raw_instruction.get("source_improvement_ids")),
    }


def _int_list(value) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def load_policy_instructions(package_root: Path, *, tenant_id: int) -> list[dict]:
    return load_approved_policy_instructions(package_root, tenant_id=tenant_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example algolia")
    parser.add_argument(
        "--package-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Installed CI-OS package root for approved learning policy overlays.",
    )
    parser.add_argument("--output", help="Optional JSON artifact path. Prints to stdout when omitted.")
    args = parser.parse_args(argv)

    with psycopg.connect(get_dsn(), autocommit=True, row_factory=dict_row) as conn:
        tenant_id = resolve_tenant_id(conn, args.tenant)
        items = load_approved_improvements(conn, tenant_id)
        evidence_by_item = load_learning_evidence_ids(conn, tenant_id, items)
        payload = build_learning_plan_payload(
            tenant_id=tenant_id,
            items=items,
            evidence_by_item=evidence_by_item,
            policy_instructions=load_policy_instructions(args.package_root, tenant_id=tenant_id),
        )

    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{encoded}\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
