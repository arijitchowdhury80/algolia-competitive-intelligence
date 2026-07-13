from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from fastapi.testclient import TestClient

import cios.admin.app as admin_app
import cios.admin.demand_imports as demand_imports
from cios.admin.app import create_app
from cios.admin.learning_apply import LearningApplyArtifactStore
from cios.admin.types import (
    CompetitorCreate,
    CompetitorUpdate,
    ImprovementStatusUpdate,
    ProductSurfaceCreate,
    ProductSurfaceUpdate,
    SourceCreate,
    SourceUpdate,
)
from cios.learn.apply import LearningApplyExecutor
from cios.learn.feedback import LearningApplyAction, LearningApplyPlan, ProposalKind
from cios.learn.recommendation_challenge import RecommendationChallengeResult
from cios.learn.types import ImprovementItem, ImprovementPriority, LearningEvent, LearningEventType


class FakeAdminRepository:
    def __init__(self) -> None:
        self.competitors: list[dict[str, Any]] = [
            {
                "competitor_id": 1,
                "competitor_name": "Constructor",
                "domain": "constructor.com",
                "category": "commerce search",
                "priority": 1,
                "status": "active",
                "sources": [
                    {
                        "source_id": 10,
                        "source_family": "blog",
                        "url": "https://constructor.com/blog",
                        "status": "active",
                        "latest_event_type": "ok",
                        "http_status": 200,
                        "detail": None,
                        "checked_at": None,
                    }
                ],
                "product_surfaces": [
                    {
                        "surface_id": 30,
                        "company_name": "Constructor",
                        "company_role": "competitor",
                        "surface_family": "docs",
                        "url": "https://docs.constructor.com/",
                        "status": "active",
                        "last_checked_at": None,
                    }
                ],
            }
        ]
        self.improvements: list[dict[str, Any]] = [
            {
                "improvement_id": 202,
                "source": "argus_recommendation:7",
                "problem": "User challenged recommendation 7; coverage may be incomplete.",
                "proposed_fix": "Re-evaluate recommendation 7 against source coverage in the next sweep.",
                "priority": "critical",
                "status": "open",
                "created_at": None,
            }
        ]
        self.feature_matrix_rows: list[dict[str, Any]] = [
            {
                "capability_text": "agentic product discovery",
                "company_name": "Constructor",
                "company_role": "competitor",
                "position_status": "proven",
                "summary": "Constructor has product proof for AI shopping agents.",
                "confidence": 0.72,
                "evidence_refs": [{"source_url": "https://constructor.com/changelog"}],
                "updated_at": "2026-07-10T05:13:00+00:00",
            },
            {
                "capability_text": "agentic product discovery",
                "company_name": "Algolia",
                "company_role": "own",
                "position_status": "gap",
                "summary": "No Algolia proof captured in this evidence set.",
                "confidence": 0.41,
                "evidence_refs": [{"source_url": "https://www.algolia.com/docs"}],
                "updated_at": "2026-07-10T05:13:00+00:00",
            },
        ]
        self.recommendations: list[dict[str, Any]] = [
            {
                "recommendation_id": 7,
                "pattern_observation_id": 44,
                "owner": "PMM",
                "action": "Create an evidence-backed AI shopping agent narrative for Algolia.",
                "why_now": "Constructor has product proof, public positioning, and rising audience demand.",
                "urgency": "this_week",
                "confidence": 0.78,
                "scorecard": {
                    "total_score": 78,
                    "verdict": "actionable",
                    "summary": "Product proof, conversation, and demand align.",
                    "dimension_scores": [
                        {
                            "dimension": "product_reality",
                            "score": 20,
                            "max_score": 25,
                            "rationale": "Constructor has release evidence.",
                            "evidence_urls": ["https://constructor.com/changelog"],
                        }
                    ],
                },
                "evidence_refs": [{"source_url": "https://constructor.com/changelog"}],
                "status": "open",
                "created_at": "2026-07-10T05:13:00+00:00",
            }
        ]
        self.evidence_ledger_payload: dict[str, Any] = {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "product_events": [
                {
                    "product_event_id": 501,
                    "company_name": "Constructor",
                    "company_role": "competitor",
                    "capability_text": "AI shopping agents",
                    "change_type": "release",
                    "summary": "Constructor published product proof for AI shopping agents.",
                    "observed_at": "2026-07-10T05:13:00+00:00",
                    "confidence": 0.82,
                    "evidence_refs": [{"source_url": "https://constructor.com/changelog"}],
                }
            ],
            "conversation_themes": [
                {
                    "conversation_theme_id": 601,
                    "company_name": "Constructor",
                    "theme": "AI shopping agents",
                    "summary": "Constructor is positioning AI shopping agents as category infrastructure.",
                    "intensity": 0.74,
                    "observed_at": "2026-07-10T05:14:00+00:00",
                    "evidence_refs": [{"source_url": "https://constructor.com/blog/ai-shopping-agent"}],
                }
            ],
            "demand_signals": [
                {
                    "demand_signal_id": 701,
                    "topic": "AI shopping agents",
                    "metric": "engaged_sessions",
                    "value": 240.0,
                    "change_pct": 0.32,
                    "period_start": "2026-07-01T00:00:00+00:00",
                    "period_end": "2026-07-10T00:00:00+00:00",
                    "source_label": "Looker Studio GA4 export",
                    "evidence_refs": [{"source_url": "looker://algolia/ga4/ai-shopping-agents"}],
                    "metadata": {
                        "source_file": "argus-demand-plan-template.csv",
                        "source_row_number": 1,
                        "source_fingerprint": "b" * 64,
                        "argus_capability_key": "ai shopping agents",
                        "argus_assessment": "own_product_gap",
                        "argus_suggested_filters": ["AI shopping agents", "shopping agent"],
                        "argus_related_competitors": ["Constructor", "Elastic"],
                        "argus_why_collect": (
                            "Decide whether Algolia needs product proof for AI shopping agents."
                        ),
                        "argus_evidence_urls": [
                            "https://constructor.com/changelog/ai-shopping-agent"
                        ],
                    },
                }
            ],
            "patterns": [
                {
                    "pattern_observation_id": 44,
                    "pattern_type": "own_narrative_gap",
                    "capability_text": "AI shopping agents",
                    "summary": "Constructor is louder while Algolia has no matching narrative in this evidence set.",
                    "involved_companies": ["Algolia", "Constructor"],
                    "confidence": 0.78,
                    "evidence_refs": [{"source_url": "https://constructor.com/changelog"}],
                    "created_at": "2026-07-10T05:15:00+00:00",
                }
            ],
        }
        self.learning_apply_plan_path: str | None = "/tmp/cios-product-market/algolia/learning-apply-plan.json"
        self.run_status_payload: dict[str, Any] = {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "report_id": 42,
            "report_date": "2026-07-10",
            "cadence": "daily",
            "report_status": "rendered",
            "product_market_status": "ran",
            "demand_plane_status": "missing",
            "looker_discovered_count": 0,
            "looker_ready_count": 0,
            "looker_error_count": 0,
            "looker_normalized_row_count": 0,
            "looker_skipped_row_count": 0,
            "looker_archived_count": 0,
            "next_sweep_plan_path": "/tmp/cios-product-market/algolia/next-sweep-learning-plan.json",
            "learning_apply_plan_path": self.learning_apply_plan_path,
            "learning_apply_plan_summary": {
                "action_count": 1,
                "skipped_count": 0,
                "targets": ["source_coverage_policy"],
                "package_paths": ["config/source-coverage-policy.yaml"],
            },
            "product_surface_plan_summary": {
                "target_count": 2,
                "learning_prioritized_count": 1,
                "prioritized_targets": [
                    {
                        "company_name": "Coveo",
                        "surface_family": "docs",
                        "url": "https://www.coveo.com/en/docs",
                        "learning_priority": 100,
                        "learning_reasons": [
                            "coverage_recheck: Re-audit Coveo source coverage before ranking Constructor again."
                        ],
                    }
                ],
            },
            "runner_summary": {
                "verdict": "watch",
                "learning_instruction_count": 1,
                "learning_instruction_improvement_ids": [202],
            },
            "ledger_refresh_status": "ran",
            "ledger_refresh_summary": {
                "verdict": "watch",
                "product_event_count": 2,
                "conversation_theme_count": 1,
                "demand_signal_count": 1,
                "pattern_count": 1,
                "recommendation_count": 0,
                "learning_instruction_count": 1,
                "learning_instruction_improvement_ids": [202],
                "intelligence_brief": {
                    "top_insight": "Ledger replay says coverage gate held the action.",
                    "primary_action": "Re-audit Coveo before promoting Constructor.",
                    "demand_read": {
                        "summary": "1 rising demand topic matched product proof.",
                    },
                    "conversion_diagnostics": {
                        "summary": "2 product events and 1 demand signal became 1 pattern.",
                        "blockers": ["Coveo source coverage degraded."],
                    },
                },
            },
            "latest_intelligence_brief": {
                "top_insight": "Durable run intelligence says coverage gate held the action.",
                "confidence_limits": ["Coveo source coverage was degraded."],
            },
            "run_intelligence_history": [
                {
                    "run_intelligence_id": 88,
                    "verdict": "watch",
                    "top_insight": "Durable run intelligence says coverage gate held the action.",
                    "primary_action": None,
                    "confidence_limits": ["Coveo source coverage was degraded."],
                    "evidence_urls": ["https://constructor.com/changelog"],
                    "created_at": "2026-07-10T05:13:00+00:00",
                    "product_event_count": 2,
                    "conversation_theme_count": 1,
                    "demand_signal_count": 1,
                    "pattern_count": 1,
                    "recommendation_count": 0,
                    "learning_instruction_count": 1,
                    "learning_instruction_improvement_ids": [202],
                }
            ],
            "scout_paths": ["/tmp/cios-product-market/algolia/surface-exports/000030-coveo-docs.json"],
            "errors": [],
        }
        self.created_competitor: CompetitorCreate | None = None
        self.updated_competitor: tuple[int, CompetitorUpdate] | None = None
        self.created_source: tuple[int, SourceCreate] | None = None
        self.updated_source: tuple[int, SourceUpdate] | None = None
        self.created_product_surface: tuple[int, ProductSurfaceCreate] | None = None
        self.updated_product_surface: tuple[int, ProductSurfaceUpdate] | None = None
        self.updated_improvement: tuple[int, ImprovementStatusUpdate] | None = None
        self.updated_recommendation: tuple[int, str] | None = None

    def registry(self, tenant_slug: str):
        return {
            "tenant_slug": tenant_slug,
            "tenant_id": 1,
            "competitors": self.competitors,
            "improvements": self.improvements,
        }

    def latest_run_status(self, tenant_slug: str):
        payload = copy.deepcopy(self.run_status_payload)
        payload["tenant_slug"] = tenant_slug
        payload["learning_apply_plan_path"] = self.learning_apply_plan_path
        return payload

    def list_improvements(self, tenant_slug: str, status: str | None = "open"):
        if status is None:
            return self.improvements
        return [item for item in self.improvements if item["status"] == status]

    def update_improvement_status(self, tenant_slug: str, improvement_id: int, payload: ImprovementStatusUpdate):
        self.updated_improvement = (improvement_id, payload)
        row = self.improvements[0] | {"status": payload.status}
        return row

    def next_sweep_plan(self, tenant_slug: str):
        return {
            "tenant_id": 1,
            "generated_at": "2026-07-10T05:13:00Z",
            "instructions": [
                {
                    "tenant_id": 1,
                    "kind": "other",
                    "priority": "critical",
                    "summary": "Re-evaluate recommendation 7 against source coverage in the next sweep.",
                    "instruction": "Re-evaluate recommendation 7 against source coverage in the next sweep.",
                    "status": "ready_for_next_sweep",
                    "change": {"source": "argus_recommendation:7"},
                    "evidence_event_ids": [101],
                    "source_improvement_ids": [202],
                }
            ],
            "skipped": [],
        }

    def feature_matrix(self, tenant_slug: str):
        return self.feature_matrix_rows

    def evidence_ledger(self, tenant_slug: str):
        return self.evidence_ledger_payload | {"tenant_slug": tenant_slug}

    def list_recommendations(self, tenant_slug: str, status: str | None = "open"):
        if status is None:
            return self.recommendations
        return [item for item in self.recommendations if item["status"] == status]

    def update_recommendation_status(self, tenant_slug: str, recommendation_id: int, payload):
        self.updated_recommendation = (recommendation_id, payload.status)
        row = self.recommendations[0] | {"status": payload.status}
        return row

    def create_competitor(self, tenant_slug: str, payload: CompetitorCreate):
        self.created_competitor = payload
        return {
            "competitor_id": 2,
            "competitor_name": payload.name,
            "domain": payload.domain,
            "category": payload.category,
            "priority": payload.priority,
            "status": "active",
            "sources": [],
            "product_surfaces": [],
        }

    def update_competitor(self, tenant_slug: str, competitor_id: int, payload: CompetitorUpdate):
        self.updated_competitor = (competitor_id, payload)
        return self.competitors[0] | {
            "status": payload.status or self.competitors[0]["status"],
            "competitor_name": payload.name or self.competitors[0]["competitor_name"],
        }

    def create_source(self, tenant_slug: str, competitor_id: int, payload: SourceCreate):
        self.created_source = (competitor_id, payload)
        return {
            "source_id": 11,
            "source_family": payload.source_family,
            "url": payload.url,
            "status": payload.status,
            "latest_event_type": None,
            "http_status": None,
            "detail": None,
            "checked_at": None,
        }

    def update_source(self, tenant_slug: str, source_id: int, payload: SourceUpdate):
        self.updated_source = (source_id, payload)
        return {
            "source_id": source_id,
            "source_family": payload.source_family or "blog",
            "url": payload.url or "https://constructor.com/blog",
            "status": payload.status or "active",
            "latest_event_type": None,
            "http_status": None,
            "detail": None,
            "checked_at": None,
        }

    def create_product_surface(self, tenant_slug: str, competitor_id: int, payload: ProductSurfaceCreate):
        self.created_product_surface = (competitor_id, payload)
        return {
            "surface_id": 31,
            "company_name": "Constructor",
            "company_role": "competitor",
            "surface_family": payload.surface_family,
            "url": payload.url,
            "status": payload.status,
            "last_checked_at": None,
        }

    def update_product_surface(self, tenant_slug: str, surface_id: int, payload: ProductSurfaceUpdate):
        self.updated_product_surface = (surface_id, payload)
        return {
            "surface_id": surface_id,
            "company_name": "Constructor",
            "company_role": "competitor",
            "surface_family": payload.surface_family or "docs",
            "url": payload.url or "https://docs.constructor.com/",
            "status": payload.status or "active",
            "last_checked_at": None,
        }


class FakeRecommendationChallengeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record_challenge(self, **kwargs):
        self.calls.append(kwargs)
        return RecommendationChallengeResult(
            event=LearningEvent(
                id=101,
                tenant_id=1,
                run_id=kwargs.get("run_id"),
                event_type=LearningEventType.RECOMMENDATION_CHALLENGE,
                lesson="challenge saved",
                proposed_change="re-evaluate audience demand in the next sweep",
            ),
            improvement=ImprovementItem(
                id=202,
                tenant_id=1,
                source=f"argus_recommendation:{kwargs['recommendation_id']}",
                problem="challenge saved",
                proposed_fix="re-evaluate audience demand in the next sweep",
                priority=ImprovementPriority.HIGH,
            ),
            next_sweep_instruction="re-evaluate audience demand in the next sweep",
        )


class FakeLedgerRefreshRunner:
    def __init__(self, events: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.events = events

    def __call__(self, **kwargs):
        if self.events is not None:
            self.events.append("refresh")
        self.calls.append(kwargs)
        return {
            "tenant_id": kwargs["tenant_id"],
            "verdict": "actionable",
            "product_event_count": 2,
            "conversation_theme_count": 1,
            "demand_signal_count": 1,
            "feature_position_count": 2,
            "pattern_count": 1,
            "recommendation_count": 1,
            "intelligence_brief": {
                "verdict": "actionable",
                "top_insight": "Ledger replay found a demand-backed narrative gap.",
                "primary_action": "Create the agentic product discovery narrative.",
                "evidence_urls": ["looker://algolia/ga4/topics"],
                "confidence_limits": [],
                "next_questions": [],
                "demand_read": {
                    "summary": "1 rising demand topic found; 1 matched product proof.",
                    "top_topics": [{"topic": "agentic product discovery"}],
                },
                "conversion_diagnostics": {
                    "summary": "2 product events and 1 demand signal became 1 pattern."
                },
            },
        }


class FakeDemandImportLedgerPersister:
    def __init__(self, events: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.events = events

    def persist(self, *, tenant_id: int, prepared):
        if self.events is not None:
            self.events.append("persist")
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "payload_paths": list(prepared.payload_paths),
            }
        )
        return {
            "status": "persisted",
            "tenant_id": tenant_id,
            "demand_signal_count": prepared.normalized_row_count,
            "saved_ids": [701],
        }


class FakeDemandIntakeControl:
    def __init__(self, result: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "status": "blocked_missing_demand_source",
            "exit_code": 2,
            "tenant": "algolia",
            "mode": "blocked",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "readiness": {"status": "blocked_missing_demand_source"},
            "ga4_export": None,
            "demand_import": None,
        }
        self.error = error

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeDashboardRefreshRunner:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "status": "published",
            "index": "/tmp/public/index.html",
            "json": "/tmp/public/data/semantic-dashboard.json",
        }
        self.error = error
        self.events = events

    def __call__(self, **kwargs):
        if self.events is not None:
            self.events.append("dashboard")
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeProductSurfaceRepairControl:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "status": "succeeded",
            "tenant_id": 1,
            "selected": 1,
            "succeeded": 1,
            "failed": 0,
            "scout_paths": ["/tmp/cios-product-market/algolia/product-surface-repairs/repair.json"],
            "results": [
                {
                    "status": "succeeded",
                    "target": {"company_name": "Coveo", "surface_id": 10},
                    "category": "no_markdown",
                    "row_count": 1,
                }
            ],
        }
        self.error = error

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeProductSurfaceExtractionControl:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "status": "ready",
            "tenant_id": 1,
            "planned": 1,
            "succeeded": 1,
            "empty": 0,
            "failed": 0,
            "product_row_count": 2,
            "scout_paths": ["/tmp/cios-product-market/algolia/surface-exports/000044-klevu-docs.json"],
            "results": [
                {
                    "status": "succeeded",
                    "company_name": "Klevu",
                    "surface_family": "docs",
                    "row_count": 2,
                }
            ],
        }
        self.error = error

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeProductSurfaceCandidatePromotionControl:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "status": "completed",
            "tenant_id": 1,
            "promoted_count": 1,
            "promoted_surfaces": [
                {
                    "surface_id": 151,
                    "tenant_id": 1,
                    "company_id": 9,
                    "company_name": "Klevu",
                    "company_role": "competitor",
                    "surface_family": "changelog",
                    "url": "https://www.klevu.com/changelog/",
                }
            ],
        }
        self.error = error

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeProductSurfaceRepairRefreshRunner:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {
            "verdict": "watch",
            "product_event_count": 1,
            "conversation_theme_count": 0,
            "demand_signal_count": 0,
            "pattern_count": 1,
            "recommendation_count": 0,
            "intelligence_brief": {
                "top_insight": "Repair imported one product proof row.",
                "primary_action": None,
                "confidence_limits": ["Demand plane is still missing."],
            },
        }
        self.error = error

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeProductSurfaceRepairHistoryStore:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[str] = []
        self.payload = payload or {
            "tenant_slug": "algolia",
            "repair_root": "/tmp/cios-product-market/algolia/product-surface-repairs",
            "attempt_count": 1,
            "latest": {
                "status": "failed",
                "selected": 1,
                "succeeded": 0,
                "failed": 1,
                "generated_at": "2026-07-12T08:06:09+00:00",
                "company_name": "Coveo",
                "surface_id": 10,
                "category": "no_markdown",
                "row_count": 0,
                "error": "HTTP 403",
                "imported_product_event_count": 0,
                "argus_top_insight": None,
                "summary_path": "/tmp/repair-summary.json",
            },
            "attempts": [],
        }

    def status(self, tenant_slug: str, *, limit: int = 5):
        self.calls.append(tenant_slug)
        return self.payload | {"tenant_slug": tenant_slug}


class FakeDemandIntakeHistoryStore:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[str] = []
        self.payload = payload or {
            "tenant_slug": "algolia",
            "run_root": "/tmp/cios-product-market/algolia/demand-intake-runs",
            "attempt_count": 1,
            "latest": {
                "status": "blocked_missing_demand_source",
                "exit_code": 2,
                "mode": "blocked",
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "readiness_status": "blocked_missing_demand_source",
                "normalized_row_count": 0,
                "demand_signal_count": 0,
                "argus_top_insight": None,
                "summary_path": "/tmp/demand-intake-summary.json",
            },
            "attempts": [],
        }

    def status(self, tenant_slug: str, *, limit: int = 5):
        self.calls.append(tenant_slug)
        return self.payload | {"tenant_slug": tenant_slug}


class FakeOperatorHandoffStore:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[str] = []
        self.payload = payload or {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-11T20:02:00Z",
            "status": "blocked_on_evidence",
            "argus_readiness": "not_actionable",
            "summary": "Argus is blocked by 1 evidence gap before it can promote this run to action.",
            "next_operator_action": "Upload GA4 / Looker demand export for the current and previous periods.",
            "top_blocker": {
                "work_item_id": "argus-evidence:88:demand",
                "evidence_plane": "demand",
                "severity": "blocks_action",
                "title": "Demand plane missing",
                "why_needed": "Demand evidence is missing, so Argus withheld owner recommendations.",
                "blocks": ["owner recommendations", "priority ranking", "action promotion"],
                "observed_state": {"demand_plane_status": "missing"},
            },
            "primary_command": {
                "label": "Download demand template",
                "href": "/api/tenants/algolia/argus/demand-imports/template",
                "method": "get",
                "surface": "Demand imports",
            },
            "secondary_command": {
                "label": "Prepare demand and refresh Argus",
                "href": "/admin/algolia/argus/demand-imports/refresh",
                "method": "post",
                "surface": "Demand imports",
            },
            "operator_brief": [
                "Argus withheld action because Demand plane missing is open on the demand plane.",
                "Next step: Upload GA4 / Looker demand export for the current and previous periods.",
            ],
            "demand_collection_plan": {
                "status": "needs_demand_source",
                "topic_count": 2,
                "topics": [
                    {
                        "topic": "Shopping Assistant",
                        "related_competitors": ["Constructor"],
                        "evidence_url_count": 3,
                    },
                    {
                        "topic": "Channel Assistant",
                        "related_competitors": ["Klevu"],
                        "evidence_url_count": 1,
                    },
                ],
            },
            "demand_plan_template": {
                "status": "generated",
                "format": "csv",
                "filename": "argus-demand-plan-template.csv",
            },
            "artifact_refs": {
                "work_queue": "/tmp/cios-product-market/algolia/argus-evidence-work-queue.json",
                "dashboard": "/tmp/cios-product-market/algolia/argus-dashboard.json",
            },
            "work_queue": {
                "generated_at": "2026-07-11T20:00:00Z",
                "work_item_count": 1,
                "blocking_count": 1,
                "limiting_count": 0,
                "item_ids": ["argus-evidence:88:demand"],
            },
            "artifact_path": "/tmp/cios-product-market/algolia/argus-operator-handoff.json",
            "artifact_found": True,
        }

    def status(self, tenant_slug: str) -> dict[str, Any]:
        self.calls.append(tenant_slug)
        return self.payload


class FakeDataPlaneManifestStore:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[str] = []
        self.payload = payload or {
            "schema_version": 1,
            "tenant_slug": "algolia",
            "generated_at": "2026-07-12T04:05:00Z",
            "dashboard_generated_at": "2026-07-12T04:04:00Z",
            "status": "blocked_on_evidence",
            "argus_readiness": "not_actionable",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "source_of_truth": {
                "runtime": "Hermes",
                "domain_package": "CI-OS",
                "database": "Postgres evidence ledger",
                "ui_role": "derived readout only",
            },
            "artifact_refs": {
                "dashboard": "/tmp/cios-product-market/algolia/argus-dashboard.json",
                "demand_readiness": "/tmp/cios-product-market/algolia/argus-demand-readiness.json",
            },
            "planes": {
                "registry_coverage": {
                    "status": "present",
                    "summary": "Registry and source coverage are represented.",
                    "blocks_action": False,
                    "storage": ["competitors", "sources"],
                    "counts": {"monitored_competitor_count": 27, "active_source_count": 48},
                },
                "product_reality": {
                    "status": "present",
                    "summary": "Product reality evidence fed the feature matrix.",
                    "blocks_action": False,
                    "storage": ["product_surfaces", "product_change_events"],
                    "counts": {"product_event_count": 2, "product_surface_target_count": 30},
                },
                "market_conversation": {
                    "status": "present",
                    "summary": "Market conversation evidence fed the current Argus read.",
                    "blocks_action": False,
                    "storage": ["semantic_deltas", "conversation_themes"],
                    "counts": {"conversation_theme_count": 1, "pattern_count": 1},
                },
                "audience_demand": {
                    "status": "blocked_missing_demand_source",
                    "summary": "Tenant-side demand is missing, so Argus cannot promote outward movement.",
                    "blocks_action": True,
                    "storage": ["demand_signals"],
                    "counts": {"demand_signal_count": 0, "looker_ready_count": 0},
                    "next_hermes_action": "configure_ga4_or_upload_demand_export",
                },
                "operator_learning": {
                    "status": "present",
                    "summary": "Approved learning was consumed or prepared for this run.",
                    "blocks_action": False,
                    "storage": ["learning_events", "improvement_queue"],
                    "counts": {"consumed_learning_count": 1, "learning_instruction_count": 1},
                },
                "run_truth": {
                    "status": "present",
                    "summary": "Run-stage ledger is present for Hermes and Argus inspection.",
                    "blocks_action": False,
                    "storage": ["run_stage_ledgers", "product_market_run_intelligence"],
                    "counts": {"stage_count": 9, "failed_stage_count": 0},
                },
            },
            "blockers": [
                {
                    "plane": "audience_demand",
                    "severity": "blocks_action",
                    "title": "Demand plane missing",
                    "next_step": "Configure GA4 or upload a GA / Looker export.",
                    "work_item_id": "argus-evidence:88:demand",
                }
            ],
            "safety": {
                "ui_must_not_invent_semantics": True,
                "recommendations_require_backend_scorecards": True,
                "empty_or_missing_plane_blocks_promotion": True,
            },
            "artifact_path": "/tmp/cios-product-market/algolia/argus-data-plane-manifest.json",
            "artifact_found": True,
        }

    def status(self, tenant_slug: str) -> dict[str, Any]:
        self.calls.append(tenant_slug)
        return self.payload


def _manifest_store_with_demand_plan(topics: list[dict[str, Any]] | None = None) -> FakeDataPlaneManifestStore:
    base = FakeDataPlaneManifestStore().payload
    plan_topics = topics or [
        {
            "topic": "AI Shopping Agent",
            "capability_key": "ai shopping agent",
            "assessment": "own_product_gap",
            "why_collect": "Measure whether Algolia demand exists for AI shopping agents.",
            "suggested_filter_terms": ["AI Shopping Agent", "shopping agent"],
            "related_competitors": ["Constructor"],
            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
        },
        {
            "topic": "Context engineering",
            "capability_key": "context engineering",
            "assessment": "own_narrative_gap",
            "why_collect": "Measure whether Algolia demand exists for context engineering.",
            "suggested_filter_terms": ["Context engineering", "context"],
            "related_competitors": ["Elastic"],
            "evidence_urls": ["https://elastic.co/blog/context-engineering"],
        },
    ]
    return FakeDataPlaneManifestStore(
        payload={
            **base,
            "planes": {
                **base["planes"],
                "audience_demand": {
                    **base["planes"]["audience_demand"],
                    "details": {
                        "demand_collection_plan": {
                            "status": "needs_demand_source",
                            "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
                            "topics": plan_topics,
                        }
                    },
                },
            },
        }
    )


