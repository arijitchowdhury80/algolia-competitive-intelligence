"""Run workflow for Argus product-market intelligence.

Hermes can schedule and invoke this package, but the intelligence logic stays
inside CI-OS. The workflow owns the domain sequence: validate tenant scope,
persist evidence inputs, synthesize patterns, then persist Argus actions.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .demand_quality import DemandQualityConfig
from .feature_matrix import derive_feature_positions_from_product_events
from .product_market import ProductMarketSynthesizer
from .types import (
    ConversationTheme,
    DemandSignal,
    FeaturePosition,
    PatternObservation,
    ProductChangeEvent,
    ProductMarketResult,
    Recommendation,
)


class ProductMarketLedger(Protocol):
    def save_product_change_event(self, event: ProductChangeEvent) -> int: ...

    def save_conversation_theme(self, theme: ConversationTheme) -> int: ...

    def save_demand_signal(self, signal: DemandSignal) -> int: ...

    def save_feature_position(self, position: FeaturePosition) -> int: ...

    def save_pattern_observation(self, pattern: PatternObservation) -> int: ...

    def save_recommendation(
        self,
        recommendation: Recommendation,
        *,
        pattern_observation_id: int | None = None,
    ) -> int: ...


class ProductMarketIntelligenceWorkflow:
    """Persist evidence and synthesized intelligence for one tenant run."""

    _ACTION_REVIEW_KINDS = {"scoring_review", "priority_recheck", "evidence_recheck"}
    _DEFAULT_LEARNED_ACTION_THRESHOLD = 80

    def __init__(
        self,
        *,
        repository: ProductMarketLedger,
        synthesizer: ProductMarketSynthesizer | None = None,
    ) -> None:
        self._repository = repository
        self._synthesizer = synthesizer or ProductMarketSynthesizer()

    def run(
        self,
        *,
        tenant_id: int,
        own_company_name: str,
        product_events: list[ProductChangeEvent],
        conversation_themes: list[ConversationTheme],
        demand_signals: list[DemandSignal],
        demand_quality: DemandQualityConfig | None = None,
        learning_instructions: list[Mapping[str, Any]] | None = None,
    ) -> ProductMarketResult:
        self._validate_tenant_scope(
            tenant_id=tenant_id,
            product_events=product_events,
            conversation_themes=conversation_themes,
            demand_signals=demand_signals,
        )

        for event in product_events:
            self._repository.save_product_change_event(event)
        for theme in conversation_themes:
            self._repository.save_conversation_theme(theme)
        for signal in demand_signals:
            self._repository.save_demand_signal(signal)
        for position in derive_feature_positions_from_product_events(product_events):
            self._repository.save_feature_position(position)

        synthesizer = self._synthesizer
        if demand_quality is not None:
            synthesizer = ProductMarketSynthesizer(
                demand_floor=demand_quality.change_floor,
                demand_value_floor=demand_quality.value_floor,
            )
        result = synthesizer.synthesize(
            tenant_id=tenant_id,
            own_company_name=own_company_name,
            product_events=product_events,
            conversation_themes=conversation_themes,
            demand_signals=demand_signals,
        )
        result = self._apply_learning_instructions(result, learning_instructions or [])

        pattern_ids = [self._repository.save_pattern_observation(pattern) for pattern in result.patterns]
        for idx, recommendation in enumerate(result.recommendations):
            pattern_observation_id = pattern_ids[min(idx, len(pattern_ids) - 1)] if pattern_ids else None
            self._repository.save_recommendation(
                recommendation,
                pattern_observation_id=pattern_observation_id,
            )

        return result

    @staticmethod
    def _apply_learning_instructions(
        result: ProductMarketResult,
        instructions: list[Mapping[str, Any]],
    ) -> ProductMarketResult:
        """Apply approved next-sweep learning gates before persistence.

        Coverage recheck instructions are deliberately conservative: they do
        not erase the pattern memory, but they block action promotion because
        the user has challenged whether the monitored universe was complete
        enough to rank priorities.
        """

        kinds = {str(instruction.get("kind") or "") for instruction in instructions}
        if "coverage_recheck" in kinds:
            return result.model_copy(update={"verdict": "watch", "recommendations": []})

        if kinds & ProductMarketIntelligenceWorkflow._ACTION_REVIEW_KINDS:
            threshold = ProductMarketIntelligenceWorkflow._learned_action_threshold(instructions)
            recommendations = [
                recommendation
                for recommendation in result.recommendations
                if recommendation.scorecard.total_score >= threshold
            ]
            if len(recommendations) != len(result.recommendations):
                verdict = "actionable" if recommendations else ("watch" if result.patterns else "quiet")
                return result.model_copy(update={"verdict": verdict, "recommendations": recommendations})
        return result

    @staticmethod
    def _learned_action_threshold(instructions: list[Mapping[str, Any]]) -> int:
        thresholds: list[int] = []
        for instruction in instructions:
            kind = str(instruction.get("kind") or "")
            if kind not in ProductMarketIntelligenceWorkflow._ACTION_REVIEW_KINDS:
                continue
            change = instruction.get("change") if isinstance(instruction.get("change"), Mapping) else {}
            raw_threshold = change.get("action_threshold") if isinstance(change, Mapping) else None
            if raw_threshold is None:
                thresholds.append(ProductMarketIntelligenceWorkflow._DEFAULT_LEARNED_ACTION_THRESHOLD)
                continue
            try:
                thresholds.append(int(raw_threshold))
            except (TypeError, ValueError):
                thresholds.append(ProductMarketIntelligenceWorkflow._DEFAULT_LEARNED_ACTION_THRESHOLD)
        if not thresholds:
            return ProductMarketIntelligenceWorkflow._DEFAULT_LEARNED_ACTION_THRESHOLD
        return max(thresholds)

    @staticmethod
    def _validate_tenant_scope(
        *,
        tenant_id: int,
        product_events: list[ProductChangeEvent],
        conversation_themes: list[ConversationTheme],
        demand_signals: list[DemandSignal],
    ) -> None:
        for item in [*product_events, *conversation_themes, *demand_signals]:
            if item.tenant_id != tenant_id:
                raise ValueError("Product-market workflow input tenant_id does not match run tenant_id")


__all__ = ["ProductMarketIntelligenceWorkflow", "ProductMarketLedger"]
