"""Argus product-market intelligence spine.

This package is the bridge between collected evidence and the UI/briefing
surfaces: it fuses product reality, market conversation, and demand signals
into patterns and owner-specific recommendations. No DB or network lives here.
"""

from .product_market import ProductMarketSynthesizer
from .product_surface_planner import ProductSurfaceExportPlanItem, plan_product_surface_exports
from .feature_matrix import (
    ProductFeatureComparisonRead,
    ProductFeatureComparisonRow,
    build_product_feature_comparison_read,
    derive_feature_positions_from_product_events,
)
from .workflow import ProductMarketIntelligenceWorkflow, ProductMarketLedger
from .adapters import (
    conversation_record_to_conversation_theme,
    looker_row_to_demand_signal,
    scout_record_to_product_change_event,
)
from .inputs import ProductMarketInputBatch, build_product_market_input_batch
from .importers import build_payload_from_exports, load_export_records
from .scout_adapter import ScoutCommandSpec, ScoutExecutionError, run_scout_export
from .scout_surface_exporter import (
    ProductSurfaceTarget,
    ScoutSurfaceExtractionError,
    scout_extract_response_to_product_records,
)
from .runner import (
    ProductMarketIntelligenceBrief,
    ProductMarketRunPayload,
    ProductMarketRunSummary,
    build_product_market_intelligence_brief,
    load_product_market_payload,
    run_product_market_payload,
)
from .types import (
    ConversationTheme,
    DemandSignal,
    EvidenceRef,
    FeaturePosition,
    ProductChangeEvent,
    ProductMarketResult,
    Recommendation,
    RecommendationScorecard,
    RubricDimensionScore,
    SourceMethod,
)

__all__ = [
    "ProductMarketSynthesizer",
    "ProductMarketIntelligenceWorkflow",
    "ProductMarketLedger",
    "ProductMarketInputBatch",
    "ProductMarketIntelligenceBrief",
    "ProductMarketRunPayload",
    "ProductMarketRunSummary",
    "ProductFeatureComparisonRead",
    "ProductFeatureComparisonRow",
    "ProductSurfaceExportPlanItem",
    "ConversationTheme",
    "DemandSignal",
    "EvidenceRef",
    "FeaturePosition",
    "ProductChangeEvent",
    "ProductMarketResult",
    "Recommendation",
    "RecommendationScorecard",
    "RubricDimensionScore",
    "SourceMethod",
    "ScoutCommandSpec",
    "ScoutExecutionError",
    "ProductSurfaceTarget",
    "ScoutSurfaceExtractionError",
    "build_product_market_input_batch",
    "build_payload_from_exports",
    "derive_feature_positions_from_product_events",
    "build_product_feature_comparison_read",
    "build_product_market_intelligence_brief",
    "load_export_records",
    "load_product_market_payload",
    "run_product_market_payload",
    "run_scout_export",
    "plan_product_surface_exports",
    "scout_extract_response_to_product_records",
    "conversation_record_to_conversation_theme",
    "looker_row_to_demand_signal",
    "scout_record_to_product_change_event",
]