def _client(
    repo: FakeAdminRepository | None = None,
    *,
    token: str | None = None,
    allowed_hosts=None,
    challenge_recorder: FakeRecommendationChallengeRecorder | None = None,
    ledger_refresh_runner: FakeLedgerRefreshRunner | None = None,
    dashboard_refresh_runner: FakeDashboardRefreshRunner | None = None,
    demand_import_ledger_persister: FakeDemandImportLedgerPersister | None = None,
    demand_intake_control: FakeDemandIntakeControl | None = None,
    demand_intake_history_store: FakeDemandIntakeHistoryStore | None = None,
    operator_handoff_store: FakeOperatorHandoffStore | None = None,
    data_plane_manifest_store: FakeDataPlaneManifestStore | None = None,
    product_surface_repair_control: FakeProductSurfaceRepairControl | None = None,
    product_surface_extraction_control: FakeProductSurfaceExtractionControl | None = None,
    product_surface_candidate_promotion_control: FakeProductSurfaceCandidatePromotionControl | None = None,
    product_surface_repair_refresh_runner: FakeProductSurfaceRepairRefreshRunner | None = None,
    product_surface_repair_history_store: FakeProductSurfaceRepairHistoryStore | None = None,
):
    app = create_app(
        repository=repo or FakeAdminRepository(),
        admin_token=token,
        allowed_hosts=allowed_hosts or {"testclient"},
        recommendation_challenge_recorder=challenge_recorder,
        ledger_refresh_runner=ledger_refresh_runner,
        dashboard_refresh_runner=dashboard_refresh_runner,
        demand_import_ledger_persister=demand_import_ledger_persister,
        demand_intake_control=demand_intake_control,
        demand_intake_history_store=demand_intake_history_store,
        operator_handoff_store=operator_handoff_store,
        data_plane_manifest_store=data_plane_manifest_store,
        product_surface_repair_control=product_surface_repair_control,
        product_surface_extraction_control=product_surface_extraction_control,
        product_surface_candidate_promotion_control=product_surface_candidate_promotion_control,
        product_surface_repair_refresh_runner=product_surface_repair_refresh_runner,
        product_surface_repair_history_store=product_surface_repair_history_store,
    )
    return TestClient(app)


def _write_learning_apply_artifacts(package_root: Path) -> None:
    pending = LearningApplyAction(
        tenant_id=1,
        kind=ProposalKind.COVERAGE_RECHECK,
        target="source_coverage_policy",
        package_path="config/source-coverage-policy.yaml",
        summary="Re-audit Coveo before ranking Constructor.",
        instruction="Run a coverage recheck for Coveo product and conversation sources.",
        change={"company": "Coveo", "priority": "critical"},
        evidence_event_ids=[701],
        source_improvement_ids=[401],
    )
    approved = LearningApplyAction(
        tenant_id=1,
        kind=ProposalKind.SOURCE_RETRY_TUNING,
        target="source_retry_policy",
        package_path="config/source-retry-policy.yaml",
        summary="Add bounded retry for HTTP 503 fetch failures.",
        instruction="Tune source retry policy for repeated 503 failures.",
        change={"source": "https://coveo.com/blog", "priority": "high"},
        evidence_event_ids=[702],
        source_improvement_ids=[402],
    )
    executor = LearningApplyExecutor(package_root=package_root)
    executor.execute(LearningApplyPlan(tenant_id=1, actions=[pending]))
    executor.execute(LearningApplyPlan(tenant_id=1, actions=[approved]), approved_by="arijit")


def _write_learning_apply_plan(path: Path) -> None:
    action = LearningApplyAction(
        tenant_id=1,
        kind=ProposalKind.COVERAGE_RECHECK,
        target="source_coverage_policy",
        package_path="config/source-coverage-policy.yaml",
        summary="Re-audit Coveo before ranking Constructor.",
        instruction="Run a coverage recheck for Coveo product and conversation sources.",
        change={"company": "Coveo", "priority": "critical"},
        evidence_event_ids=[701],
        source_improvement_ids=[401],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LearningApplyPlan(tenant_id=1, actions=[action]).model_dump_json(indent=2), encoding="utf-8")


