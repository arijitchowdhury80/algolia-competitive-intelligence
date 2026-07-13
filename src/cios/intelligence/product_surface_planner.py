"""Plan Hermes-executable Scout exports for product surfaces."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, Field

from .scout_surface_exporter import ProductSurfaceTarget


class ProductSurfaceExportPlanItem(BaseModel):
    """One command Hermes can execute to collect product-reality evidence."""

    target: ProductSurfaceTarget
    output_path: Path
    command: list[str]
    learning_priority: int = 0
    learning_reasons: list[str] = Field(default_factory=list)
    focus_capability: str | None = None


def plan_product_surface_exports(
    targets: list[ProductSurfaceTarget],
    *,
    output_dir: Path,
    python_bin: str,
    script_path: Path,
    scout_bin: str,
    provider: str,
    timeout_seconds: float,
    use_js: bool,
    learning_instructions: list[Mapping[str, Any]] | None = None,
    focus_capability: str | None = None,
) -> list[ProductSurfaceExportPlanItem]:
    output_dir = Path(output_dir)
    prioritized_targets = _prioritize_targets(targets, learning_instructions or [])
    plan: list[ProductSurfaceExportPlanItem] = []
    for index, (target, learning_priority, learning_reasons) in enumerate(prioritized_targets, start=1):
        output_path = output_dir / _output_filename(target, index)
        command = [
            python_bin,
            str(script_path),
            "--tenant-id",
            str(target.tenant_id),
            "--company-id",
            str(target.company_id),
            "--company-name",
            target.company_name,
            "--company-role",
            target.company_role,
            "--surface-family",
            target.surface_family,
            "--url",
            target.url,
            "--scout-bin",
            scout_bin,
            "--provider",
            provider,
            "--timeout-seconds",
            _number_arg(timeout_seconds),
        ]
        if use_js:
            command.append("--js")
        if focus_capability and focus_capability.strip():
            command.extend(["--focus-capability", focus_capability.strip()])
        command.extend(["--output", str(output_path)])
        plan.append(
            ProductSurfaceExportPlanItem(
                target=target,
                output_path=output_path,
                command=command,
                learning_priority=learning_priority,
                learning_reasons=learning_reasons,
                focus_capability=focus_capability.strip() if focus_capability and focus_capability.strip() else None,
            )
        )
    return plan


def _prioritize_targets(
    targets: list[ProductSurfaceTarget],
    learning_instructions: list[Mapping[str, Any]],
) -> list[tuple[ProductSurfaceTarget, int, list[str]]]:
    ranked: list[tuple[int, int, ProductSurfaceTarget, list[str]]] = []
    for index, target in enumerate(targets):
        reasons = _coverage_learning_reasons(target, learning_instructions)
        priority = 100 if reasons else 0
        ranked.append((-priority, index, target, reasons))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [(target, -priority_sort, reasons) for priority_sort, _index, target, reasons in ranked]


def _coverage_learning_reasons(
    target: ProductSurfaceTarget,
    learning_instructions: list[Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    target_name = _norm(target.company_name)
    for instruction in learning_instructions:
        if str(instruction.get("kind") or "") != "coverage_recheck":
            continue
        text = _instruction_text(instruction)
        if not target_name or not _coverage_instruction_mentions_target(target_name, text):
            continue
        reason = str(instruction.get("instruction") or instruction.get("summary") or "coverage recheck")
        reasons.append(f"coverage_recheck: {reason}")
    return reasons


def _coverage_instruction_mentions_target(target_name: str, text: str) -> bool:
    normalized = _norm(text)
    phrases = [
        f"re-audit {target_name}",
        f"reaudit {target_name}",
        f"missed {target_name}",
        f"{target_name} source",
        f"{target_name} sources",
        f"{target_name} coverage",
        f"{target_name} entirely",
    ]
    return any(phrase in normalized for phrase in phrases)


def _instruction_text(instruction: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in ("instruction", "summary"):
        value = instruction.get(key)
        if value is not None:
            values.append(str(value))
    change = instruction.get("change")
    if isinstance(change, Mapping):
        for key in ("source", "problem", "proposed_fix"):
            value = change.get(key)
            if value is not None:
                values.append(str(value))
    return " ".join(values)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _output_filename(target: ProductSurfaceTarget, fallback_index: int) -> str:
    stable_id = target.surface_id or fallback_index
    company_slug = _slug(target.company_name)
    return f"{stable_id:06d}-{company_slug}-{target.surface_family}.json"


def _slug(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower())) or "company"


def _number_arg(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


__all__ = ["ProductSurfaceExportPlanItem", "plan_product_surface_exports"]
