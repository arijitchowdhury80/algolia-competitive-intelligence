"""Deterministic product-market synthesis for Argus.

This is not the LLM layer. It is the evidence gate and first-pass reasoning
layer that tells Argus which signals are eligible to become intelligence:
shipping evidence plus conversation can create a watch pattern, but demand
evidence is required before an action is promoted.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .capabilities import capability_key, demand_capability_key
from .demand_quality import DEMAND_CHANGE_FLOOR, DEMAND_VALUE_FLOOR, is_rising_demand_signal
from .types import (
    ConversationTheme,
    DemandSignal,
    EvidenceRef,
    PatternObservation,
    ProductChangeEvent,
    ProductMarketResult,
    Recommendation,
    RecommendationScorecard,
    RubricDimensionScore,
)


def _dedupe_evidence(items: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    seen: set[str] = set()
    out: list[EvidenceRef] = []
    for item in items:
        if item.source_url in seen:
            continue
        seen.add(item.source_url)
        out.append(item)
    return out


def _evidence_urls(items: Iterable[EvidenceRef], limit: int | None = None) -> list[str]:
    urls: list[str] = []
    for item in _dedupe_evidence(items):
        urls.append(item.source_url)
        if limit is not None and len(urls) >= limit:
            break
    return urls


class ProductMarketSynthesizer:
    """Fuses product reality, conversation, and demand into Argus patterns.

    The point is to prevent the old failure mode where a loud conversation was
    treated as action. Conversation plus product proof can become a watch
    pattern; demand is required before Argus promotes an owner action.
    """

    def __init__(
        self,
        demand_floor: float = DEMAND_CHANGE_FLOOR,
        demand_value_floor: float = DEMAND_VALUE_FLOOR,
    ) -> None:
        self._demand_floor = demand_floor
        self._demand_value_floor = demand_value_floor

    def synthesize(
        self,
        *,
        tenant_id: int,
        own_company_name: str,
        product_events: list[ProductChangeEvent],
        conversation_themes: list[ConversationTheme],
        demand_signals: list[DemandSignal],
    ) -> ProductMarketResult:
        product_by_cap = self._group_product(product_events)
        conversation_by_cap = self._group_conversation(conversation_themes)
        demand_by_cap = self._group_rising_demand(demand_signals)

        patterns: list[PatternObservation] = []
        recommendations: list[Recommendation] = []
        capabilities = sorted(set(product_by_cap) | set(conversation_by_cap) | set(demand_by_cap))

        for capability_key in capabilities:
            products = product_by_cap.get(capability_key, [])
            conversations = conversation_by_cap.get(capability_key, [])
            demands = demand_by_cap.get(capability_key, [])
            own_products = [p for p in products if p.company_role == "own"]
            competitor_products = [p for p in products if p.company_role == "competitor"]
            own_conversations = [
                c for c in conversations if (c.company_name or "").lower() == own_company_name.lower()
            ]
            competitor_conversations = [
                c for c in conversations if (c.company_name or "").lower() != own_company_name.lower()
            ]

            if not demands:
                if competitor_products and competitor_conversations:
                    evidence = _dedupe_evidence(
                        [
                            *(e for p in competitor_products for e in p.evidence),
                            *(e for c in competitor_conversations for e in c.evidence),
                        ]
                    )
                    companies = sorted({p.company_name for p in competitor_products})
                    label = self._display_capability(products, conversations, demands, capability_key)
                    patterns.append(
                        PatternObservation(
                            tenant_id=tenant_id,
                            pattern_type="competitive_pressure",
                            capability=label,
                            summary=(
                                f"{', '.join(companies)} has product proof and public positioning around "
                                f"{label}, but Argus has no tenant-side demand evidence in this run; "
                                "watch the movement, do not promote action yet."
                            ),
                            involved_companies=companies,
                            confidence=0.58,
                            evidence=evidence,
                        )
                    )
                continue

            if competitor_products and competitor_conversations and own_products and not own_conversations:
                evidence = _dedupe_evidence(
                    [
                        *(e for p in competitor_products for e in p.evidence),
                        *(e for c in competitor_conversations for e in c.evidence),
                        *(e for d in demands for e in d.evidence),
                        *(e for p in own_products for e in p.evidence),
                    ]
                )
                companies = sorted({p.company_name for p in competitor_products})
                label = self._display_capability(products, conversations, demands, capability_key)
                pattern = PatternObservation(
                    tenant_id=tenant_id,
                    pattern_type="own_narrative_gap",
                    capability=label,
                    summary=(
                        f"{', '.join(companies)} is shipping and saying {label}, while "
                        f"{own_company_name} has product proof but no matching narrative in this evidence set."
                    ),
                    involved_companies=[own_company_name, *companies],
                    confidence=0.78,
                    evidence=evidence,
                )
                patterns.append(pattern)
                recommendations.append(
                    Recommendation(
                        tenant_id=tenant_id,
                        owner="PMM",
                        action=(
                            f"Create an evidence-backed {label} narrative that connects "
                            f"{own_company_name}'s shipped capability to rising audience demand."
                        ),
                        why_now=(
                            "A competitor has release proof and public positioning while tenant-side "
                            "demand is rising, so silence creates a narrative gap."
                        ),
                        urgency="this_week",
                        confidence=pattern.confidence,
                        scorecard=self._score_narrative_gap(
                            own_company_name=own_company_name,
                            competitor_names=companies,
                            competitor_products=competitor_products,
                            competitor_conversations=competitor_conversations,
                            own_products=own_products,
                            demands=demands,
                            evidence=evidence,
                        ),
                        evidence=evidence,
                    )
                )
                continue

            if competitor_products and competitor_conversations and not own_products:
                evidence = _dedupe_evidence(
                    [
                        *(e for p in competitor_products for e in p.evidence),
                        *(e for c in competitor_conversations for e in c.evidence),
                        *(e for d in demands for e in d.evidence),
                    ]
                )
                companies = sorted({p.company_name for p in competitor_products})
                label = self._display_capability(products, conversations, demands, capability_key)
                pattern = PatternObservation(
                    tenant_id=tenant_id,
                    pattern_type="own_product_gap",
                    capability=label,
                    summary=(
                        f"{', '.join(companies)} has release proof and public positioning around "
                        f"{label}, but {own_company_name} has no product proof in this evidence set."
                    ),
                    involved_companies=[own_company_name, *companies],
                    confidence=0.74,
                    evidence=evidence,
                )
                patterns.append(pattern)
                recommendations.append(
                    Recommendation(
                        tenant_id=tenant_id,
                        owner="Product",
                        action=(
                            f"Audit whether {own_company_name} has a provable {label} capability; "
                            "if yes, add public evidence, and if no, open a product gap review."
                        ),
                        why_now=(
                            "Competitor product proof, competitor narrative, and audience demand all align."
                        ),
                        urgency="this_week",
                        confidence=pattern.confidence,
                        scorecard=self._score_product_gap(
                            own_company_name=own_company_name,
                            competitor_names=companies,
                            competitor_products=competitor_products,
                            competitor_conversations=competitor_conversations,
                            demands=demands,
                            evidence=evidence,
                        ),
                        evidence=evidence,
                    )
                )
                continue

            if competitor_conversations and not competitor_products:
                evidence = _dedupe_evidence(
                    [
                        *(e for c in competitor_conversations for e in c.evidence),
                        *(e for d in demands for e in d.evidence),
                    ]
                )
                companies = sorted({c.company_name or "market" for c in competitor_conversations})
                label = self._display_capability(products, conversations, demands, capability_key)
                patterns.append(
                    PatternObservation(
                        tenant_id=tenant_id,
                        pattern_type="conversation_without_product_proof",
                        capability=label,
                        summary=(
                            f"{', '.join(companies)} is talking about {label}, but Argus has "
                            "conversation evidence, not release proof; watch it, do not act as if it shipped."
                        ),
                        involved_companies=companies,
                        confidence=0.52,
                        evidence=evidence,
                    )
                )
                continue

            if competitor_products and not competitor_conversations and not own_products:
                evidence = _dedupe_evidence(
                    [
                        *(e for p in competitor_products for e in p.evidence),
                        *(e for d in demands for e in d.evidence),
                    ]
                )
                companies = sorted({p.company_name for p in competitor_products})
                label = self._display_capability(products, conversations, demands, capability_key)
                pattern = PatternObservation(
                    tenant_id=tenant_id,
                    pattern_type="own_product_gap",
                    capability=label,
                    summary=(
                        f"{', '.join(companies)} has release proof for {label} and rising audience "
                        f"demand, but no captured public positioning and no {own_company_name} "
                        "product proof in this evidence set."
                    ),
                    involved_companies=[own_company_name, *companies],
                    confidence=0.66,
                    evidence=evidence,
                )
                patterns.append(pattern)
                recommendations.append(
                    Recommendation(
                        tenant_id=tenant_id,
                        owner="Product",
                        action=(
                            f"Audit whether {own_company_name} can prove {label}; competitor "
                            "release evidence and audience demand are already aligned."
                        ),
                        why_now=(
                            "Competitor release proof and audience demand align even though market "
                            "conversation is quiet."
                        ),
                        urgency="this_week",
                        confidence=pattern.confidence,
                        scorecard=self._score_release_only_product_gap(
                            own_company_name=own_company_name,
                            competitor_names=companies,
                            competitor_products=competitor_products,
                            demands=demands,
                            evidence=evidence,
                        ),
                        evidence=evidence,
                    )
                )
                continue

            if own_products and not own_conversations:
                evidence = _dedupe_evidence(
                    [
                        *(e for p in own_products for e in p.evidence),
                        *(e for d in demands for e in d.evidence),
                    ]
                )
                label = self._display_capability(products, conversations, demands, capability_key)
                pattern = PatternObservation(
                    tenant_id=tenant_id,
                    pattern_type="product_without_market_conversation",
                    capability=label,
                    summary=(
                        f"{own_company_name} has product proof for {label} and rising audience demand, "
                        "but no matching narrative in this evidence set."
                    ),
                    involved_companies=[own_company_name],
                    confidence=0.68,
                    evidence=evidence,
                )
                patterns.append(pattern)
                recommendations.append(
                    Recommendation(
                        tenant_id=tenant_id,
                        owner="PMM",
                        action=(
                            f"Turn the shipped {label} capability into an evidence-backed market "
                            "narrative before the demand window cools."
                        ),
                        why_now=(
                            "Product reality and audience demand align, but the captured conversation "
                            "does not yet explain the capability."
                        ),
                        urgency="this_week",
                        confidence=pattern.confidence,
                        scorecard=self._score_product_without_conversation(
                            own_company_name=own_company_name,
                            own_products=own_products,
                            demands=demands,
                            evidence=evidence,
                        ),
                        evidence=evidence,
                    )
                )

        verdict = "actionable" if recommendations else ("watch" if patterns else "quiet")
        return ProductMarketResult(
            tenant_id=tenant_id,
            verdict=verdict,
            patterns=patterns,
            recommendations=recommendations,
        )

    @staticmethod
    def _group_product(events: list[ProductChangeEvent]) -> dict[str, list[ProductChangeEvent]]:
        grouped: dict[str, list[ProductChangeEvent]] = defaultdict(list)
        for event in events:
            grouped[capability_key(event.capability)].append(event)
        return dict(grouped)

    @staticmethod
    def _group_conversation(themes: list[ConversationTheme]) -> dict[str, list[ConversationTheme]]:
        grouped: dict[str, list[ConversationTheme]] = defaultdict(list)
        for theme in themes:
            grouped[capability_key(theme.theme)].append(theme)
        return dict(grouped)

    def _group_rising_demand(self, signals: list[DemandSignal]) -> dict[str, list[DemandSignal]]:
        grouped: dict[str, list[DemandSignal]] = defaultdict(list)
        for signal in signals:
            if is_rising_demand_signal(
                signal,
                change_floor=self._demand_floor,
                value_floor=self._demand_value_floor,
            ):
                key = demand_capability_key(signal.topic, signal.metadata)
                if key:
                    grouped[key].append(signal)
        return dict(grouped)

    @staticmethod
    def _display_capability(
        products: list[ProductChangeEvent],
        conversations: list[ConversationTheme],
        demands: list[DemandSignal],
        fallback: str,
    ) -> str:
        if products:
            return products[0].capability
        if conversations:
            return conversations[0].theme
        if demands:
            return demands[0].topic
        return fallback

    @staticmethod
    def _score_narrative_gap(
        *,
        own_company_name: str,
        competitor_names: list[str],
        competitor_products: list[ProductChangeEvent],
        competitor_conversations: list[ConversationTheme],
        own_products: list[ProductChangeEvent],
        demands: list[DemandSignal],
        evidence: list[EvidenceRef],
    ) -> RecommendationScorecard:
        competitor_label = ", ".join(competitor_names)
        return RecommendationScorecard(
            total_score=78,
            verdict="actionable",
            summary="Competitor product proof, public narrative, and audience demand all align.",
            dimension_scores=[
                RubricDimensionScore(
                    dimension="product_reality",
                    score=20,
                    max_score=25,
                    rationale=f"{competitor_label} has release evidence and {own_company_name} has product proof.",
                    evidence_urls=[
                        *_evidence_urls(e for product in competitor_products for e in product.evidence),
                        *_evidence_urls(e for product in own_products for e in product.evidence),
                    ],
                ),
                RubricDimensionScore(
                    dimension="market_conversation",
                    score=18,
                    max_score=20,
                    rationale=f"{competitor_label} is publicly positioning the theme.",
                    evidence_urls=_evidence_urls(e for theme in competitor_conversations for e in theme.evidence),
                ),
                RubricDimensionScore(
                    dimension="audience_demand",
                    score=20,
                    max_score=20,
                    rationale="Tenant audience demand is rising on the same capability.",
                    evidence_urls=_evidence_urls(e for signal in demands for e in signal.evidence),
                ),
                RubricDimensionScore(
                    dimension="own_response_gap",
                    score=10,
                    max_score=15,
                    rationale=f"{own_company_name} has proof but no matching narrative in this evidence set.",
                    evidence_urls=_evidence_urls(e for product in own_products for e in product.evidence),
                ),
                RubricDimensionScore(
                    dimension="evidence_breadth",
                    score=10,
                    max_score=20,
                    rationale=f"{len(evidence)} distinct evidence refs support the recommendation.",
                    evidence_urls=_evidence_urls(evidence),
                ),
            ],
        )

    @staticmethod
    def _score_product_gap(
        *,
        own_company_name: str,
        competitor_names: list[str],
        competitor_products: list[ProductChangeEvent],
        competitor_conversations: list[ConversationTheme],
        demands: list[DemandSignal],
        evidence: list[EvidenceRef],
    ) -> RecommendationScorecard:
        competitor_label = ", ".join(competitor_names)
        return RecommendationScorecard(
            total_score=74,
            verdict="actionable",
            summary="Competitor product proof, public narrative, and audience demand align while own product proof is missing.",
            dimension_scores=[
                RubricDimensionScore(
                    dimension="product_reality",
                    score=22,
                    max_score=25,
                    rationale=f"{competitor_label} has release evidence while {own_company_name} has no product proof in this evidence set.",
                    evidence_urls=_evidence_urls(e for product in competitor_products for e in product.evidence),
                ),
                RubricDimensionScore(
                    dimension="market_conversation",
                    score=18,
                    max_score=20,
                    rationale=f"{competitor_label} is publicly positioning the theme.",
                    evidence_urls=_evidence_urls(e for theme in competitor_conversations for e in theme.evidence),
                ),
                RubricDimensionScore(
                    dimension="audience_demand",
                    score=20,
                    max_score=20,
                    rationale="Tenant audience demand is rising on the same capability.",
                    evidence_urls=_evidence_urls(e for signal in demands for e in signal.evidence),
                ),
                RubricDimensionScore(
                    dimension="own_response_gap",
                    score=8,
                    max_score=15,
                    rationale=f"{own_company_name} lacks product proof in the captured evidence.",
                    evidence_urls=_evidence_urls(evidence, limit=3),
                ),
                RubricDimensionScore(
                    dimension="evidence_breadth",
                    score=6,
                    max_score=20,
                    rationale=f"{len(evidence)} distinct evidence refs support the recommendation.",
                    evidence_urls=_evidence_urls(evidence),
                ),
            ],
        )

    @staticmethod
    def _score_release_only_product_gap(
        *,
        own_company_name: str,
        competitor_names: list[str],
        competitor_products: list[ProductChangeEvent],
        demands: list[DemandSignal],
        evidence: list[EvidenceRef],
    ) -> RecommendationScorecard:
        competitor_label = ", ".join(competitor_names)
        return RecommendationScorecard(
            total_score=66,
            verdict="actionable",
            summary=(
                "Competitor release proof and audience demand align, even though public conversation is quiet."
            ),
            dimension_scores=[
                RubricDimensionScore(
                    dimension="product_reality",
                    score=23,
                    max_score=25,
                    rationale=f"{competitor_label} has release evidence.",
                    evidence_urls=_evidence_urls(e for product in competitor_products for e in product.evidence),
                ),
                RubricDimensionScore(
                    dimension="audience_demand",
                    score=20,
                    max_score=20,
                    rationale="Tenant audience demand is rising on the same capability.",
                    evidence_urls=_evidence_urls(e for signal in demands for e in signal.evidence),
                ),
                RubricDimensionScore(
                    dimension="own_response_gap",
                    score=13,
                    max_score=15,
                    rationale=f"{own_company_name} has no product proof in the captured evidence.",
                    evidence_urls=_evidence_urls(evidence, limit=3),
                ),
                RubricDimensionScore(
                    dimension="evidence_breadth",
                    score=10,
                    max_score=20,
                    rationale=f"{len(evidence)} distinct evidence refs support the recommendation.",
                    evidence_urls=_evidence_urls(evidence),
                ),
            ],
        )

    @staticmethod
    def _score_product_without_conversation(
        *,
        own_company_name: str,
        own_products: list[ProductChangeEvent],
        demands: list[DemandSignal],
        evidence: list[EvidenceRef],
    ) -> RecommendationScorecard:
        return RecommendationScorecard(
            total_score=66,
            verdict="actionable",
            summary="Own product proof and audience demand align, but market narrative is missing.",
            dimension_scores=[
                RubricDimensionScore(
                    dimension="product_reality",
                    score=22,
                    max_score=25,
                    rationale=f"{own_company_name} has shipped or documented product proof.",
                    evidence_urls=_evidence_urls(e for product in own_products for e in product.evidence),
                ),
                RubricDimensionScore(
                    dimension="audience_demand",
                    score=20,
                    max_score=20,
                    rationale="Tenant audience demand is rising on the same capability.",
                    evidence_urls=_evidence_urls(e for signal in demands for e in signal.evidence),
                ),
                RubricDimensionScore(
                    dimension="own_response_gap",
                    score=14,
                    max_score=15,
                    rationale=f"{own_company_name} has no matching narrative in the captured evidence.",
                    evidence_urls=_evidence_urls(e for product in own_products for e in product.evidence),
                ),
                RubricDimensionScore(
                    dimension="evidence_breadth",
                    score=10,
                    max_score=20,
                    rationale=f"{len(evidence)} distinct evidence refs support the recommendation.",
                    evidence_urls=_evidence_urls(evidence),
                ),
            ],
        )