def test_json_api_returns_argus_demand_import_status(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    inbox = drop / "ga-pages.csv"
    inbox.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    broken_inbox = drop / "bad.json"
    broken_inbox.write_text("{", encoding="utf-8")
    archived = drop / "_archive" / "20260711T080000Z"
    archived.mkdir(parents=True)
    (archived / "accepted.csv").write_text("ok\n", encoding="utf-8")
    rejected = drop / "_rejected" / "20260711T080000Z"
    rejected.mkdir(parents=True)
    (rejected / "bad.csv").write_text("bad\n", encoding="utf-8")
    work_dir = tmp_path / "work" / "algolia"
    work_dir.mkdir(parents=True)
    manifest = work_dir / "looker-export-manifest.json"
    manifest.write_text(
        """
        {
          "tenant": "algolia",
          "discovered_count": 2,
          "ready_count": 1,
          "error_count": 1,
          "normalized_row_count": 14,
          "skipped_row_count": 3,
          "files": [
            {"path": "ga-pages.csv", "status": "ready", "normalized_row_count": 14},
            {"path": "bad.csv", "status": "error", "error": "parse failed"}
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(tmp_path / "work"))
    client = _client()

    response = client.get("/api/tenants/algolia/argus/demand-imports")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_slug"] == "algolia"
    assert payload["drop_folder"] == str(drop)
    assert payload["manifest_path"] == str(manifest)
    assert payload["manifest_exists"] is True
    assert payload["discovered_count"] == 2
    assert payload["ready_count"] == 1
    assert payload["error_count"] == 1
    assert payload["normalized_row_count"] == 14
    assert payload["skipped_row_count"] == 3
    assert {item["name"] for item in payload["inbox_files"]} == {"bad.json", "ga-pages.csv"}
    previews = {preview["name"]: preview for preview in payload["inbox_previews"]}
    assert previews["ga-pages.csv"]["status"] == "ready"
    assert previews["ga-pages.csv"]["raw_row_count"] == 1
    assert previews["ga-pages.csv"]["normalized_row_count"] == 1
    assert previews["ga-pages.csv"]["skipped_row_count"] == 0
    assert previews["ga-pages.csv"]["topics"] == ["AI Shopping Agent"]
    assert previews["bad.json"]["status"] == "error"
    assert "JSON" in previews["bad.json"]["error"] or "Expecting" in previews["bad.json"]["error"]
    assert payload["archived_files"][0]["name"] == "accepted.csv"
    assert payload["rejected_files"][0]["name"] == "bad.csv"
    assert ".csv" in payload["accepted_suffixes"]


def test_json_api_annotates_queued_demand_imports_with_argus_plan_coverage(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(tmp_path / "work"))
    manifest = FakeDataPlaneManifestStore()
    manifest.payload["planes"]["audience_demand"]["details"] = {
        "demand_collection_plan": {
            "status": "needs_demand_source",
            "topic_count": 2,
            "topics": [
                {
                    "topic": "AI Shopping Agent",
                    "capability_key": "ai shopping agent",
                    "suggested_filter_terms": ["AI Shopping Agent", "agentic commerce"],
                },
                {
                    "topic": "Context engineering",
                    "capability_key": "context engineering",
                    "suggested_filter_terms": ["context engineering"],
                },
            ],
        }
    }
    client = _client(data_plane_manifest_store=manifest)

    response = client.get("/api/tenants/algolia/argus/demand-imports")

    assert response.status_code == 200
    assert manifest.calls == ["algolia"]
    preview = response.json()["inbox_previews"][0]
    assert preview["name"] == "ga-pages.csv"
    assert preview["demand_plan_coverage"]["status"] == "partial_coverage"
    assert preview["demand_plan_coverage"]["matched_plan_topic_count"] == 1
    assert preview["demand_plan_coverage"]["planned_topic_count"] == 2
    assert preview["demand_plan_coverage"]["matched_topics"][0]["topic"] == "AI Shopping Agent"
    assert preview["demand_plan_coverage"]["missing_topics"][0]["topic"] == "Context engineering"


def test_json_api_prepare_argus_demand_imports_attaches_plan_metadata(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    work_root = tmp_path / "work"
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    manifest = FakeDataPlaneManifestStore()
    manifest.payload["planes"]["audience_demand"]["details"] = {
        "demand_collection_plan": {
            "status": "needs_demand_source",
            "topic_count": 1,
            "topics": [
                {
                    "topic": "AI Shopping Agent",
                    "capability_key": "ai shopping agent",
                    "assessment": "own_product_gap",
                    "suggested_filter_terms": ["AI Shopping Agent"],
                    "related_competitors": ["Constructor"],
                    "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                }
            ],
        }
    }
    client = _client(token="secret", data_plane_manifest_store=manifest)

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports/prepare",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert manifest.calls == ["algolia"]
    assert payload["manifest"]["files"][0]["demand_plan_coverage"]["status"] == "covered"
    normalized_payload = json.loads(Path(payload["payload_paths"][0]).read_text(encoding="utf-8"))
    row = normalized_payload["records"][0]
    assert row["argus_plan_matched"] is True
    assert row["argus_capability_key"] == "ai shopping agent"
    assert row["argus_related_competitors"] == ["Constructor"]


def test_admin_html_shows_queued_demand_import_argus_plan_coverage(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(tmp_path / "work"))
    manifest = FakeDataPlaneManifestStore()
    manifest.payload["planes"]["audience_demand"]["details"] = {
        "demand_collection_plan": {
            "status": "needs_demand_source",
            "topic_count": 2,
            "topics": [
                {
                    "topic": "AI Shopping Agent",
                    "capability_key": "ai shopping agent",
                    "suggested_filter_terms": ["AI Shopping Agent"],
                },
                {
                    "topic": "Context engineering",
                    "capability_key": "context engineering",
                    "suggested_filter_terms": ["context engineering"],
                },
            ],
        }
    }
    client = _client(data_plane_manifest_store=manifest)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Plan coverage" in response.text
    assert "partial_coverage" in response.text
    assert "1/2 planned topics" in response.text
    assert "matched: AI Shopping Agent" in response.text
    assert "missing: Context engineering" in response.text


def test_json_api_uploads_argus_demand_export_to_tenant_drop_folder(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    client = _client(token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports",
        headers={"x-cios-admin-token": "secret"},
        json={
            "filename": "ga-pages.csv",
            "content": (
                "Page title,Page path,Engaged sessions,Engaged sessions previous period,"
                "Period start,Period end,Looker Studio URL\n"
                "AI Shopping Agent,/ai,240,160,2026-07-01,2026-07-08,"
                "https://lookerstudio.google.com/reporting/abc\n"
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    saved = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    assert payload["name"] == "ga-pages.csv"
    assert payload["path"] == str(saved)
    assert payload["status"] == "queued_for_next_sweep"
    assert payload["preview_status"] == "ready"
    assert payload["raw_row_count"] == 1
    assert payload["normalized_row_count"] == 1
    assert payload["skipped_row_count"] == 0
    assert payload["topics"] == ["AI Shopping Agent"]
    assert payload["error"] is None
    assert saved.read_text(encoding="utf-8").startswith("Page title")


def test_json_api_uploads_argus_demand_export_with_plan_coverage(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    manifest = FakeDataPlaneManifestStore()
    manifest.payload["planes"]["audience_demand"]["details"] = {
        "demand_collection_plan": {
            "status": "needs_demand_source",
            "topic_count": 2,
            "topics": [
                {
                    "topic": "AI Shopping Agent",
                    "capability_key": "ai shopping agent",
                    "suggested_filter_terms": ["AI Shopping Agent", "agentic commerce"],
                },
                {
                    "topic": "Context engineering",
                    "capability_key": "context engineering",
                    "suggested_filter_terms": ["context engineering"],
                },
            ],
        }
    }
    client = _client(token="secret", data_plane_manifest_store=manifest)

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports",
        headers={"x-cios-admin-token": "secret"},
        json={
            "filename": "ga-pages.csv",
            "content": (
                "Page title,Page path,Engaged sessions,Engaged sessions previous period,"
                "Period start,Period end,Looker Studio URL\n"
                "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,"
                "https://lookerstudio.google.com/reporting/abc\n"
            ),
        },
    )

    assert response.status_code == 200
    assert manifest.calls == ["algolia"]
    coverage = response.json()["demand_plan_coverage"]
    assert coverage["status"] == "partial_coverage"
    assert coverage["matched_plan_topic_count"] == 1
    assert coverage["planned_topic_count"] == 2
    assert coverage["matched_topics"][0]["topic"] == "AI Shopping Agent"
    assert coverage["missing_topics"][0]["topic"] == "Context engineering"


def test_admin_html_uploads_argus_demand_export_file_to_tenant_drop_folder(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    client = _client(token="secret")

    response = client.post(
        "/admin/algolia/argus/demand-imports",
        headers={"x-cios-admin-token": "secret"},
        files={
            "file": (
                "ga-pages.csv",
                "Page title,Page path,Engaged sessions\nAI Shopping Agent,/ai,240\n",
                "text/csv",
            )
        },
        follow_redirects=False,
    )

    saved = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    assert saved.read_text(encoding="utf-8").startswith("Page title")


def test_json_api_returns_argus_demand_import_template() -> None:
    client = _client()

    response = client.get("/api/tenants/algolia/argus/demand-imports/template")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=argus-demand-template.csv" in response.headers["content-disposition"]
    body = response.text
    assert body.startswith("Page title,Page path,Engaged sessions")
    assert "Engaged sessions previous period" in body
    assert "Looker Studio URL" in body
    assert "AI Shopping Agent" not in body


def test_json_api_returns_argus_plan_specific_demand_import_template() -> None:
    manifest = FakeDataPlaneManifestStore(
        payload={
            **FakeDataPlaneManifestStore().payload,
            "planes": {
                **FakeDataPlaneManifestStore().payload["planes"],
                "audience_demand": {
                    **FakeDataPlaneManifestStore().payload["planes"]["audience_demand"],
                    "details": {
                        "demand_collection_plan": {
                            "status": "needs_demand_source",
                            "topics": [
                                {
                                    "topic": "AI Assistant",
                                    "capability_key": "ai assistant",
                                    "assessment": "own_product_gap",
                                    "why_collect": "Decide whether Algolia needs product proof for AI Assistant.",
                                    "suggested_filter_terms": ["AI Assistant", "assistant"],
                                    "related_competitors": ["Constructor", "Elastic"],
                                    "evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
                                },
                                {
                                    "topic": "Context engineering",
                                    "capability_key": "context engineering",
                                    "assessment": "own_narrative_gap",
                                    "why_collect": "Create an Algolia narrative for context engineering.",
                                    "suggested_filter_terms": ["Context engineering", "context"],
                                    "related_competitors": ["Elastic"],
                                    "evidence_urls": ["https://elastic.co/blog/context-engineering"],
                                },
                            ],
                        }
                    },
                },
            },
        }
    )
    client = _client(data_plane_manifest_store=manifest)

    response = client.get("/api/tenants/algolia/argus/demand-imports/template?planned=1")

    assert response.status_code == 200
    assert manifest.calls == ["algolia"]
    assert "attachment; filename=argus-demand-plan-template.csv" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["Argus topic"] == "AI Assistant"
    assert rows[0]["Capability key"] == "ai assistant"
    assert rows[0]["Suggested filters"] == "AI Assistant | assistant"
    assert rows[0]["Related competitors"] == "Constructor | Elastic"
    assert rows[0]["Why collect"] == "Decide whether Algolia needs product proof for AI Assistant."
    assert rows[0]["Page title"] == ""
    assert rows[0]["Engaged sessions"] == ""
    assert rows[1]["Argus topic"] == "Context engineering"


def test_json_api_returns_argus_demand_work_order_guide_from_manifest() -> None:
    manifest = _manifest_store_with_demand_plan()
    client = _client(data_plane_manifest_store=manifest)

    response = client.get("/api/tenants/algolia/argus/demand-imports/work-order")

    assert response.status_code == 200
    assert manifest.calls == ["algolia"]
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["tenant_slug"] == "algolia"
    assert payload["template_href"] == "/api/tenants/algolia/argus/demand-imports/template?planned=1"
    assert payload["upload_action"] == "/admin/algolia/argus/demand-imports"
    assert payload["refresh_action"] == "/admin/algolia/argus/demand-imports/refresh"
    assert payload["topic_count"] == 2
    assert payload["topics"][0]["topic"] == "AI Shopping Agent"
    assert payload["topics"][0]["row_status"] == "needs_metrics"
    assert payload["topics"][0]["filter_terms"] == ["AI Shopping Agent", "shopping agent", "ai shopping agent"]
    assert payload["topics"][0]["related_competitors"] == ["Constructor"]
    assert payload["topics"][0]["evidence_url_count"] == 1
    assert payload["required_columns"][0] == "Page title"
    assert payload["required_metric"] == "Engaged sessions"
    assert "Measure whether Algolia" not in json.dumps(payload)


def test_json_api_rejects_unsafe_or_unsupported_demand_uploads(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    client = _client(token="secret")

    traversal = client.post(
        "/api/tenants/algolia/argus/demand-imports",
        headers={"x-cios-admin-token": "secret"},
        json={"filename": "../escape.csv", "content": "bad"},
    )
    unsupported = client.post(
        "/api/tenants/algolia/argus/demand-imports",
        headers={"x-cios-admin-token": "secret"},
        json={"filename": "notes.txt", "content": "bad"},
    )

    assert traversal.status_code == 400
    assert unsupported.status_code == 400
    assert not (app_dir / "data" / "escape.csv").exists()


def test_json_api_prepares_queued_demand_exports_without_archiving(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    good = drop / "ga-pages.csv"
    good.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    bad = drop / "bad.json"
    bad.write_text("{", encoding="utf-8")
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    client = _client(token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports/prepare",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    manifest_path = work_root / "algolia" / "looker-export-manifest.json"
    normalized_path = work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json"
    assert payload["tenant_slug"] == "algolia"
    assert payload["manifest_path"] == str(manifest_path)
    assert payload["discovered_count"] == 2
    assert payload["ready_count"] == 1
    assert payload["error_count"] == 1
    assert payload["normalized_row_count"] == 1
    assert payload["skipped_row_count"] == 0
    assert payload["payload_paths"] == [str(normalized_path)]
    assert manifest_path.exists()
    assert normalized_path.exists()
    assert good.exists()
    assert bad.exists()
    manifest = payload["manifest"]
    statuses = {Path(item["path"]).name: item["status"] for item in manifest["files"]}
    assert statuses == {"bad.json": "error", "ga-pages.csv": "ready"}


def test_json_api_prepare_manifest_explains_skipped_demand_rows(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "bad-ga-pages.csv").write_text(
        "Page title and screen name,Landing page + query string,Engaged sessions,Date range\n"
        "Generic blog post,/blog/company-news,120,\"Jul 1, 2026 - Jul 8, 2026\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    client = _client(token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports/prepare",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready_count"] == 0
    assert payload["normalized_row_count"] == 0
    assert payload["skipped_row_count"] == 1
    assert payload["manifest"]["files"][0]["status"] == "empty"
    assert payload["manifest"]["files"][0]["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "missing_topic",
            "missing_fields": ["topic"],
            "source_file": "bad-ga-pages.csv",
            "available_columns": [
                "Date range",
                "Engaged sessions",
                "Landing page + query string",
                "Page title and screen name",
            ],
        }
    ]


def test_admin_html_can_prepare_queued_demand_exports(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    client = _client(token="secret")

    response = client.post(
        "/admin/algolia/argus/demand-imports/prepare",
        headers={"x-cios-admin-token": "secret"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    assert (work_root / "algolia" / "looker-export-manifest.json").exists()
    assert (work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json").exists()


def test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR", "0.03")
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR", "25")
    events: list[str] = []
    runner = FakeLedgerRefreshRunner(events=events)
    dashboard_runner = FakeDashboardRefreshRunner(events=events)
    persister = FakeDemandImportLedgerPersister(events=events)
    client = _client(
        token="secret",
        ledger_refresh_runner=runner,
        dashboard_refresh_runner=dashboard_runner,
        demand_import_ledger_persister=persister,
    )

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports/refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "demand_prepared_and_argus_refreshed"
    assert payload["demand_import"]["normalized_row_count"] == 1
    assert payload["demand_import"]["payload_paths"] == [
        str(work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json")
    ]
    assert payload["demand_ledger"] == {
        "status": "persisted",
        "tenant_id": 1,
        "demand_signal_count": 1,
        "saved_ids": [701],
    }
    assert payload["ledger_refresh"]["verdict"] == "actionable"
    assert payload["ledger_refresh"]["intelligence_brief"]["top_insight"].startswith("Ledger replay")
    assert payload["argus_read"] == {
        "verdict": "actionable",
        "top_insight": "Ledger replay found a demand-backed narrative gap.",
        "primary_action": "Create the agentic product discovery narrative.",
        "demand_summary": "1 rising demand topic found; 1 matched product proof.",
        "conversion_summary": "2 product events and 1 demand signal became 1 pattern.",
        "counts": {
            "product_events": 2,
            "conversation_themes": 1,
            "demand_signals": 1,
            "patterns": 1,
            "recommendations": 1,
        },
    }
    assert payload["dashboard_refresh"]["status"] == "published"
    assert payload["archive"]["archived_count"] == 1
    assert not (drop / "ga-pages.csv").exists()
    archived = list((drop / "_archive").glob("*/ga-pages.csv"))
    assert len(archived) == 1
    assert runner.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "own_company_name": "Algolia",
            "days": 30,
            "limit": 500,
            "demand_quality": {"change_floor": 0.03, "value_floor": 25.0},
        }
    ]
    assert persister.calls == [
        {
            "tenant_id": 1,
            "payload_paths": [str(work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json")],
        }
    ]
    assert dashboard_runner.calls == [{"tenant_slug": "algolia"}]
    assert events == ["persist", "refresh", "dashboard"]


def test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    events: list[str] = []
    runner = FakeLedgerRefreshRunner(events=events)
    dashboard_runner = FakeDashboardRefreshRunner(events=events)
    persister = FakeDemandImportLedgerPersister(events=events)
    client = _client(
        token="secret",
        ledger_refresh_runner=runner,
        dashboard_refresh_runner=dashboard_runner,
        demand_import_ledger_persister=persister,
    )

    response = client.post(
        "/admin/algolia/argus/demand-imports/refresh",
        headers={"x-cios-admin-token": "secret"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    assert (work_root / "algolia" / "looker-export-manifest.json").exists()
    assert (work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json").exists()
    assert not (drop / "ga-pages.csv").exists()
    archived = list((drop / "_archive").glob("*/ga-pages.csv"))
    assert len(archived) == 1
    assert persister.calls == [
        {
            "tenant_id": 1,
            "payload_paths": [str(work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json")],
        }
    ]
    assert runner.calls[0]["tenant_id"] == 1
    assert runner.calls[0]["own_company_name"] == "Algolia"
    assert dashboard_runner.calls == [{"tenant_slug": "algolia"}]
    assert events == ["persist", "refresh", "dashboard"]


def test_json_api_blocks_operator_action_when_dashboard_refresh_fails(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    client = _client(
        token="secret",
        ledger_refresh_runner=FakeLedgerRefreshRunner(),
        demand_import_ledger_persister=FakeDemandImportLedgerPersister(),
        dashboard_refresh_runner=FakeDashboardRefreshRunner(error=RuntimeError("dashboard rerender failed")),
    )

    response = client.post(
        "/api/tenants/algolia/argus/demand-imports/refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 502
    assert "dashboard rerender failed" in response.json()["detail"]
    assert (drop / "ga-pages.csv").exists()
    assert not (drop / "_archive").exists()


def test_admin_html_links_to_demand_import_template(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "/api/tenants/algolia/argus/demand-imports/template" in response.text
    assert "Download demand template" in response.text
    assert "/api/tenants/algolia/argus/demand-imports/template?planned=1" in response.text
    assert "Download Argus demand plan template" in response.text
    assert "/api/tenants/algolia/argus/demand-imports/work-order" in response.text
    assert "View demand work-order guide" in response.text
    assert 'action="/admin/algolia/argus/demand-imports/refresh"' in response.text
    assert "Prepare demand and refresh Argus" in response.text


def test_json_api_refreshes_argus_from_evidence_ledger() -> None:
    runner = FakeLedgerRefreshRunner()
    client = _client(token="secret", ledger_refresh_runner=runner)

    response = client.post(
        "/api/tenants/algolia/argus/ledger-refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "actionable"
    assert payload["intelligence_brief"]["top_insight"].startswith("Ledger replay")
    assert runner.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "own_company_name": "Algolia",
            "days": 30,
            "limit": 500,
        }
    ]


def test_admin_html_can_refresh_argus_from_evidence_ledger() -> None:
    runner = FakeLedgerRefreshRunner()
    client = _client(token="secret", ledger_refresh_runner=runner)

    response = client.post(
        "/admin/algolia/argus/ledger-refresh",
        headers={"x-cios-admin-token": "secret"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    assert runner.calls[0]["tenant_id"] == 1
    assert runner.calls[0]["own_company_name"] == "Algolia"


def test_admin_default_ledger_refresh_runner_reads_demand_quality_env(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSummary:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"verdict": "watch", "demand_quality": captured["demand_quality"]}

    def fake_connect(*args, **kwargs):
        return FakeConn()

    def fake_refresh(**kwargs):
        captured.update(kwargs)
        return FakeSummary()

    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR", "0.04")
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR", "40")
    monkeypatch.setattr(admin_app.psycopg, "connect", fake_connect)
    monkeypatch.setattr(admin_app, "run_product_market_ledger_refresh", fake_refresh)
    client = TestClient(
        create_app(
            repository=FakeAdminRepository(),
            dsn="postgresql://cios_app@example.test/cios",
            admin_token="secret",
            allowed_hosts={"testclient"},
        )
    )

    response = client.post(
        "/api/tenants/algolia/argus/ledger-refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["demand_quality"] == {"change_floor": 0.04, "value_floor": 40.0}
    assert captured["demand_quality"] == {"change_floor": 0.04, "value_floor": 40.0}


def _clear_ga4_env(monkeypatch) -> None:
    for key in [
        "CIOS_GA4_EXPORT_ENABLED",
        "CIOS_GA4_PROPERTY_ID",
        "CIOS_GA4_CURRENT_START",
        "CIOS_GA4_CURRENT_END",
        "CIOS_GA4_PREVIOUS_START",
        "CIOS_GA4_PREVIOUS_END",
        "CIOS_GA4_TOPIC_DIMENSION",
        "CIOS_GA4_URL_DIMENSION",
        "CIOS_GA4_METRIC",
        "CIOS_GA4_LIMIT",
        "CIOS_GA4_SOURCE_URL",
        "CIOS_GA4_CREDENTIALS_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CIOS_GA4_EXPORT_SCRIPT",
        "CIOS_GA4_ROLLING_DAYS",
        "CIOS_GA4_TODAY",
    ]:
        monkeypatch.delenv(key, raising=False)


def _configure_ready_ga4(monkeypatch, tmp_path):
    _clear_ga4_env(monkeypatch)
    app_dir = tmp_path / "cios"
    script = tmp_path / "export_ga4_demand.py"
    credentials = tmp_path / "private" / "service-account.json"
    script.write_text("# fake script path for readiness\n", encoding="utf-8")
    credentials.parent.mkdir(parents=True)
    credentials.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_GA4_EXPORT_ENABLED", "1")
    monkeypatch.setenv("CIOS_GA4_PROPERTY_ID", "properties/123456")
    monkeypatch.setenv("CIOS_GA4_CURRENT_START", "2026-07-01")
    monkeypatch.setenv("CIOS_GA4_CURRENT_END", "2026-07-08")
    monkeypatch.setenv("CIOS_GA4_PREVIOUS_START", "2026-06-24")
    monkeypatch.setenv("CIOS_GA4_PREVIOUS_END", "2026-06-30")
    monkeypatch.setenv("CIOS_GA4_CREDENTIALS_JSON", str(credentials))
    monkeypatch.setenv("CIOS_GA4_EXPORT_SCRIPT", str(script))
    return app_dir, credentials, script


def test_json_api_returns_ga4_export_readiness_without_secret_values(tmp_path, monkeypatch) -> None:
    _app_dir, credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    client = _client()

    response = client.get("/api/tenants/algolia/argus/ga4-export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_slug"] == "algolia"
    assert payload["enabled"] is True
    assert payload["ready"] is True
    assert payload["missing_required"] == []
    assert payload["property_configured"] is True
    assert payload["credentials_configured"] is True
    assert payload["credentials_path_exists"] is True
    assert payload["current_start"] == "2026-07-01"
    assert payload["current_end"] == "2026-07-08"
    assert payload["metric"] == "engagedSessions"
    assert payload["output_path"].endswith("/data/looker/algolia/ga4-demand.json")
    assert str(credentials) not in response.text
    assert "123456" not in response.text


def test_json_api_marks_ga4_ready_with_rolling_date_window(tmp_path, monkeypatch) -> None:
    _app_dir, credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    monkeypatch.delenv("CIOS_GA4_CURRENT_START", raising=False)
    monkeypatch.delenv("CIOS_GA4_CURRENT_END", raising=False)
    monkeypatch.delenv("CIOS_GA4_PREVIOUS_START", raising=False)
    monkeypatch.delenv("CIOS_GA4_PREVIOUS_END", raising=False)
    monkeypatch.setenv("CIOS_GA4_TODAY", "2026-07-12")
    client = _client()

    response = client.get("/api/tenants/algolia/argus/ga4-export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["current_start"] == "2026-07-05"
    assert payload["current_end"] == "2026-07-11"
    assert payload["previous_start"] == "2026-06-28"
    assert payload["previous_end"] == "2026-07-04"
    assert payload["missing_required"] == []
    assert str(credentials) not in response.text


def test_json_api_blocks_ga4_export_when_not_ready(monkeypatch) -> None:
    _clear_ga4_env(monkeypatch)
    monkeypatch.setenv("CIOS_GA4_EXPORT_ENABLED", "1")
    client = _client(token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/ga4-export",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "CIOS_GA4_PROPERTY_ID" in detail
    assert "CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS" in detail


def test_json_api_runs_ga4_export_to_tenant_drop_folder_when_ready(tmp_path, monkeypatch) -> None:
    app_dir, credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        assert kwargs["timeout"] == 60.0
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        output = app_dir / "data" / "looker" / "algolia" / "ga4-demand.json"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "ok", "output": str(output), "record_count": 2}),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)
    client = _client(token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/ga4-export",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    expected_output = app_dir / "data" / "looker" / "algolia" / "ga4-demand.json"
    assert payload["tenant_slug"] == "algolia"
    assert payload["status"] == "exported"
    assert payload["record_count"] == 2
    assert payload["output_path"] == str(expected_output)
    assert payload["credentials_configured"] is True
    assert str(credentials) not in response.text
    assert calls
    command = calls[0]
    assert "--credentials-json" in command
    assert command[command.index("--credentials-json") + 1] == str(credentials)
    assert command[command.index("--output") + 1] == str(expected_output)


def test_json_api_runs_ga4_export_and_refreshes_argus_in_one_operator_action(tmp_path, monkeypatch) -> None:
    app_dir, credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    work_root = tmp_path / "work"
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    events: list[str] = []
    runner = FakeLedgerRefreshRunner(events=events)
    dashboard_runner = FakeDashboardRefreshRunner(events=events)
    persister = FakeDemandImportLedgerPersister(events=events)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "topic": "AI Shopping Agent guide",
                            "metric": "engaged_sessions",
                            "value": 240.0,
                            "change_pct": 0.5,
                            "period_start": "2026-07-01T00:00:00+00:00",
                            "period_end": "2026-07-08T00:00:00+00:00",
                            "source_label": "GA4 Data API export",
                            "source_url": "ga4://properties/123456/runReport",
                            "excerpt": "pageTitle: AI Shopping Agent guide",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "ok", "output": str(output), "record_count": 1}),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)
    client = _client(
        token="secret",
        ledger_refresh_runner=runner,
        dashboard_refresh_runner=dashboard_runner,
        demand_import_ledger_persister=persister,
    )

    response = client.post(
        "/api/tenants/algolia/argus/ga4-export/refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    expected_output = app_dir / "data" / "looker" / "algolia" / "ga4-demand.json"
    expected_normalized = work_root / "algolia" / "looker-normalized" / "ga4-demand.normalized.json"
    assert payload["status"] == "ga4_exported_and_argus_refreshed"
    assert payload["ga4_export"]["status"] == "exported"
    assert payload["ga4_export"]["record_count"] == 1
    assert payload["ga4_export"]["output_path"] == str(expected_output)
    assert payload["demand_import"]["normalized_row_count"] == 1
    assert payload["demand_import"]["payload_paths"] == [str(expected_normalized)]
    assert payload["demand_ledger"]["demand_signal_count"] == 1
    assert payload["ledger_refresh"]["verdict"] == "actionable"
    assert payload["argus_read"]["demand_summary"] == "1 rising demand topic found; 1 matched product proof."
    assert payload["dashboard_refresh"]["status"] == "published"
    assert payload["archive"]["archived_count"] == 1
    assert not expected_output.exists()
    archived = list((expected_output.parent / "_archive").glob("*/ga4-demand.json"))
    assert len(archived) == 1
    assert persister.calls == [{"tenant_id": 1, "payload_paths": [str(expected_normalized)]}]
    assert runner.calls[0]["tenant_id"] == 1
    assert dashboard_runner.calls == [{"tenant_slug": "algolia"}]
    assert events == ["persist", "refresh", "dashboard"]
    assert calls[0][calls[0].index("--output") + 1] == str(expected_output)
    assert str(credentials) not in response.text


def test_json_api_ga4_export_refresh_passes_argus_demand_plan_to_export_script(
    tmp_path,
    monkeypatch,
) -> None:
    app_dir, _credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    work_root = tmp_path / "work"
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    manifest = FakeDataPlaneManifestStore()
    manifest.payload["planes"]["audience_demand"]["details"] = {
            "demand_collection_plan": {
                "status": "needs_demand_source",
                "topic_count": 1,
                "topics": [
                    {
                        "topic": "AI Shopping Agent",
                        "capability_key": "ai shopping agent",
                        "suggested_filter_terms": ["AI Shopping Agent", "agentic commerce"],
                    }
                ],
            }
    }
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        assert "--demand-plan" in calls[-1]
        demand_plan_path = Path(calls[-1][calls[-1].index("--demand-plan") + 1])
        demand_plan = json.loads(demand_plan_path.read_text(encoding="utf-8"))
        assert demand_plan["topic_count"] == 1
        assert demand_plan["topics"][0]["capability_key"] == "ai shopping agent"
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "topic": "AI Shopping Agent",
                            "metric": "engaged_sessions",
                            "value": 240.0,
                            "period_start": "2026-07-01T00:00:00+00:00",
                            "period_end": "2026-07-08T00:00:00+00:00",
                            "source_label": "GA4 Data API export",
                            "source_url": "ga4://properties/123456/runReport",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "ok",
                    "output": str(output),
                    "record_count": 1,
                    "demand_plan_status": "partial_coverage",
                    "demand_plan_topic_count": 1,
                    "matched_plan_topic_count": 1,
                    "off_plan_record_count": 0,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)
    client = _client(
        token="secret",
        data_plane_manifest_store=manifest,
        ledger_refresh_runner=FakeLedgerRefreshRunner(),
        dashboard_refresh_runner=FakeDashboardRefreshRunner(),
        demand_import_ledger_persister=FakeDemandImportLedgerPersister(),
    )

    response = client.post(
        "/api/tenants/algolia/argus/ga4-export/refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    demand_plan_path = app_dir / "data" / "looker" / "algolia" / "argus-demand-plan.json"
    assert payload["ga4_export"]["demand_plan_path"] == str(demand_plan_path)
    assert payload["ga4_export"]["demand_plan_status"] == "partial_coverage"
    assert payload["ga4_export"]["matched_plan_topic_count"] == 1
    assert calls


def test_json_api_blocks_ga4_refresh_when_dashboard_refresh_fails(tmp_path, monkeypatch) -> None:
    _app_dir, _credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(tmp_path / "work"))

    def fake_run(cmd, **kwargs):
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "topic": "AI Shopping Agent guide",
                            "metric": "engaged_sessions",
                            "value": 240.0,
                            "period_start": "2026-07-01T00:00:00+00:00",
                            "period_end": "2026-07-08T00:00:00+00:00",
                            "source_label": "GA4 Data API export",
                            "source_url": "ga4://properties/123456/runReport",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "ok", "output": str(output), "record_count": 1}),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)
    client = _client(
        token="secret",
        ledger_refresh_runner=FakeLedgerRefreshRunner(),
        demand_import_ledger_persister=FakeDemandImportLedgerPersister(),
        dashboard_refresh_runner=FakeDashboardRefreshRunner(error=RuntimeError("dashboard rerender failed")),
    )

    response = client.post(
        "/api/tenants/algolia/argus/ga4-export/refresh",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 502
    assert "dashboard rerender failed" in response.json()["detail"]
    assert (_app_dir / "data" / "looker" / "algolia" / "ga4-demand.json").exists()
    assert not (_app_dir / "data" / "looker" / "algolia" / "_archive").exists()


def test_admin_html_shows_ga4_connector_and_form(tmp_path, monkeypatch) -> None:
    _app_dir, credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "GA4 connector" in response.text
    assert "ready" in response.text
    assert "Run GA4 export now" in response.text
    assert 'action="/admin/algolia/argus/ga4-export"' in response.text
    assert "Run GA4 export and refresh Argus" in response.text
    assert 'action="/admin/algolia/argus/ga4-export/refresh"' in response.text
    assert str(credentials) not in response.text


def test_admin_html_explains_disabled_ga4_connector_setup(monkeypatch) -> None:
    _clear_ga4_env(monkeypatch)
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "GA4 export is disabled." in response.text
    assert "Connector setup needed" in response.text
    assert "Set CIOS_GA4_EXPORT_ENABLED=1" in response.text
    assert "CIOS_GA4_PROPERTY_ID" in response.text
    assert "CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS" in response.text
    assert 'disabled aria-disabled="true"' in response.text


def test_admin_html_can_run_ga4_export_when_ready(tmp_path, monkeypatch) -> None:
    _app_dir, credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "ok", "output": "ga4-demand.json", "record_count": 1}),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)
    client = _client(token="secret")

    response = client.post(
        "/admin/algolia/argus/ga4-export",
        headers={"x-cios-admin-token": "secret"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    assert calls
    assert str(credentials) in calls[0]


def test_admin_html_can_run_ga4_export_and_refresh_argus_when_ready(tmp_path, monkeypatch) -> None:
    app_dir, _credentials, _script = _configure_ready_ga4(monkeypatch, tmp_path)
    work_root = tmp_path / "work"
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(work_root))
    events: list[str] = []
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "topic": "AI Shopping Agent guide",
                            "metric": "engaged_sessions",
                            "value": 240.0,
                            "period_start": "2026-07-01T00:00:00+00:00",
                            "period_end": "2026-07-08T00:00:00+00:00",
                            "source_label": "GA4 Data API export",
                            "source_url": "ga4://properties/123456/runReport",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "ok", "output": str(output), "record_count": 1}),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)
    runner = FakeLedgerRefreshRunner(events=events)
    dashboard_runner = FakeDashboardRefreshRunner(events=events)
    persister = FakeDemandImportLedgerPersister(events=events)
    client = _client(
        token="secret",
        ledger_refresh_runner=runner,
        dashboard_refresh_runner=dashboard_runner,
        demand_import_ledger_persister=persister,
    )

    response = client.post(
        "/admin/algolia/argus/ga4-export/refresh",
        headers={"x-cios-admin-token": "secret"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    drop = app_dir / "data" / "looker" / "algolia"
    assert not (drop / "ga4-demand.json").exists()
    archived = list((drop / "_archive").glob("*/ga4-demand.json"))
    assert len(archived) == 1
    assert (work_root / "algolia" / "looker-normalized" / "ga4-demand.normalized.json").exists()
    assert persister.calls == [
        {
            "tenant_id": 1,
            "payload_paths": [str(work_root / "algolia" / "looker-normalized" / "ga4-demand.normalized.json")],
        }
    ]
    assert runner.calls[0]["tenant_id"] == 1
    assert dashboard_runner.calls == [{"tenant_slug": "algolia"}]
    assert events == ["persist", "refresh", "dashboard"]
    assert calls


def test_json_api_runs_argus_demand_intake_with_tenant_context() -> None:
    control = FakeDemandIntakeControl()
    client = _client(demand_intake_control=control)

    response = client.post("/api/tenants/algolia/argus/demand-intake")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked_missing_demand_source"
    assert payload["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert control.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "own_company_name": "Algolia",
            "days": 30,
            "limit": 500,
            "command_timeout_seconds": 300.0,
        }
    ]


def test_json_api_runs_argus_demand_intake_with_demand_quality_env(monkeypatch) -> None:
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR", "0.03")
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR", "25")
    control = FakeDemandIntakeControl()
    client = _client(demand_intake_control=control)

    response = client.post("/api/tenants/algolia/argus/demand-intake")

    assert response.status_code == 200
    assert control.calls[0]["demand_quality"] == {"change_floor": 0.03, "value_floor": 25.0}


def test_json_api_returns_argus_demand_intake_history() -> None:
    history_store = FakeDemandIntakeHistoryStore()
    client = _client(demand_intake_history_store=history_store)

    response = client.get("/api/tenants/algolia/argus/demand-intake")

    assert response.status_code == 200
    payload = response.json()
    assert payload["attempt_count"] == 1
    assert payload["latest"]["status"] == "blocked_missing_demand_source"
    assert payload["latest"]["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert history_store.calls == ["algolia"]


def test_admin_html_shows_argus_demand_intake_action_and_history() -> None:
    history_store = FakeDemandIntakeHistoryStore()
    client = _client(demand_intake_history_store=history_store)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus demand intake" in response.text
    assert "Run demand intake" in response.text
    assert 'action="/admin/algolia/argus/demand-intake"' in response.text
    assert "blocked_missing_demand_source" in response.text
    assert "configure_ga4_or_upload_demand_export" in response.text


def test_admin_form_runs_argus_demand_intake_and_redirects() -> None:
    control = FakeDemandIntakeControl()
    client = _client(demand_intake_control=control)

    response = client.post(
        "/admin/algolia/argus/demand-intake",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia#argus-demand-intake"
    assert control.calls[0]["tenant_slug"] == "algolia"
    assert control.calls[0]["tenant_id"] == 1


def test_admin_html_lists_competitors_sources_and_add_forms() -> None:
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Constructor" in response.text
    assert "https://constructor.com/blog" in response.text
    assert "https://docs.constructor.com/" in response.text
    assert "Add competitor" in response.text
    assert "Add source" in response.text
    assert "Add product surface" in response.text
    assert "Argus learning queue" in response.text
    assert "Argus run console" in response.text
    assert "Demand imports" in response.text
    assert "Upload GA / Looker export" in response.text
    assert "Demand source contract" in response.text
    assert "Manual GA / Looker export" in response.text
    assert "GA4 API export" in response.text
    assert "waiting_for_upload" in response.text
    assert "disabled" in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert 'type="file" name="file"' in response.text
    assert "Queued demand preview" in response.text
    assert "Refresh Argus from evidence ledger" in response.text
    assert "Product-market chain" in response.text
    assert "Inward demand" in response.text
    assert "0 demand rows" in response.text
    assert "Learning apply plan" in response.text
    assert "1 package action" in response.text
    assert "source_coverage_policy" in response.text
    assert "config/source-coverage-policy.yaml" in response.text
    assert "Prepare apply proposals" in response.text
    assert "Apply approved policies" in response.text
    assert "ran" in response.text
    assert "Coveo" in response.text
    assert "coverage_recheck" in response.text
    assert "User challenged recommendation 7" in response.text
    assert "Re-evaluate recommendation 7" in response.text
    assert "Pause" in response.text
    assert "Retire" in response.text
    assert "Approve" in response.text
    assert "Reject" in response.text
    assert 'action="/admin/algolia/sources"' in response.text
    assert 'action="/admin/algolia/product-surfaces"' in response.text
    assert 'action="/admin/algolia/argus/demand-imports"' in response.text
    assert 'action="/admin/algolia/argus/ledger-refresh"' in response.text
    assert 'action="/admin/algolia/argus/learning-apply/execute"' in response.text
    assert 'action="/admin/algolia/competitors/1/status"' in response.text
    assert 'action="/admin/algolia/competitors/1"' in response.text
    assert 'aria-label="Edit competitor Constructor"' in response.text
    assert 'action="/admin/algolia/sources/10/status"' in response.text
    assert 'action="/admin/algolia/sources/10"' in response.text
    assert 'aria-label="Edit source 10"' in response.text
    assert 'action="/admin/algolia/product-surfaces/30/status"' in response.text
    assert 'action="/admin/algolia/product-surfaces/30"' in response.text
    assert 'aria-label="Edit product surface 30"' in response.text
    assert 'action="/admin/algolia/argus/improvements/202/status"' in response.text


def test_admin_html_shows_learning_apply_artifacts(tmp_path, monkeypatch) -> None:
    package_root = tmp_path / "cios"
    _write_learning_apply_artifacts(package_root)
    monkeypatch.setenv("CIOS_APP_DIR", str(package_root))
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus learning apply" in response.text
    assert "Learning policy audit" in response.text
    assert "Policy audit clean" in response.text
    assert "Pending package proposals" in response.text
    assert "Approved package policies" in response.text
    assert "pending_human_approval" in response.text
    assert "approved_policy_written" in response.text
    assert "source_retry_policy" in response.text
    assert "source_coverage_policy" in response.text
    assert "config/source-retry-policy.yaml" in response.text
    assert "arijit" in response.text


def test_admin_html_shows_learning_policy_audit_failure(tmp_path, monkeypatch) -> None:
    package_root = tmp_path / "cios"
    _write_learning_apply_artifacts(package_root)
    policy_path = package_root / "config" / "source-retry-policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    payload["policies"][0]["summary"] = "Changed after approval without re-approval."
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("CIOS_APP_DIR", str(package_root))
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Learning policy audit" in response.text
    assert "Policy audit failed" in response.text
    assert "action_id_drift" in response.text
    assert "restore the approved policy fields" in response.text


def test_admin_html_previews_queued_demand_export(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Queued demand preview" in response.text
    assert "ga-pages.csv" in response.text
    assert "AI Shopping Agent" in response.text
    assert "queued valid rows" in response.text


def test_admin_html_shows_demand_manifest_skipped_row_diagnostics(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "cios"
    work_dir = tmp_path / "work" / "algolia"
    work_dir.mkdir(parents=True)
    manifest = work_dir / "looker-export-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tenant": "algolia",
                "discovered_count": 1,
                "ready_count": 0,
                "error_count": 0,
                "normalized_row_count": 0,
                "skipped_row_count": 1,
                "files": [
                    {
                        "path": "bad-ga-pages.csv",
                        "status": "empty",
                        "raw_row_count": 1,
                        "normalized_row_count": 0,
                        "skipped_row_count": 1,
                        "skipped_rows": [
                            {
                                "row_number": 1,
                                "reason": "missing_topic",
                                "missing_fields": ["topic"],
                                "source_file": "bad-ga-pages.csv",
                                "available_columns": [
                                    "Date range",
                                    "Engaged sessions",
                                    "Landing page + query string",
                                    "Page title and screen name",
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CIOS_APP_DIR", str(app_dir))
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORK_DIR", str(tmp_path / "work"))
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Demand import diagnostics" in response.text
    assert "bad-ga-pages.csv" in response.text
    assert "missing_topic" in response.text
    assert "missing fields: topic" in response.text
    assert "available columns: Date range, Engaged sessions, Landing page + query string, Page title and screen name" in response.text


def test_json_api_adds_competitor() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    response = client.post(
        "/api/tenants/algolia/competitors",
        json={"name": "Coveo", "domain": "coveo.com", "category": "commerce search", "priority": 2},
    )

    assert response.status_code == 200
    assert response.json()["competitor_name"] == "Coveo"
    assert repo.created_competitor is not None
    assert repo.created_competitor.name == "Coveo"


def test_json_api_pauses_and_retires_competitor() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    paused = client.post("/api/tenants/algolia/competitors/1/status", json={"status": "paused"})
    retired = client.post("/api/tenants/algolia/competitors/1/status", json={"status": "retired"})

    assert paused.status_code == 200
    assert retired.status_code == 200
    assert repo.updated_competitor is not None
    assert repo.updated_competitor[1].status == "retired"


def test_json_api_adds_and_pauses_source() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    created = client.post(
        "/api/tenants/algolia/competitors/1/sources",
        json={"source_family": "blog", "url": "https://constructor.com/news", "status": "active"},
    )
    paused = client.post("/api/tenants/algolia/sources/11/status", json={"status": "blocked"})

    assert created.status_code == 200
    assert paused.status_code == 200
    assert repo.created_source is not None
    assert repo.created_source[0] == 1
    assert repo.updated_source is not None
    assert repo.updated_source[1].status == "blocked"


def test_json_api_adds_and_pauses_product_surface() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    created = client.post(
        "/api/tenants/algolia/competitors/1/product-surfaces",
        json={"surface_family": "docs", "url": "https://docs.constructor.com/", "status": "active"},
    )
    paused = client.post("/api/tenants/algolia/product-surfaces/31/status", json={"status": "paused"})

    assert created.status_code == 200
    assert paused.status_code == 200
    assert repo.created_product_surface is not None
    assert repo.created_product_surface[0] == 1
    assert repo.updated_product_surface is not None
    assert repo.updated_product_surface[1].status == "paused"


def test_json_api_records_argus_recommendation_challenge() -> None:
    recorder = FakeRecommendationChallengeRecorder()
    client = _client(challenge_recorder=recorder)

    response = client.post(
        "/api/tenants/algolia/argus/recommendations/7/challenge",
        json={
            "challenge": "Why prioritize Constructor when Coveo coverage is degraded?",
            "category": "scoring",
            "run_id": "run-2026-07-10",
            "scorecard_dimension": "audience_demand",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "learning_event_id": 101,
        "improvement_id": 202,
        "next_sweep_instruction": "re-evaluate audience demand in the next sweep",
    }
    assert recorder.calls == [
        {
            "tenant_id": 1,
            "recommendation_id": 7,
            "run_id": "run-2026-07-10",
            "challenge": "Why prioritize Constructor when Coveo coverage is degraded?",
            "category": "scoring",
            "scorecard_dimension": "audience_demand",
        }
    ]


def test_json_api_lists_and_updates_argus_improvements() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    listed = client.get("/api/tenants/algolia/argus/improvements")
    approved = client.post(
        "/api/tenants/algolia/argus/improvements/202/status",
        json={"status": "approved"},
    )

    assert listed.status_code == 200
    assert listed.json()[0]["improvement_id"] == 202
    assert listed.json()[0]["priority"] == "critical"
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert repo.updated_improvement is not None
    assert repo.updated_improvement[0] == 202
    assert repo.updated_improvement[1].status == "approved"


def test_json_api_returns_argus_next_sweep_learning_plan() -> None:
    client = _client()

    response = client.get("/api/tenants/algolia/argus/next-sweep-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 1
    assert payload["instructions"][0]["source_improvement_ids"] == [202]
    assert payload["instructions"][0]["evidence_event_ids"] == [101]
    assert payload["instructions"][0]["status"] == "ready_for_next_sweep"
    assert "source coverage" in payload["instructions"][0]["instruction"]


def test_json_api_returns_argus_evidence_work_queue_for_missing_demand() -> None:
    repo = FakeAdminRepository()
    repo.run_status_payload["run_intelligence_history"][0]["demand_signal_count"] = 0
    repo.run_status_payload["run_intelligence_history"][0]["confidence_limits"] = [
        "Demand evidence is missing, so Argus withheld owner recommendations."
    ]
    repo.evidence_ledger_payload["demand_signals"] = []
    client = _client(repo)

    response = client.get("/api/tenants/algolia/argus/evidence-work-queue")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["work_item_id"] == "argus-evidence:88:demand"
    assert payload[0]["evidence_plane"] == "demand"
    assert payload[0]["severity"] == "blocks_action"
    assert payload[0]["title"] == "Demand plane missing"
    assert payload[0]["next_step"] == "Upload GA4 / Looker demand export for the current and previous periods."
    assert payload[0]["operator_surface"] == "Demand imports"
    assert payload[0]["primary_action_label"] == "Download demand template"
    assert payload[0]["primary_action_href"] == "/api/tenants/algolia/argus/demand-imports/template"
    assert payload[0]["secondary_action_label"] == "Prepare demand and refresh Argus"
    assert payload[0]["secondary_action_href"] == "/admin/algolia/argus/demand-imports/refresh"
    assert payload[0]["accepted_input_formats"] == ["csv", "json", "jsonl"]
    assert "Page title" in payload[0]["required_fields"]
    assert payload[0]["observed_state"]["demand_plane_status"] == "missing"
    assert payload[0]["observed_state"]["looker_normalized_row_count"] == 0


def test_json_api_returns_argus_product_muscle_work_queue_for_uncovered_competitors() -> None:
    repo = FakeAdminRepository()
    repo.competitors.append(
        {
            "competitor_id": 2,
            "competitor_name": "Bloomreach",
            "domain": "bloomreach.com",
            "category": "commerce search",
            "priority": 2,
            "status": "active",
            "sources": [],
            "product_surfaces": [],
        }
    )
    client = _client(repo)

    response = client.get("/api/tenants/algolia/argus/product-muscle-work-queue")

    assert response.status_code == 200
    payload = response.json()
    bloomreach = next(item for item in payload if item["company_name"] == "Bloomreach")
    assert bloomreach["work_item_id"] == "product-muscle:competitor:2:missing-surfaces"
    assert bloomreach["severity"] == "blocks_feature_matrix"
    assert bloomreach["title"] == "Bloomreach has no active product surfaces"
    assert bloomreach["primary_action_label"] == "Add product surface"
    assert bloomreach["primary_action_href"] == "/admin?tenant=algolia#add-product-surface"
    assert bloomreach["secondary_action_label"] == "Refresh Argus from evidence ledger"
    assert bloomreach["secondary_action_href"] == "/admin/algolia/argus/ledger-refresh"
    assert bloomreach["observed_state"]["active_product_surface_count"] == 0
    assert bloomreach["observed_state"]["known_capability_cell_count"] == 0


def test_json_api_enriches_product_muscle_queue_with_latest_surface_execution_trace(
    tmp_path, monkeypatch
) -> None:
    work_root = tmp_path / "product-market"
    tenant_root = work_root / "algolia"
    export_dir = tenant_root / "surface-exports"
    export_dir.mkdir(parents=True)
    output = export_dir / "000030-coveo-docs.json"
    output.write_text("[]", encoding="utf-8")
    plan = {
        "tenant_id": 1,
        "items": [
            {
                "target": {
                    "company_id": 2,
                    "company_name": "Coveo",
                    "company_role": "competitor",
                    "surface_family": "docs",
                    "surface_id": 30,
                    "tenant_id": 1,
                    "url": "https://docs.coveo.com/",
                },
                "output_path": str(output),
                "command": ["python", "export_product_surface_with_scout.py"],
            }
        ],
    }
    summary = {
        "planned": 1,
        "succeeded": 1,
        "failed": 0,
        "scout_paths": [str(output)],
        "results": [
            {
                "status": "succeeded",
                "output_path": str(output),
                "returncode": 0,
            }
        ],
    }
    (tenant_root / "product-surface-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tenant_root / "product-surface-execution-summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORKDIR", str(work_root))
    repo = FakeAdminRepository()
    repo.competitors = [
        {
            "competitor_id": 2,
            "competitor_name": "Coveo",
            "domain": "coveo.com",
            "category": "commerce search",
            "priority": 2,
            "status": "active",
            "sources": [],
            "product_surfaces": [
                {
                    "surface_id": 30,
                    "company_name": "Coveo",
                    "company_role": "competitor",
                    "surface_family": "docs",
                    "url": "https://docs.coveo.com/",
                    "status": "active",
                    "last_checked_at": None,
                }
            ],
        }
    ]
    repo.feature_matrix_rows = []
    repo.evidence_ledger_payload["product_events"] = []
    client = _client(repo)

    response = client.get("/api/tenants/algolia/argus/product-muscle-work-queue")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    state = payload[0]["observed_state"]
    assert state["latest_surface_export_planned_count"] == 1
    assert state["latest_surface_export_succeeded_count"] == 1
    assert state["latest_surface_export_failed_count"] == 0
    assert state["latest_surface_export_row_count"] == 0
    assert state["latest_surface_export_empty_output_count"] == 1
    assert state["latest_surface_export_summary_path"] == str(
        tenant_root / "product-surface-execution-summary.json"
    )


def test_json_api_runs_product_surface_repair_with_bounded_inputs(monkeypatch) -> None:
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR", "0.03")
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR", "25")
    repair_control = FakeProductSurfaceRepairControl()
    repair_refresh_runner = FakeProductSurfaceRepairRefreshRunner()
    client = _client(
        product_surface_repair_control=repair_control,
        product_surface_repair_refresh_runner=repair_refresh_runner,
    )

    response = client.post(
        "/api/tenants/algolia/argus/product-surface-repair",
        json={
            "company_name": "Coveo",
            "category": "no_markdown",
            "use_js": True,
            "repair_timeout_seconds": 240,
            "command_timeout_seconds": 260,
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["selected"] == 1
    assert payload["argus_refresh"]["product_event_count"] == 1
    assert payload["argus_read"]["top_insight"] == "Repair imported one product proof row."
    assert repair_control.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "company_name": "Coveo",
            "company_id": None,
            "surface_id": None,
            "category": "no_markdown",
            "use_js": True,
            "repair_timeout_seconds": 240.0,
            "command_timeout_seconds": 260.0,
            "limit": 1,
        }
    ]
    assert repair_refresh_runner.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "own_company_name": "Algolia",
            "scout_paths": ["/tmp/cios-product-market/algolia/product-surface-repairs/repair.json"],
            "demand_quality": {"change_floor": 0.03, "value_floor": 25.0},
        }
    ]


def test_json_api_runs_product_surface_extraction_with_company_filter_and_refresh(monkeypatch) -> None:
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR", "0.03")
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR", "25")
    extraction_control = FakeProductSurfaceExtractionControl()
    refresh_runner = FakeProductSurfaceRepairRefreshRunner(
        result={
            "verdict": "watch",
            "product_event_count": 2,
            "conversation_theme_count": 0,
            "demand_signal_count": 0,
            "pattern_count": 1,
            "recommendation_count": 0,
            "intelligence_brief": {
                "top_insight": "Extraction imported two Klevu product proof rows.",
                "primary_action": None,
                "confidence_limits": ["Demand plane is still missing."],
            },
        }
    )
    client = _client(
        product_surface_extraction_control=extraction_control,
        product_surface_repair_refresh_runner=refresh_runner,
    )

    response = client.post(
        "/api/tenants/algolia/argus/product-surface-extraction",
        json={
            "company_name": "Klevu",
            "focus_capability": "Channel Assistant",
            "use_js": True,
            "timeout_seconds": 160,
            "command_timeout_seconds": 220,
            "max_workers": 2,
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["planned"] == 1
    assert payload["succeeded"] == 1
    assert payload["argus_refresh"]["product_event_count"] == 2
    assert payload["argus_read"]["top_insight"] == "Extraction imported two Klevu product proof rows."
    assert extraction_control.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "company_name": "Klevu",
            "focus_capability": "Channel Assistant",
            "company_id": None,
            "surface_id": None,
            "use_js": True,
            "timeout_seconds": 160.0,
            "command_timeout_seconds": 220.0,
            "max_workers": 2,
            "limit": 1,
        }
    ]
    assert refresh_runner.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "own_company_name": "Algolia",
            "scout_paths": ["/tmp/cios-product-market/algolia/surface-exports/000044-klevu-docs.json"],
            "demand_quality": {"change_floor": 0.03, "value_floor": 25.0},
        }
    ]


def test_json_api_promotes_product_surface_candidates_with_company_filter() -> None:
    promotion_control = FakeProductSurfaceCandidatePromotionControl()
    client = _client(product_surface_candidate_promotion_control=promotion_control)

    response = client.post(
        "/api/tenants/algolia/argus/product-surface-candidates/promote",
        json={
            "company_name": "Klevu",
            "company_id": 9,
            "surface_family": "changelog",
            "discovery_source": "product_muscle_gap_plan",
            "promoted_by": "argus",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["promoted_count"] == 1
    assert payload["promoted_surfaces"][0]["company_name"] == "Klevu"
    assert promotion_control.calls == [
        {
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "company_name": "Klevu",
            "company_id": 9,
            "surface_family": "changelog",
            "discovery_source": "product_muscle_gap_plan",
            "promoted_by": "argus",
            "limit": 1,
        }
    ]


def test_json_api_skips_argus_refresh_when_product_surface_repair_has_no_successful_paths() -> None:
    repair_control = FakeProductSurfaceRepairControl(
        result={
            "status": "failed",
            "tenant_id": 1,
            "selected": 1,
            "succeeded": 0,
            "failed": 1,
            "scout_paths": [],
            "results": [{"status": "failed", "error": "HTTP 403"}],
        }
    )
    repair_refresh_runner = FakeProductSurfaceRepairRefreshRunner()
    client = _client(
        product_surface_repair_control=repair_control,
        product_surface_repair_refresh_runner=repair_refresh_runner,
    )

    response = client.post(
        "/api/tenants/algolia/argus/product-surface-repair",
        json={"company_name": "Coveo", "category": "no_markdown"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["argus_refresh"] is None
    assert payload["argus_read"] is None
    assert repair_refresh_runner.calls == []


def test_json_api_returns_product_surface_repair_history() -> None:
    history_store = FakeProductSurfaceRepairHistoryStore()
    client = _client(product_surface_repair_history_store=history_store)

    response = client.get("/api/tenants/algolia/argus/product-surface-repairs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["attempt_count"] == 1
    assert payload["latest"]["company_name"] == "Coveo"
    assert payload["latest"]["error"] == "HTTP 403"
    assert history_store.calls == ["algolia"]


def test_admin_form_runs_product_surface_repair_and_redirects() -> None:
    repair_control = FakeProductSurfaceRepairControl()
    repair_refresh_runner = FakeProductSurfaceRepairRefreshRunner()
    client = _client(
        product_surface_repair_control=repair_control,
        product_surface_repair_refresh_runner=repair_refresh_runner,
    )

    response = client.post(
        "/admin/algolia/argus/product-surface-repair?company_name=Coveo&category=no_markdown",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia#argus-product-muscle-work-queue"
    assert repair_control.calls[0]["tenant_slug"] == "algolia"
    assert repair_control.calls[0]["company_name"] == "Coveo"
    assert repair_control.calls[0]["category"] == "no_markdown"
    assert repair_control.calls[0]["use_js"] is True
    assert repair_refresh_runner.calls[0]["scout_paths"] == [
        "/tmp/cios-product-market/algolia/product-surface-repairs/repair.json"
    ]


def test_admin_html_shows_latest_product_surface_repair_history() -> None:
    history_store = FakeProductSurfaceRepairHistoryStore()
    client = _client(product_surface_repair_history_store=history_store)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Latest product-surface repair attempts" in response.text
    assert "Coveo" in response.text
    assert "no_markdown" in response.text
    assert "HTTP 403" in response.text
    assert "0 imported product events" in response.text


def test_admin_html_shows_argus_evidence_work_queue_actions() -> None:
    repo = FakeAdminRepository()
    repo.run_status_payload["run_intelligence_history"][0]["demand_signal_count"] = 0
    repo.run_status_payload["run_intelligence_history"][0]["confidence_limits"] = [
        "Demand evidence is missing, so Argus withheld owner recommendations."
    ]
    repo.evidence_ledger_payload["demand_signals"] = []
    client = _client(repo)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus evidence work queue" in response.text
    assert "Demand plane missing" in response.text
    assert "Demand evidence is missing, so Argus withheld owner recommendations." in response.text
    assert "Upload GA4 / Looker demand export for the current and previous periods." in response.text
    assert 'href="/api/tenants/algolia/argus/demand-imports/template"' in response.text
    assert 'action="/admin/algolia/argus/demand-imports/refresh"' in response.text


def test_admin_html_shows_argus_product_muscle_work_queue() -> None:
    repo = FakeAdminRepository()
    repo.competitors.append(
        {
            "competitor_id": 2,
            "competitor_name": "Bloomreach",
            "domain": "bloomreach.com",
            "category": "commerce search",
            "priority": 2,
            "status": "active",
            "sources": [],
            "product_surfaces": [],
        }
    )
    client = _client(repo)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus product muscle work queue" in response.text
    assert "Bloomreach has no active product surfaces" in response.text
    assert "Add a changelog, docs, release notes, API docs, pricing, integration, or product page source." in response.text
    assert 'href="/admin?tenant=algolia#add-product-surface"' in response.text
    assert 'action="/admin/algolia/argus/ledger-refresh"' in response.text


def test_admin_html_shows_product_surface_repair_action_for_classified_failures(
    tmp_path, monkeypatch
) -> None:
    work_root = tmp_path / "product-market"
    tenant_root = work_root / "algolia"
    export_dir = tenant_root / "surface-exports"
    export_dir.mkdir(parents=True)
    output = export_dir / "000030-coveo-docs.json"
    plan = {
        "tenant_id": 1,
        "items": [
            {
                "target": {
                    "company_id": 2,
                    "company_name": "Coveo",
                    "company_role": "competitor",
                    "surface_family": "docs",
                    "surface_id": 30,
                    "tenant_id": 1,
                    "url": "https://docs.coveo.com/",
                },
                "output_path": str(output),
                "command": ["python", "export_product_surface_with_scout.py"],
            }
        ],
    }
    summary = {
        "planned": 1,
        "succeeded": 0,
        "failed": 1,
        "results": [
            {
                "status": "failed",
                "output_path": str(output),
                "returncode": 1,
                "error": "Scout product surface scrape returned no markdown",
            }
        ],
    }
    (tenant_root / "product-surface-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tenant_root / "product-surface-execution-summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    monkeypatch.setenv("CIOS_PRODUCT_MARKET_WORKDIR", str(work_root))
    repo = FakeAdminRepository()
    repo.competitors = [
        {
            "competitor_id": 2,
            "competitor_name": "Coveo",
            "domain": "coveo.com",
            "category": "commerce search",
            "priority": 2,
            "status": "active",
            "sources": [],
            "product_surfaces": [
                {
                    "surface_id": 30,
                    "company_name": "Coveo",
                    "company_role": "competitor",
                    "surface_family": "docs",
                    "url": "https://docs.coveo.com/",
                    "status": "active",
                    "last_checked_at": None,
                }
            ],
        }
    ]
    repo.feature_matrix_rows = []
    repo.evidence_ledger_payload["product_events"] = []
    client = _client(repo)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Run repair retry" in response.text
    assert (
        'action="/admin/algolia/argus/product-surface-repair?company_name=Coveo&amp;category=no_markdown"'
        in response.text
    )
    assert 'href="/admin?tenant=algolia#add-product-surface"' in response.text


def test_json_api_returns_argus_operator_handoff_from_hermes_artifact() -> None:
    store = FakeOperatorHandoffStore()
    client = _client(operator_handoff_store=store)

    response = client.get("/api/tenants/algolia/argus/operator-handoff")

    assert response.status_code == 200
    payload = response.json()
    assert store.calls == ["algolia"]
    assert payload["tenant_slug"] == "algolia"
    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["next_operator_action"] == "Upload GA4 / Looker demand export for the current and previous periods."
    assert payload["top_blocker"]["work_item_id"] == "argus-evidence:88:demand"
    assert payload["top_blocker"]["evidence_plane"] == "demand"
    assert payload["primary_command"]["label"] == "Download demand template"
    assert payload["primary_command"]["href"] == "/api/tenants/algolia/argus/demand-imports/template"
    assert payload["demand_collection_plan"]["topic_count"] == 2
    assert payload["demand_collection_plan"]["topics"][0]["topic"] == "Shopping Assistant"
    assert payload["demand_plan_template"]["filename"] == "argus-demand-plan-template.csv"
    assert payload["artifact_found"] is True
    assert payload["artifact_path"] == "/tmp/cios-product-market/algolia/argus-operator-handoff.json"


def test_admin_html_embeds_argus_operator_handoff_in_run_console() -> None:
    client = _client(operator_handoff_store=FakeOperatorHandoffStore())

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus operator handoff" in response.text
    assert "blocked_on_evidence" in response.text
    assert "not_actionable" in response.text
    assert "Argus is blocked by 1 evidence gap before it can promote this run to action." in response.text
    assert "Demand plane missing" in response.text
    assert "Upload GA4 / Looker demand export for the current and previous periods." in response.text
    assert "Argus demand work order" in response.text
    assert "2 topics to collect" in response.text
    assert "Shopping Assistant" in response.text
    assert "Constructor" in response.text
    assert "Channel Assistant" in response.text
    assert "argus-demand-plan-template.csv" in response.text
    assert 'href="/api/tenants/algolia/argus/demand-imports/template"' in response.text
    assert 'href="/api/tenants/algolia/argus/demand-imports/template?planned=1"' in response.text
    assert 'action="/admin/algolia/argus/demand-imports/refresh"' in response.text


def test_json_api_returns_argus_data_plane_manifest_from_hermes_artifact() -> None:
    store = FakeDataPlaneManifestStore()
    client = _client(data_plane_manifest_store=store)

    response = client.get("/api/tenants/algolia/argus/data-plane-manifest")

    assert response.status_code == 200
    payload = response.json()
    assert store.calls == ["algolia"]
    assert payload["tenant_slug"] == "algolia"
    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert payload["source_of_truth"]["runtime"] == "Hermes"
    assert payload["source_of_truth"]["domain_package"] == "CI-OS"
    assert payload["planes"]["audience_demand"]["blocks_action"] is True
    assert payload["planes"]["audience_demand"]["counts"]["demand_signal_count"] == 0
    assert payload["blockers"][0]["title"] == "Demand plane missing"
    assert payload["artifact_found"] is True


def test_admin_html_embeds_argus_operating_planes_in_run_console() -> None:
    client = _client(data_plane_manifest_store=FakeDataPlaneManifestStore())

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus operating planes" in response.text
    assert "Hermes · CI-OS · Postgres evidence ledger" in response.text
    assert "registry coverage" in response.text
    assert "product reality" in response.text
    assert "market conversation" in response.text
    assert "audience demand" in response.text
    assert "operator learning" in response.text
    assert "run truth" in response.text
    assert "blocked_missing_demand_source" in response.text
    assert "Tenant-side demand is missing, so Argus cannot promote outward movement." in response.text
    assert "Next Hermes action: configure_ga4_or_upload_demand_export" in response.text
    assert "Demand plane missing" in response.text


def test_json_api_returns_learning_apply_artifacts(tmp_path, monkeypatch) -> None:
    package_root = tmp_path / "cios"
    _write_learning_apply_artifacts(package_root)
    monkeypatch.setenv("CIOS_APP_DIR", str(package_root))
    client = _client()

    response = client.get("/api/tenants/algolia/argus/learning-apply")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_slug"] == "algolia"
    assert payload["tenant_id"] == 1
    assert payload["proposal_count"] == 2
    assert payload["approved_policy_count"] == 1
    proposal_targets = {item["target"]: item for item in payload["proposals"]}
    assert proposal_targets["source_coverage_policy"]["status"] == "pending_human_approval"
    assert proposal_targets["source_coverage_policy"]["source_improvement_ids"] == [401]
    assert proposal_targets["source_retry_policy"]["status"] == "approved_policy_written"
    policies = {item["target"]: item for item in payload["approved_policies"]}
    assert policies["source_retry_policy"]["approved_by"] == "arijit"
    assert policies["source_retry_policy"]["package_path"] == "config/source-retry-policy.yaml"
    assert policies["source_retry_policy"]["evidence_event_ids"] == [702]
    assert payload["policy_audit"]["passed"] is True
    assert payload["policy_audit"]["policy_count"] == 1
    assert payload["policy_audit"]["issue_count"] == 0


def test_json_api_executes_current_learning_apply_plan_as_proposals(tmp_path, monkeypatch) -> None:
    package_root = tmp_path / "cios"
    plan_path = tmp_path / "runs" / "algolia" / "learning-apply-plan.json"
    _write_learning_apply_plan(plan_path)
    monkeypatch.setenv("CIOS_APP_DIR", str(package_root))
    repo = FakeAdminRepository()
    repo.learning_apply_plan_path = str(plan_path)
    client = _client(repo=repo, token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/learning-apply/execute",
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 1
    assert payload["proposal_count"] == 1
    assert payload["applied_count"] == 0
    assert payload["proposals"][0]["status"] == "pending_human_approval"
    status = LearningApplyArtifactStore(package_root).status("algolia", tenant_id=1)
    assert status.proposal_count == 1
    assert status.approved_policy_count == 0
    assert status.proposals[0].target == "source_coverage_policy"


def test_json_api_executes_current_learning_apply_plan_with_approval(tmp_path, monkeypatch) -> None:
    package_root = tmp_path / "cios"
    plan_path = tmp_path / "runs" / "algolia" / "learning-apply-plan.json"
    _write_learning_apply_plan(plan_path)
    monkeypatch.setenv("CIOS_APP_DIR", str(package_root))
    repo = FakeAdminRepository()
    repo.learning_apply_plan_path = str(plan_path)
    client = _client(repo=repo, token="secret")

    response = client.post(
        "/api/tenants/algolia/argus/learning-apply/execute",
        json={"approved_by": "arijit"},
        headers={"x-cios-admin-token": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["proposal_count"] == 1
    assert payload["applied_count"] == 1
    assert payload["applied"][0]["package_path"] == "config/source-coverage-policy.yaml"
    status = LearningApplyArtifactStore(package_root).status("algolia", tenant_id=1)
    assert status.approved_policy_count == 1
    assert status.approved_policies[0].approved_by == "arijit"
    assert status.approved_policies[0].source_improvement_ids == [401]


def test_admin_html_can_execute_current_learning_apply_plan_with_approval(tmp_path, monkeypatch) -> None:
    package_root = tmp_path / "cios"
    plan_path = tmp_path / "runs" / "algolia" / "learning-apply-plan.json"
    _write_learning_apply_plan(plan_path)
    monkeypatch.setenv("CIOS_APP_DIR", str(package_root))
    repo = FakeAdminRepository()
    repo.learning_apply_plan_path = str(plan_path)
    client = _client(repo=repo, token="secret")

    response = client.post(
        "/admin/algolia/argus/learning-apply/execute",
        data={"approved_by": "arijit"},
        headers={"x-cios-admin-token": "secret"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tenant=algolia"
    status = LearningApplyArtifactStore(package_root).status("algolia", tenant_id=1)
    assert status.approved_policy_count == 1


def test_json_api_returns_latest_argus_run_status() -> None:
    client = _client()

    response = client.get("/api/tenants/algolia/argus/run-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_slug"] == "algolia"
    assert payload["report_id"] == 42
    assert payload["product_market_status"] == "ran"
    assert payload["demand_plane_status"] == "missing"
    assert payload["looker_normalized_row_count"] == 0
    assert payload["product_surface_plan_summary"]["learning_prioritized_count"] == 1
    assert payload["product_surface_plan_summary"]["prioritized_targets"][0]["company_name"] == "Coveo"
    assert payload["runner_summary"]["learning_instruction_improvement_ids"] == [202]
    assert payload["ledger_refresh_status"] == "ran"
    assert payload["ledger_refresh_summary"]["learning_instruction_improvement_ids"] == [202]
    assert payload["ledger_refresh_summary"]["intelligence_brief"]["top_insight"].startswith("Ledger replay")
    assert payload["latest_intelligence_brief"]["top_insight"].startswith("Durable run intelligence")
    assert payload["run_intelligence_history"][0]["run_intelligence_id"] == 88
    assert payload["run_intelligence_history"][0]["top_insight"].startswith("Durable run intelligence")


def test_json_api_returns_argus_feature_matrix() -> None:
    client = _client()

    response = client.get("/api/tenants/algolia/argus/feature-matrix")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["capability_text"] == "agentic product discovery"
    assert payload[0]["company_name"] == "Constructor"
    assert payload[0]["position_status"] == "proven"
    assert payload[0]["evidence_refs"][0]["source_url"] == "https://constructor.com/changelog"
    assert payload[1]["company_role"] == "own"


def test_json_api_returns_feature_comparison_matrix_with_unknown_cells() -> None:
    repo = FakeAdminRepository()
    repo.competitors.append(
        {
            "competitor_id": 2,
            "competitor_name": "Bloomreach",
            "domain": "bloomreach.com",
            "category": "commerce search",
            "priority": 2,
            "status": "active",
            "sources": [],
            "product_surfaces": [],
        }
    )
    client = _client(repo)

    response = client.get("/api/tenants/algolia/argus/feature-comparison")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_slug"] == "algolia"
    assert [company["company_name"] for company in payload["companies"]] == [
        "Algolia",
        "Constructor",
        "Bloomreach",
    ]
    row = payload["rows"][0]
    assert row["capability_text"] == "agentic product discovery"
    cells = {cell["company_name"]: cell for cell in row["cells"]}
    assert cells["Constructor"]["position_status"] == "proven"
    assert cells["Constructor"]["evidence_count"] == 1
    assert cells["Algolia"]["position_status"] == "gap"
    assert cells["Bloomreach"]["position_status"] == "unknown"
    assert cells["Bloomreach"]["evidence_count"] == 0
    assert "No product proof captured" in cells["Bloomreach"]["summary"]
    assert row["unknown_count"] == 1


def test_json_api_feature_comparison_includes_argus_planned_capabilities_as_unknowns() -> None:
    repo = FakeAdminRepository()
    repo.feature_matrix_rows = []
    manifest = _manifest_store_with_demand_plan()
    client = _client(repo, data_plane_manifest_store=manifest)

    response = client.get("/api/tenants/algolia/argus/feature-comparison")

    assert response.status_code == 200
    assert manifest.calls == ["algolia"]
    payload = response.json()
    assert [company["company_name"] for company in payload["companies"]] == ["Algolia", "Constructor"]
    rows = {row["capability_text"]: row for row in payload["rows"]}
    assert set(rows) == {"AI Shopping Agent", "Context engineering"}
    shopping_cells = {cell["company_name"]: cell for cell in rows["AI Shopping Agent"]["cells"]}
    assert shopping_cells["Algolia"]["position_status"] == "unknown"
    assert shopping_cells["Constructor"]["position_status"] == "unknown"
    assert "No product proof captured for Algolia on AI Shopping Agent" in shopping_cells["Algolia"]["summary"]
    assert rows["AI Shopping Agent"]["unknown_count"] == 2
    assert rows["AI Shopping Agent"]["evidence_count"] == 0


def test_json_api_returns_argus_recommendations_for_action_workbench() -> None:
    client = _client()

    response = client.get("/api/tenants/algolia/argus/recommendations")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["recommendation_id"] == 7
    assert payload[0]["owner"] == "PMM"
    assert payload[0]["action"].startswith("Create an evidence-backed")
    assert payload[0]["scorecard"]["total_score"] == 78
    assert payload[0]["evidence_refs"][0]["source_url"] == "https://constructor.com/changelog"


def test_json_api_returns_argus_evidence_ledger() -> None:
    client = _client()

    response = client.get("/api/tenants/algolia/argus/evidence-ledger")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_slug"] == "algolia"
    assert payload["product_events"][0]["company_name"] == "Constructor"
    assert payload["product_events"][0]["capability_text"] == "AI shopping agents"
    assert payload["conversation_themes"][0]["theme"] == "AI shopping agents"
    assert payload["demand_signals"][0]["source_label"] == "Looker Studio GA4 export"
    assert payload["demand_signals"][0]["metadata"]["argus_capability_key"] == "ai shopping agents"
    assert payload["patterns"][0]["pattern_type"] == "own_narrative_gap"


def test_json_api_updates_argus_recommendation_status() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    response = client.post(
        "/api/tenants/algolia/argus/recommendations/7/status",
        json={"status": "accepted"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert repo.updated_recommendation == (7, "accepted")


def test_admin_page_renders_argus_action_workbench() -> None:
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus action workbench" in response.text
    assert "Create an evidence-backed AI shopping agent narrative for Algolia." in response.text
    assert "Product proof, conversation, and demand align." in response.text
    assert "78" in response.text
    assert "https://constructor.com/changelog" in response.text
    assert 'action="/admin/algolia/argus/recommendations/7/status"' in response.text
    assert 'action="/admin/algolia/argus/recommendations/7/challenge"' in response.text


def test_admin_page_renders_argus_evidence_ledger() -> None:
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus evidence ledger" in response.text
    assert "Product proof" in response.text
    assert "Market conversation" in response.text
    assert "Audience demand" in response.text
    assert "Pattern memory" in response.text
    assert "Constructor published product proof for AI shopping agents." in response.text
    assert "Constructor is positioning AI shopping agents as category infrastructure." in response.text
    assert "Looker Studio GA4 export" in response.text
    assert "own_narrative_gap" in response.text


def test_admin_page_renders_argus_run_intelligence_history() -> None:
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Argus run reads" in response.text
    assert "Durable run intelligence says coverage gate held the action." in response.text
    assert "Ledger replay" in response.text
    assert "Ledger replay says coverage gate held the action." in response.text
    assert "2 product · 1 conversation · 1 demand" in response.text


def test_admin_page_renders_latest_ledger_replay_brain_trace() -> None:
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Latest ledger replay read" in response.text
    assert "Ledger replay says coverage gate held the action." in response.text
    assert "Re-audit Coveo before promoting Constructor." in response.text
    assert "1 rising demand topic matched product proof." in response.text
    assert "2 product events and 1 demand signal became 1 pattern." in response.text
    assert "Coveo source coverage degraded." in response.text
    assert "2 product · 1 conversation · 1 demand · 1 pattern · 0 recommendations" in response.text


def test_admin_page_renders_feature_matrix_muscle_readout() -> None:
    client = _client()

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Product muscle matrix" in response.text
    assert "agentic product discovery" in response.text
    assert "Constructor has product proof for AI shopping agents." in response.text
    assert "https://constructor.com/changelog" in response.text


def test_admin_page_renders_feature_comparison_unknowns() -> None:
    repo = FakeAdminRepository()
    repo.competitors.append(
        {
            "competitor_id": 2,
            "competitor_name": "Bloomreach",
            "domain": "bloomreach.com",
            "category": "commerce search",
            "priority": 2,
            "status": "active",
            "sources": [],
            "product_surfaces": [],
        }
    )
    client = _client(repo)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Product feature comparison" in response.text
    assert "Bloomreach" in response.text
    assert "unknown" in response.text
    assert "No product proof captured for Bloomreach" in response.text


def test_admin_page_renders_argus_planned_capabilities_in_feature_comparison() -> None:
    repo = FakeAdminRepository()
    repo.feature_matrix_rows = []
    manifest = _manifest_store_with_demand_plan()
    client = _client(repo, data_plane_manifest_store=manifest)

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 200
    assert "Product feature comparison" in response.text
    assert "AI Shopping Agent" in response.text
    assert "Context engineering" in response.text
    assert "No product proof captured for Algolia on AI Shopping Agent" in response.text
    assert "No product proof captured for Constructor on Context engineering" in response.text


def test_html_forms_add_source_and_pause_competitor() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    added = client.post(
        "/admin/algolia/sources",
        data={
            "competitor_id": "1",
            "source_family": "news",
            "url": "https://constructor.com/news",
            "status": "active",
        },
        follow_redirects=False,
    )
    paused = client.post(
        "/admin/algolia/competitors/1/status",
        data={"status": "paused"},
        follow_redirects=False,
    )
    retired_source = client.post(
        "/admin/algolia/sources/10/status",
        data={"status": "retired"},
        follow_redirects=False,
    )
    added_surface = client.post(
        "/admin/algolia/product-surfaces",
        data={
            "competitor_id": "1",
            "surface_family": "docs",
            "url": "https://docs.constructor.com/",
            "status": "active",
        },
        follow_redirects=False,
    )
    paused_surface = client.post(
        "/admin/algolia/product-surfaces/30/status",
        data={"status": "paused"},
        follow_redirects=False,
    )
    approved_improvement = client.post(
        "/admin/algolia/argus/improvements/202/status",
        data={"status": "approved"},
        follow_redirects=False,
    )
    accepted_recommendation = client.post(
        "/admin/algolia/argus/recommendations/7/status",
        data={"status": "accepted"},
        follow_redirects=False,
    )

    assert added.status_code == 303
    assert paused.status_code == 303
    assert retired_source.status_code == 303
    assert added_surface.status_code == 303
    assert paused_surface.status_code == 303
    assert approved_improvement.status_code == 303
    assert accepted_recommendation.status_code == 303
    assert repo.created_source is not None
    assert repo.created_source[1].source_family == "news"
    assert repo.updated_competitor is not None
    assert repo.updated_competitor[1].status == "paused"
    assert repo.updated_source is not None
    assert repo.updated_source[1].status == "retired"
    assert repo.created_product_surface is not None
    assert repo.created_product_surface[1].surface_family == "docs"
    assert repo.updated_product_surface is not None
    assert repo.updated_product_surface[1].status == "paused"
    assert repo.updated_improvement is not None
    assert repo.updated_improvement[1].status == "approved"
    assert repo.updated_recommendation == (7, "accepted")


def test_html_forms_edit_competitor_source_and_product_surface() -> None:
    repo = FakeAdminRepository()
    client = _client(repo)

    edited_competitor = client.post(
        "/admin/algolia/competitors/1",
        data={
            "name": "Constructor.io",
            "domain": "constructor.com",
            "category": "search/discovery",
            "priority": "2",
            "status": "active",
        },
        follow_redirects=False,
    )
    edited_source = client.post(
        "/admin/algolia/sources/10",
        data={
            "source_family": "changelog",
            "url": "https://constructor.com/changelog",
            "title": "Constructor changelog",
            "status": "active",
        },
        follow_redirects=False,
    )
    edited_surface = client.post(
        "/admin/algolia/product-surfaces/30",
        data={
            "surface_family": "release_notes",
            "url": "https://docs.constructor.com/releases",
            "status": "active",
        },
        follow_redirects=False,
    )

    assert edited_competitor.status_code == 303
    assert edited_source.status_code == 303
    assert edited_surface.status_code == 303
    assert edited_competitor.headers["location"] == "/admin?tenant=algolia"
    assert repo.updated_competitor is not None
    assert repo.updated_competitor[0] == 1
    assert repo.updated_competitor[1].name == "Constructor.io"
    assert repo.updated_competitor[1].domain == "constructor.com"
    assert repo.updated_competitor[1].category == "search/discovery"
    assert repo.updated_competitor[1].priority == 2
    assert repo.updated_competitor[1].status == "active"
    assert repo.updated_source is not None
    assert repo.updated_source[0] == 10
    assert repo.updated_source[1].source_family == "changelog"
    assert str(repo.updated_source[1].url) == "https://constructor.com/changelog"
    assert repo.updated_source[1].title == "Constructor changelog"
    assert repo.updated_source[1].status == "active"
    assert repo.updated_product_surface is not None
    assert repo.updated_product_surface[0] == 30
    assert repo.updated_product_surface[1].surface_family == "release_notes"
    assert str(repo.updated_product_surface[1].url) == "https://docs.constructor.com/releases"
    assert repo.updated_product_surface[1].status == "active"


def test_write_routes_require_admin_token_when_configured() -> None:
    client = _client(token="secret")

    denied = client.post("/api/tenants/algolia/competitors", json={"name": "Coveo"})
    allowed = client.post(
        "/api/tenants/algolia/competitors",
        json={"name": "Coveo"},
        headers={"x-cios-admin-token": "secret"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_local_only_guard_blocks_unapproved_hosts() -> None:
    client = _client(allowed_hosts={"127.0.0.1"})

    response = client.get("/admin?tenant=algolia")

    assert response.status_code == 403
