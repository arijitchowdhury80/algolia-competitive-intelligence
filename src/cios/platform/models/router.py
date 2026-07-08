"""ModelRouter — the ONLY thing that maps capability + tier to a concrete
provider/model. Skills declare capability needs; they never reference a
provider or model id directly (docs/planning/CI-OS-Fable-build-goal-spec.md
section 6).

Config shape (config/model-routing.yaml):

    tiers:
      default:  {provider: google, model_id: gemini-flash-lite}
      standard: {provider: google, model_id: gemini-flash}
      high:     {provider: anthropic-cli, model_id: sonnet}
      judgment: {provider: anthropic-cli, model_id: opus}
    tenant_overrides:
      acme:
        high: {provider: google, model_id: gemini-pro-high}
    escalation_rules:
      needs_long_context: standard
      needs_json_mode: standard
      needs_vision: high

Only ONE routing config file governs routing (env-and-secrets-spec "one
routing config file" rule) — this class takes an overridable path but the
canonical instance always points at config/model-routing.yaml.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from .types import TIER_ORDER, ModelRunRecord, ModelSelection, Tier

DEFAULT_CONFIG_PATH = Path("config/model-routing.yaml")


class ModelRouter:
    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._config = self._load_config(self.config_path)

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data

    def _tier_entry(self, tier: Tier, tenant_id: Optional[str]) -> dict[str, str]:
        tiers = self._config.get("tiers", {})
        entry = dict(tiers.get(tier, {}))

        if tenant_id:
            overrides = self._config.get("tenant_overrides", {}) or {}
            tenant_cfg = overrides.get(tenant_id, {}) or {}
            tenant_tier_entry = tenant_cfg.get(tier)
            if tenant_tier_entry:
                entry.update(tenant_tier_entry)

        return entry

    def _minimum_tier_for_needs(self, capability_needs: list[str]) -> tuple[Tier, Optional[str]]:
        """Return the lowest tier index satisfying all escalation rules,
        plus a human-readable reason if escalation above 'default' happened."""
        escalation_rules = self._config.get("escalation_rules", {}) or {}

        min_tier: Tier = "default"
        reasons: list[str] = []

        for need in capability_needs:
            required_tier = escalation_rules.get(need)
            if not required_tier:
                continue
            if TIER_ORDER.index(required_tier) > TIER_ORDER.index(min_tier):
                min_tier = required_tier
            reasons.append(f"{need} requires tier>={required_tier}")

        reason = "; ".join(reasons) if reasons and min_tier != "default" else None
        return min_tier, reason

    def select_model(
        self,
        task_profile: str,
        capability_needs: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        tenant_policy: Optional[dict[str, Any]] = None,
        budget_cents: Optional[float] = None,
        latency_target_ms: Optional[int] = None,
    ) -> ModelSelection:
        capability_needs = capability_needs or []
        tier, reason = self._minimum_tier_for_needs(capability_needs)
        escalated = tier != "default"

        entry = self._tier_entry(tier, tenant_id)
        provider = entry.get("provider", "")
        model_id = entry.get("model_id", "")

        return ModelSelection(
            tier=tier,
            provider=provider,
            model_id=model_id,
            escalated=escalated,
            escalation_reason=reason if escalated else None,
        )

    def record_run(
        self,
        selection: ModelSelection,
        task_profile: str,
        tenant_id: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: float = 0.0,
        cost_cents: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> ModelRunRecord:
        now = datetime.now(timezone.utc)
        return ModelRunRecord(
            tenant_id=tenant_id,
            task_profile=task_profile,
            tier=selection.tier,
            provider=selection.provider,
            model_id=selection.model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            cost_cents=cost_cents,
            escalated=selection.escalated,
            escalation_reason=selection.escalation_reason,
            success=success,
            error=error,
            started_at=started_at or now,
            finished_at=finished_at or now,
        )
