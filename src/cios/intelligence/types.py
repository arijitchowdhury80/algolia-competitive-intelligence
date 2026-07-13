"""Value objects for Argus's product-market intelligence layer.

The existing CI-OS brain reasons over public conversation. This module adds
the missing "muscle" and "demand" planes:

- ProductChangeEvent: what a company actually shipped or documented.
- ConversationTheme: what a company or the market is saying.
- DemandSignal: what the tenant's audience is responding to.

Everything carries evidence. A claim without evidence is not a claim Argus is
allowed to show.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceMethod(str, Enum):
    """How one evidence item was captured."""

    SCOUT_CHANGELOG = "scout_changelog"
    SCOUT_DOCS = "scout_docs"
    SCOUT_PRODUCT_PAGE = "scout_product_page"
    WEB_SCAN = "web_scan"
    LOOKER_EXPORT = "looker_export"
    MANUAL = "manual"


class EvidenceRef(BaseModel):
    """One cited proof point. URLs can be normal URLs or internal source URIs
    such as looker://...; they must still be stable, inspectable references."""

    source_url: str
    captured_at: datetime
    method: SourceMethod
    excerpt: str | None = None

    @model_validator(mode="after")
    def _require_source(self) -> "EvidenceRef":
        if not self.source_url.strip():
            raise ValueError("EvidenceRef requires source_url")
        return self


class _EvidenceBacked(BaseModel):
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_evidence(self) -> "_EvidenceBacked":
        if not self.evidence:
            raise ValueError(f"{self.__class__.__name__} requires evidence")
        return self


class ProductChangeEvent(_EvidenceBacked):
    """A Scout-style product reality event from changelogs, docs, release notes,
    product pages, pricing pages, or API docs."""

    tenant_id: int
    company_id: int
    company_name: str
    company_role: Literal["own", "competitor", "partner"] = "competitor"
    capability: str
    change_type: Literal["release", "docs_update", "pricing_change", "integration", "deprecation"]
    summary: str
    observed_at: datetime

    @model_validator(mode="after")
    def _require_meaningful_fields(self) -> "ProductChangeEvent":
        if not self.company_name.strip():
            raise ValueError("ProductChangeEvent requires company_name")
        if not self.capability.strip():
            raise ValueError("ProductChangeEvent requires capability")
        if not self.summary.strip():
            raise ValueError("ProductChangeEvent requires summary")
        return self


class ConversationTheme(_EvidenceBacked):
    """A market narrative or positioning theme observed in public speech,
    content, launch pages, analyst pages, or similar sources."""

    tenant_id: int
    company_id: int | None = None
    company_name: str | None = None
    theme: str
    summary: str
    intensity: float = Field(ge=0.0, le=1.0)
    observed_at: datetime

    @model_validator(mode="after")
    def _require_theme(self) -> "ConversationTheme":
        if not self.theme.strip():
            raise ValueError("ConversationTheme requires theme")
        if not self.summary.strip():
            raise ValueError("ConversationTheme requires summary")
        return self


class DemandSignal(_EvidenceBacked):
    """A tenant-side audience response signal, typically imported from GA /
    Looker Studio. Demand proves audience response, not competitor movement."""

    tenant_id: int
    topic: str
    metric: str
    value: float
    change_pct: float | None = None
    period_start: datetime
    period_end: datetime
    source_label: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_topic_and_metric(self) -> "DemandSignal":
        if not self.topic.strip():
            raise ValueError("DemandSignal requires topic")
        if not self.metric.strip():
            raise ValueError("DemandSignal requires metric")
        if not self.source_label.strip():
            raise ValueError("DemandSignal requires source_label")
        return self

    @property
    def is_rising(self) -> bool:
        return self.change_pct is not None and self.change_pct > 0


class FeaturePosition(_EvidenceBacked):
    """Current product-muscle matrix position for one company and one
    capability. This is derived from product reality, not from market talk."""

    tenant_id: int
    company_id: int
    company_name: str
    company_role: Literal["own", "competitor", "partner"] = "competitor"
    capability: str
    position_status: Literal["unknown", "proven", "claimed", "gap", "disproven"] = "proven"
    summary: str
    last_seen_at: datetime
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_position_fields(self) -> "FeaturePosition":
        if not self.company_name.strip():
            raise ValueError("FeaturePosition requires company_name")
        if not self.capability.strip():
            raise ValueError("FeaturePosition requires capability")
        if not self.summary.strip():
            raise ValueError("FeaturePosition requires summary")
        return self


class PatternObservation(_EvidenceBacked):
    """A cross-plane observation Argus can explain and show in the UI."""

    tenant_id: int
    pattern_type: Literal[
        "own_narrative_gap",
        "own_product_gap",
        "product_without_market_conversation",
        "conversation_without_product_proof",
        "competitive_pressure",
    ]
    capability: str
    summary: str
    involved_companies: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class RubricDimensionScore(BaseModel):
    """One explicit scoring dimension behind an Argus recommendation."""

    dimension: Literal[
        "product_reality",
        "market_conversation",
        "audience_demand",
        "own_response_gap",
        "evidence_breadth",
    ]
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    rationale: str
    evidence_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_valid_dimension(self) -> "RubricDimensionScore":
        if self.score > self.max_score:
            raise ValueError("rubric dimension score cannot exceed max_score")
        if not self.rationale.strip():
            raise ValueError("rubric dimension requires rationale")
        if not self.evidence_urls:
            raise ValueError("rubric dimension requires evidence_urls")
        if any(not url.strip() for url in self.evidence_urls):
            raise ValueError("rubric dimension evidence_urls cannot be blank")
        return self


class RecommendationScorecard(BaseModel):
    """The backend confidence rubric persisted with every recommendation."""

    total_score: int = Field(ge=0, le=100)
    verdict: Literal["actionable", "watch", "insufficient"]
    summary: str
    dimension_scores: list[RubricDimensionScore] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_consistent_total(self) -> "RecommendationScorecard":
        if not self.summary.strip():
            raise ValueError("scorecard requires summary")
        if not self.dimension_scores:
            raise ValueError("scorecard requires dimension_scores")
        dimension_total = sum(dimension.score for dimension in self.dimension_scores)
        if dimension_total != self.total_score:
            raise ValueError("scorecard dimension score total must equal total_score")
        return self


class Recommendation(_EvidenceBacked):
    """A role-specific action produced from a PatternObservation."""

    tenant_id: int
    owner: Literal["PMM", "Product", "Sales", "Content", "Executive"]
    action: str
    why_now: str
    urgency: Literal["act_now", "this_week", "this_month"] = "this_week"
    confidence: float = Field(ge=0.0, le=1.0)
    scorecard: RecommendationScorecard

    @model_validator(mode="after")
    def _require_action(self) -> "Recommendation":
        if not self.action.strip():
            raise ValueError("Recommendation requires action")
        if not self.why_now.strip():
            raise ValueError("Recommendation requires why_now")
        if self.scorecard is None:
            raise ValueError("Recommendation requires scorecard")
        return self


class ProductMarketResult(BaseModel):
    tenant_id: int
    verdict: Literal["actionable", "watch", "quiet"]
    patterns: list[PatternObservation] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
