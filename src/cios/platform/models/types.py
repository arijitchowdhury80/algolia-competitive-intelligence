"""Shared data types for the CI-OS model-provider abstraction layer.

See docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md
(ModelProvider / ModelRouter interface sketch) and
docs/planning/CI-OS-Fable-build-goal-spec.md section 6 (skills declare
CAPABILITY needs, never concrete provider model ids) for the source spec.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Capability need strings used across skills, router config, and providers.
# Skills declare these — never a concrete provider/model id.
CAPABILITY_NEEDS = (
    "needs_json_mode",
    "needs_vision",
    "needs_long_context",
    "needs_tool_use",
)

Tier = Literal["default", "standard", "high", "judgment"]

TIER_ORDER: tuple[Tier, ...] = ("default", "standard", "high", "judgment")


class ChatMessage(BaseModel):
    """A single chat-style message (role + content)."""

    role: Literal["system", "user", "assistant"]
    content: str


class ModelRequest(BaseModel):
    """A provider-agnostic request to generate a model response."""

    task_profile: str
    capability_needs: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    messages: Optional[list[ChatMessage]] = None
    max_tokens: Optional[int] = None
    json_schema: Optional[dict[str, Any]] = None
    tenant_id: Optional[str] = None
    latency_target_ms: Optional[int] = None
    budget_cents: Optional[float] = None

    @model_validator(mode="after")
    def _require_prompt_or_messages(self) -> "ModelRequest":
        if not self.prompt and not self.messages:
            raise ValueError("ModelRequest requires at least one of: prompt, messages")
        return self


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelResponse(BaseModel):
    text: str
    parsed_json: Optional[dict[str, Any]] = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float
    provider: str
    provider_model_id: str
    raw: Optional[dict[str, Any]] = None


class ProviderHealth(BaseModel):
    healthy: bool
    provider: str
    checked_at: datetime
    detail: Optional[str] = None
    latency_ms: Optional[float] = None


class ModelSelection(BaseModel):
    tier: Tier
    provider: str
    model_id: str
    escalated: bool = False
    escalation_reason: Optional[str] = None


class ModelRunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: Optional[str] = None
    task_profile: str
    tier: Tier
    provider: str
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    cost_cents: Optional[float] = None
    escalated: bool = False
    escalation_reason: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    started_at: datetime
    finished_at: datetime
