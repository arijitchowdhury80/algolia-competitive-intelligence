"""Smoke tests for scripts/daily_production_run.py. No network, no live DB."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timezone
from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml

from cios.brain.brief import compose_daily_brief
from cios.brain.types import Signal, SynthesisResult, Verdict
from cios.collect.types import ContentFetchResult, Delta, FetchStatus
from cios.prescribe.types import Effort, Grounding, Prescription, Team, UrgencyWindow

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "daily_production_run.py"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "tenants-sources.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("daily_production_run", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def daily_run():
    return _load_module()


def test_config_loads_expected_shape():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # own_brand is a separate section (src/cios/ownbrand) keyed by tenant,
    # not one of daily_production_run's competitor source lists.
    tenant_plans = {k: v for k, v in data.items() if k not in {"own_brand", "product_surfaces"}}

    assert set(tenant_plans.keys()) == {"algolia", "spryker", "amplitude"}
    for slug, sources in tenant_plans.items():
        # This YAML is only a seed/default config. Runtime source selection
        # must come from the DB competitor/source registry, so this smoke test
        # must not accidentally bless the old "small YAML plan is the whole
        # universe" behavior.
        assert sources
        for source in sources:
            assert set(source.keys()) == {"name", "domain", "url", "family"}

    assert set(data["own_brand"].keys()) == {"algolia", "spryker", "amplitude"}
    assert "algolia" in data["product_surfaces"]


def test_runtime_source_plan_uses_all_active_db_sources_not_yaml_cap(daily_run):
    seed_plan = [
        {"name": "Elastic", "domain": "elastic.co", "url": "https://www.elastic.co/blog", "family": "blog"},
        {"name": "Constructor", "domain": "constructor.com", "url": "https://www.constructor.com/blog", "family": "blog"},
    ]
    db_rows = [
        {
            "competitor_id": idx,
            "competitor_name": name,
            "domain": f"{name.lower()}.example",
            "priority": 2,
            "source_id": 100 + idx,
            "source_family": "blog",
            "url": f"https://{name.lower()}.example/blog",
            "normalized_url": f"https://{name.lower()}.example/blog",
        }
        for idx, name in enumerate(
            ["Elastic", "Constructor", "Coveo", "Bloomreach", "Klevu", "Searchspring", "Yext"],
            start=1,
        )
    ]

    runtime_plan = daily_run.build_runtime_source_plan_from_rows(seed_plan, db_rows)

    assert [item["name"] for item in runtime_plan] == [
        "Elastic",
        "Constructor",
        "Coveo",
        "Bloomreach",
        "Klevu",
        "Searchspring",
        "Yext",
    ]
    assert len(runtime_plan) == 7
    assert {item["source_id"] for item in runtime_plan} == {101, 102, 103, 104, 105, 106, 107}


def test_waf_challenge_fetch_result_is_source_blocking(daily_run):
    blocked = ContentFetchResult(
        status=FetchStatus.ERROR,
        http_status=202,
        text="",
        error="blocked_by_waf:aws_waf_challenge",
    )
    empty = ContentFetchResult(
        status=FetchStatus.ERROR,
        http_status=202,
        text="",
        error="empty",
    )

    assert daily_run.source_block_reason_for_fetch_error(blocked) == "blocked_by_waf:aws_waf_challenge"
    assert daily_run.source_block_reason_for_fetch_error(empty) is None


def test_block_source_after_fetch_challenge_marks_source_blocked(daily_run, monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self, **_kwargs):
            return self.cursor_obj

    conn = FakeConn()
    monkeypatch.setattr(daily_run, "tenant_context", lambda _conn, _tenant_id: nullcontext())

    daily_run.block_source_after_fetch_challenge(
        conn,
        tenant_id=1,
        source_id=4,
        detail="blocked_by_waf:aws_waf_challenge",
        http_status=202,
    )

    assert "UPDATE sources" in conn.cursor_obj.sql
    assert "status = 'blocked'" in conn.cursor_obj.sql
    assert "evidence = sources.evidence || %(evidence)s::jsonb" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["source_id"] == 4
    assert conn.cursor_obj.params["evidence"].obj == {
        "blocked_reason": "blocked_by_waf:aws_waf_challenge",
        "blocked_http_status": 202,
        "blocked_by": "cios.daily.source_sweep",
    }


def test_product_surface_seed_plan_maps_config_to_targets(daily_run):
    config = {
        "algolia": [
            {
                "name": "Constructor",
                "role": "competitor",
                "family": "changelog",
                "url": "https://constructor.com/changelog",
            },
            {
                "name": "Algolia",
                "role": "own",
                "family": "docs",
                "url": "https://www.algolia.com/doc/",
            },
        ]
    }
    comp_ids = {"Constructor": 20}

    targets = daily_run.product_surface_targets_from_seed_plan(
        tenant_id=1,
        tenant_slug="algolia",
        seed_plan=config,
        comp_ids=comp_ids,
    )

    assert len(targets) == 2
    assert targets[0].company_id == 20
    assert targets[0].company_name == "Constructor"
    assert targets[0].company_role == "competitor"
    assert targets[0].surface_family == "changelog"
    assert targets[1].company_id == 0
    assert targets[1].company_name == "Algolia"
    assert targets[1].company_role == "own"


def test_product_surface_seed_plan_skips_unknown_competitor(daily_run):
    config = {
        "algolia": [
            {
                "name": "Unknown Competitor",
                "family": "docs",
                "url": "https://unknown.example/docs",
            }
        ]
    }

    targets = daily_run.product_surface_targets_from_seed_plan(
        tenant_id=1,
        tenant_slug="algolia",
        seed_plan=config,
        comp_ids={"Constructor": 20},
    )

    assert targets == []


def test_seed_product_surfaces_from_plan_upserts_each_target(daily_run, monkeypatch):
    saved = []

    class FakeRepo:
        def __init__(self, _conn):
            pass

        def upsert_seed_target(self, target):
            saved.append(target)
            return len(saved)

    monkeypatch.setattr(daily_run, "PgProductSurfaceRepository", FakeRepo)

    count = daily_run.seed_product_surfaces_from_plan(
        conn=object(),
        tenant_id=1,
        tenant_slug="algolia",
        product_surface_plan={
            "algolia": [
                {
                    "name": "Constructor",
                    "family": "changelog",
                    "url": "https://constructor.com/changelog",
                }
            ]
        },
        comp_ids={"Constructor": 20},
    )

    assert count == 1
    assert saved[0].company_name == "Constructor"
    assert saved[0].surface_family == "changelog"


def test_seed_product_surfaces_from_active_sources_promotes_product_like_families(daily_run, monkeypatch):
    saved = []

    class FakeRepo:
        def __init__(self, _conn):
            pass

        def upsert_seed_target(self, target):
            saved.append(target)
            return len(saved)

    monkeypatch.setattr(daily_run, "PgProductSurfaceRepository", FakeRepo)

    count = daily_run.seed_product_surfaces_from_active_sources(
        conn=object(),
        tenant_id=1,
        runtime_source_plan=[
            {
                "competitor_id": 20,
                "name": "Constructor",
                "family": "blog",
                "url": "https://constructor.com/blog",
            },
            {
                "competitor_id": 20,
                "name": "Constructor",
                "family": "product",
                "url": "https://constructor.com/product",
            },
            {
                "competitor_id": 21,
                "name": "Elastic",
                "family": "changelog",
                "url": "https://www.elastic.co/docs/release-notes/elasticsearch",
            },
            {
                "competitor_id": 22,
                "name": "Algolia",
                "family": "docs",
                "url": "https://www.algolia.com/doc/guides/model-context-protocol",
            },
            {
                "competitor_id": 23,
                "name": "OpenAI / ChatGPT",
                "family": "rss",
                "url": "https://openai.com/news/rss.xml",
            },
        ],
        own_company_name="Algolia",
    )

    assert count == 3
    assert [(target.company_name, target.company_role, target.surface_family) for target in saved] == [
        ("Constructor", "competitor", "product_page"),
        ("Elastic", "competitor", "changelog"),
        ("Algolia", "own", "docs"),
    ]
    assert saved[2].company_id == 0


def test_competitor_name_lookup_uses_runtime_plan_for_db_only_competitors(daily_run):
    runtime_plan = [
        {"competitor_id": 9, "name": "Bloomreach"},
        {"competitor_id": 10, "name": "Yext"},
    ]
    seed_ids = {"Elastic": 1}

    names = daily_run.competitor_names_from_runtime_plan(runtime_plan, seed_ids)

    assert names[1] == "Elastic"
    assert names[9] == "Bloomreach"
    assert names[10] == "Yext"


def test_active_competitor_ids_from_rows_extends_yaml_seed_ids(daily_run):
    seed_ids = {"Elastic": 1}
    rows = [
        {"competitor_id": 9, "competitor_name": "Bloomreach"},
        {"competitor_id": 10, "competitor_name": "Yext"},
    ]

    ids = daily_run.active_competitor_ids_from_rows(seed_ids, rows)

    assert ids == {"Elastic": 1, "Bloomreach": 9, "Yext": 10}


def test_select_tenants_defaults_to_delivered_tenant_only(daily_run):
    tenants = {"algolia": 1, "spryker": 2, "amplitude": 3}

    selected = daily_run.select_tenants_for_run(tenants, deliver_tenant="algolia", run_all=False)

    assert selected == {"algolia": 1}


def test_select_tenants_can_run_all_when_explicit(daily_run):
    tenants = {"algolia": 1, "spryker": 2, "amplitude": 3}

    selected = daily_run.select_tenants_for_run(tenants, deliver_tenant="algolia", run_all=True)

    assert selected == tenants


def test_fetch_settings_are_bounded_by_default(daily_run):
    timeout, retries = daily_run.fetch_settings({})

    assert timeout == 8.0
    assert retries == 0


def test_model_call_settings_are_cron_bounded_by_default(daily_run):
    timeout, attempts = daily_run.model_call_settings({})

    assert timeout == 45.0
    assert attempts == 1


def test_product_surface_timeout_settings_reject_tight_stage_cleanup_margin(daily_run):
    with pytest.raises(ValueError, match="at least 30 seconds longer"):
        daily_run.product_surface_timeout_settings(
            {
                "CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS": "600",
                "CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS": "600.1",
            }
        )


def test_product_surface_timeout_settings_reject_worker_count_above_hard_cap(daily_run):
    with pytest.raises(ValueError, match="between 1 and 8"):
        daily_run.product_surface_timeout_settings(
            {"CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS": "9"}
        )


def test_quality_timeout_defaults_separately_from_synthesis_timeout(daily_run):
    assert daily_run.quality_timeout_seconds({}) == 75.0
    assert daily_run.quality_timeout_seconds({"CIOS_MODEL_TIMEOUT_SECONDS": "150"}) == 150.0
    assert daily_run.quality_timeout_seconds({
        "CIOS_MODEL_TIMEOUT_SECONDS": "150",
        "CIOS_QUALITY_TIMEOUT_SECONDS": "70",
    }) == 70.0


def test_failed_quality_revision_can_replace_rejected_signals_with_empty_set(daily_run):
    should_apply = daily_run.should_apply_quality_revision_result(
        original_quality_status="failed",
        original_promoted_count=2,
        revised_promoted_count=0,
        synthesis_target_count=4,
    )

    assert should_apply is True


def test_failed_quality_revision_does_not_apply_when_no_revision_target_succeeded(daily_run):
    should_apply = daily_run.should_apply_quality_revision_result(
        original_quality_status="failed",
        original_promoted_count=2,
        revised_promoted_count=0,
        synthesis_target_count=4,
        revision_success_count=0,
    )

    assert should_apply is False


def test_revised_signals_are_dropped_when_second_quality_review_still_fails(daily_run):
    assert daily_run.should_drop_revised_signals_after_failed_quality(
        original_quality_status="failed",
        revised_quality_status="failed",
        revised_promoted_count=1,
    ) is True


def test_revised_signals_are_not_dropped_after_passing_quality_review(daily_run):
    assert daily_run.should_drop_revised_signals_after_failed_quality(
        original_quality_status="failed",
        revised_quality_status="passed",
        revised_promoted_count=1,
    ) is False


def test_quality_revision_keeps_successful_targets_when_one_target_times_out(daily_run):
    class FakeRevisionSynthesizer:
        async def synthesize(self, inp):
            if inp.competitor_name == "Coveo":
                raise TimeoutError("revision timed out")
            return SynthesisResult(
                tenant_id=inp.tenant_id,
                competitor_id=inp.competitor_id,
                verdict=Verdict.SIGNALS,
                signals=[
                    Signal(
                        competitor_id=inp.competitor_id,
                        signal_type="product narrative",
                        headline="Constructor keeps the supported signal",
                        what_changed="Constructor positions an AI Shopping Agent with evidence.",
                        recommended_action="Watch the narrative.",
                        owner="PMM",
                        team_to_involve="Marketing",
                        materiality_score=0.72,
                        confidence=0.8,
                        evidence_urls=["https://constructor.com/blog/ai-shopping-agent"],
                    )
                ],
            )

    result = asyncio.run(
        daily_run.synthesize_quality_revision_targets(
            synthesizer=FakeRevisionSynthesizer(),
            synth_targets=[
                (
                    11,
                    "Coveo",
                    [
                        Delta(
                            competitor_id=11,
                            delta_type="product",
                            materiality_score=0.7,
                            what_changed="Coveo source timed out during revision.",
                            evidence_urls=["https://www.coveo.com/en/platform"],
                        )
                    ],
                    [],
                ),
                (
                    12,
                    "Constructor",
                    [
                        Delta(
                            competitor_id=12,
                            delta_type="product",
                            materiality_score=0.72,
                            what_changed="Constructor positions an AI Shopping Agent.",
                            evidence_urls=["https://constructor.com/blog/ai-shopping-agent"],
                        )
                    ],
                    [],
                ),
            ],
            tenant_id=1,
            tenant_company_name="Algolia",
            own_position_facts=[],
            coverage=daily_run.CoverageReport(lanes=[daily_run.LaneStatus(lane="web", ran=True)]),
            fixes_text="Remove unsupported claims.",
        )
    )

    assert result["target_success_count"] == 1
    assert len(result["signals"]) == 1
    assert result["signals"][0]["competitor_name"] == "Constructor"
    assert result["signals"][0]["urls_ok"] is True
    assert result["errors"] == [
        "quality revise target failed: competitor=Coveo error=TimeoutError: revision timed out"
    ]


def test_passed_quality_revision_does_not_replace_promoted_signals(daily_run):
    should_apply = daily_run.should_apply_quality_revision_result(
        original_quality_status="passed",
        original_promoted_count=2,
        revised_promoted_count=0,
        synthesis_target_count=4,
    )

    assert should_apply is False


def test_daily_runner_quality_review_finalizes_before_semantic_delta_persistence():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    first_quality_review = source.index("qr = quality_reviewer.review", run_tenant_start)
    final_quality_status = source.index("res.quality_status = qr.status.value", run_tenant_start)
    published_delta_persistence = source.index("published_ids: list[int] = []", run_tenant_start)

    assert first_quality_review < published_delta_persistence
    assert final_quality_status < published_delta_persistence


def test_synthesis_settings_are_prompt_bounded_by_default(daily_run):
    competitors, deltas, facts = daily_run.synthesis_settings({})

    assert competitors == 4
    assert deltas == 8
    assert facts == 12


def test_article_fetch_cap_is_one_by_default_and_overridable(daily_run):
    assert daily_run.article_fetch_cap({}) == 1
    assert daily_run.article_fetch_cap({"CIOS_ARTICLE_FETCH_CAP": "0"}) == 0
    assert daily_run.article_fetch_cap({"CIOS_ARTICLE_FETCH_CAP": "3"}) == 3


def test_env_flag_defaults_and_parses_truthy_values(daily_run):
    assert daily_run.env_flag({}, "CIOS_ENABLE_PRESCRIPTIONS") is False
    assert daily_run.env_flag({}, "CIOS_ENABLE_PRESCRIPTIONS", default=True) is True
    assert daily_run.env_flag({"CIOS_ENABLE_PRESCRIPTIONS": "yes"}, "CIOS_ENABLE_PRESCRIPTIONS") is True
    assert daily_run.env_flag({"CIOS_ENABLE_PRESCRIPTIONS": "0"}, "CIOS_ENABLE_PRESCRIPTIONS") is False


def test_synthesis_mode_defaults_to_snapshot_current_state_guard(daily_run):
    note = daily_run.synthesis_mode_instructions({}, cold_start=False)

    assert "SNAPSHOT MODE" in note
    assert "current extracted observations" in note
    assert "not proven before/after changes" in note
    assert "return an empty signals array" in note


def test_synthesis_mode_includes_baseline_guard_when_cold_start(daily_run):
    note = daily_run.synthesis_mode_instructions({}, cold_start=True)

    assert "SNAPSHOT MODE" in note
    assert "BASELINE MODE" in note
    assert "cannot claim anything changed in the last 24 hours" in note


def test_model_aliases_default_to_sonnet(daily_run):
    assert daily_run.model_alias({}, "CIOS_MODEL_ALIAS") == "sonnet"
    assert daily_run.model_alias({}, "CIOS_QUALITY_MODEL_ALIAS") == "sonnet"


def test_product_market_chain_skips_when_disabled(daily_run, tmp_path):
    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={"CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path)},
    )

    assert result["status"] == "skipped_disabled"


def test_product_market_chain_blocks_empty_product_surface_outputs_before_synthesis(
    daily_run,
    tmp_path,
    monkeypatch,
):
    calls = []
    empty_surface = tmp_path / "surface-exports" / "000012-coveo-docs.json"

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        calls.append(cmd)
        script_name = Path(cmd[1]).name
        if script_name == "build_next_sweep_learning_plan.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"tenant_id": 1, "instructions": [], "skipped": []}), encoding="utf-8")
        elif script_name == "build_learning_apply_plan.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.write_text(json.dumps({"tenant_id": 1, "actions": [], "skipped": []}), encoding="utf-8")
        elif script_name == "execute_learning_apply_plan.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.write_text(
                json.dumps({"tenant_id": 1, "applied_count": 0, "proposal_count": 0, "skipped": []}),
                encoding="utf-8",
            )
        elif script_name == "plan_product_surface_exports.py":
            output = Path(cmd[cmd.index("--plan-output") + 1])
            output.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "target_count": 1,
                        "items": [
                            {
                                "target": {
                                    "company_name": "Coveo",
                                    "surface_family": "docs",
                                    "url": "https://www.coveo.com/en/docs",
                                },
                                "output_path": str(empty_surface),
                                "learning_priority": 0,
                                "learning_reasons": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "execute_product_surface_plan.py":
            empty_surface.parent.mkdir(parents=True, exist_ok=True)
            empty_surface.write_text("[]", encoding="utf-8")
            output = Path(cmd[cmd.index("--summary-output") + 1])
            output.write_text(
                json.dumps(
                    {
                        "planned": 1,
                        "succeeded": 0,
                        "empty": 1,
                        "failed": 0,
                        "product_plane_status": "empty",
                        "product_row_count": 0,
                        "scout_paths": [],
                        "empty_scout_paths": [str(empty_surface)],
                        "empty_outputs": [
                            {
                                "output_path": str(empty_surface),
                                "company_name": "Coveo",
                                "surface_family": "docs",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        else:
            raise AssertionError(f"{script_name} should not run after empty product surface outputs")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
            "CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME": "Algolia",
        },
    )

    assert result["status"] == "skipped_no_product_surface_outputs"
    assert result["scout_paths"] == []
    assert result["product_surface_execution_summary"]["product_plane_status"] == "empty"
    assert result["product_surface_execution_summary"]["product_row_count"] == 0
    assert result["product_surface_execution_summary"]["empty_scout_paths"] == [str(empty_surface)]
    assert [Path(call[1]).name for call in calls] == [
        "build_next_sweep_learning_plan.py",
        "build_learning_apply_plan.py",
        "execute_learning_apply_plan.py",
        "plan_product_surface_exports.py",
        "execute_product_surface_plan.py",
    ]


def test_product_surface_plan_summary_extracts_learning_prioritized_targets(daily_run, tmp_path):
    plan_path = tmp_path / "product-surface-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "target_count": 3,
                "items": [
                    {
                        "target": {
                            "company_name": "Coveo",
                            "surface_family": "docs",
                            "url": "https://www.coveo.com/en/docs",
                        },
                        "learning_priority": 100,
                        "learning_reasons": [
                            "coverage_recheck: Re-audit Coveo source coverage before ranking Constructor again."
                        ],
                    },
                    {
                        "target": {
                            "company_name": "Constructor",
                            "surface_family": "changelog",
                            "url": "https://constructor.com/changelog",
                        },
                        "learning_priority": 0,
                        "learning_reasons": [],
                    },
                    {
                        "target": {
                            "company_name": "Elastic",
                            "surface_family": "product_page",
                            "url": "https://www.elastic.co/enterprise-search",
                        },
                        "learning_priority": 0,
                        "learning_reasons": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = daily_run.summarize_product_surface_plan(plan_path)

    assert summary == {
        "target_count": 3,
        "target_company_count": 3,
        "target_companies": ["Constructor", "Coveo", "Elastic"],
        "surface_family_counts": {"changelog": 1, "docs": 1, "product_page": 1},
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
    }


def test_product_muscle_gap_discovery_plan_uses_evidence_backed_source_urls_for_missing_companies(daily_run):
    plan = daily_run.build_product_muscle_gap_discovery_plan(
        product_surface_plan_summary={
            "target_companies": ["Constructor", "Elastic"],
        },
        monitored_competitors=[
            {
                "competitor_id": 5,
                "competitor_name": "Constructor",
                "domain": "constructor.com",
                "active_source_count": 4,
            },
            {
                "competitor_id": 6,
                "competitor_name": "Elastic",
                "domain": "elastic.co",
                "active_source_count": 3,
            },
            {
                "competitor_id": 7,
                "competitor_name": "Algonomy",
                "domain": "algonomy.com",
                "active_source_count": 1,
                "monitored_sources": [
                    {
                        "source_family": "docs",
                        "url": "https://algonomy.com/docs/commerce-search",
                        "status": "active",
                    },
                    {
                        "source_family": "blog",
                        "url": "https://algonomy.com/blogs",
                        "status": "active",
                    },
                    {
                        "source_family": "pricing",
                        "url": "https://algonomy.com/pricing",
                        "status": "candidate",
                    },
                ],
            },
            {
                "competitor_id": 8,
                "competitor_name": "Perplexity AI",
                "domain": None,
                "active_source_count": 0,
            },
        ],
    )

    assert plan["monitored_company_count"] == 4
    assert plan["covered_company_count"] == 2
    assert plan["missing_company_count"] == 2
    assert [item["company_name"] for item in plan["missing_companies"]] == [
        "Algonomy",
        "Perplexity AI",
    ]
    assert plan["missing_companies"][0]["candidate_surface_urls"] == [
        {
            "surface_family": "docs",
            "url": "https://algonomy.com/docs/commerce-search",
            "evidence_source_family": "docs",
            "evidence_source_status": "active",
        },
    ]
    assert plan["missing_companies"][1]["candidate_surface_urls"] == []
    assert plan["candidate_url_count"] == 1
    assert plan["candidate_surface_family_counts"] == {
        "docs": 1,
    }


def test_product_muscle_gap_discovery_plan_does_not_guess_generic_urls_from_domain_only(daily_run):
    plan = daily_run.build_product_muscle_gap_discovery_plan(
        product_surface_plan_summary={"target_companies": []},
        monitored_competitors=[
            {
                "competitor_id": 7,
                "competitor_name": "Algonomy",
                "domain": "algonomy.com",
                "active_source_count": 1,
            }
        ],
    )

    assert plan["missing_company_count"] == 1
    assert plan["missing_companies"][0]["candidate_surface_urls"] == []
    assert plan["candidate_url_count"] == 0
    assert plan["candidate_surface_family_counts"] == {}
    assert plan["missing_companies"][0]["heuristic_surface_probes"] == [
        {
            "surface_family": "changelog",
            "url": "https://algonomy.com/changelog",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "release_notes",
            "url": "https://algonomy.com/release-notes",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "docs",
            "url": "https://algonomy.com/docs",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "api_docs",
            "url": "https://algonomy.com/developers",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "pricing",
            "url": "https://algonomy.com/pricing",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "integration",
            "url": "https://algonomy.com/integrations",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "product_page",
            "url": "https://algonomy.com/products",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
        {
            "surface_family": "product_page",
            "url": "https://algonomy.com/platform",
            "discovery_reason": "domain_heuristic",
            "requires_validation": True,
        },
    ]
    assert plan["heuristic_probe_count"] == 8
    assert plan["heuristic_surface_family_counts"] == {
        "api_docs": 1,
        "changelog": 1,
        "docs": 1,
        "integration": 1,
        "pricing": 1,
        "product_page": 2,
        "release_notes": 1,
    }


def test_product_muscle_gap_discovery_plan_targets_empty_product_surface_outputs(daily_run):
    plan = daily_run.build_product_muscle_gap_discovery_plan(
        product_surface_plan_summary={"target_companies": ["Klevu"]},
        product_surface_execution_summary={
            "empty_outputs": [
                {
                    "company_name": "Klevu",
                    "surface_family": "docs",
                }
            ]
        },
        monitored_competitors=[
            {
                "competitor_id": 9,
                "competitor_name": "Klevu",
                "domain": "klevu.com",
                "active_source_count": 1,
            }
        ],
    )

    assert plan["covered_company_count"] == 1
    assert plan["missing_company_count"] == 0
    assert plan["empty_surface_target_count"] == 1
    assert plan["empty_surface_targets"] == [
        {
            "competitor_id": 9,
            "company_name": "Klevu",
            "domain": "klevu.com",
            "active_source_count": 1,
            "failed_surface_family": "docs",
            "candidate_surface_urls": [],
            "heuristic_surface_probes": [
                {
                    "surface_family": "changelog",
                    "url": "https://klevu.com/changelog",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "release_notes",
                    "url": "https://klevu.com/release-notes",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "docs",
                    "url": "https://klevu.com/docs",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "api_docs",
                    "url": "https://klevu.com/developers",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "pricing",
                    "url": "https://klevu.com/pricing",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "integration",
                    "url": "https://klevu.com/integrations",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "product_page",
                    "url": "https://klevu.com/products",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
                {
                    "surface_family": "product_page",
                    "url": "https://klevu.com/platform",
                    "discovery_reason": "domain_heuristic",
                    "requires_validation": True,
                },
            ],
        }
    ]
    assert plan["heuristic_probe_count"] == 8


def test_product_muscle_gap_discovery_plan_prioritizes_unknown_feature_cells_from_demand_and_movement(
    daily_run,
):
    plan = daily_run.build_product_muscle_gap_discovery_plan(
        product_surface_plan_summary={
            "target_companies": ["Constructor", "Bloomreach"],
        },
        monitored_competitors=[
            {
                "competitor_id": 5,
                "competitor_name": "Constructor",
                "domain": "constructor.com",
                "active_source_count": 4,
            },
            {
                "competitor_id": 9,
                "competitor_name": "Bloomreach",
                "domain": "bloomreach.com",
                "active_source_count": 4,
                "monitored_sources": [
                    {
                        "source_family": "docs",
                        "url": "https://documentation.bloomreach.com/discovery/",
                        "status": "active",
                    },
                    {
                        "source_family": "product",
                        "url": "https://www.bloomreach.com/en/products/discovery",
                        "status": "active",
                    },
                    {
                        "source_family": "blog",
                        "url": "https://www.bloomreach.com/en/blog",
                        "status": "active",
                    },
                ],
            },
        ],
        feature_matrix_rows=[
            {
                "capability_text": "AI Shopping Agent",
                "company_name": "Constructor",
                "company_role": "competitor",
                "position_status": "proven",
                "evidence_refs": [{"url": "https://constructor.com/changelog/ai-shopping-agent"}],
            }
        ],
        runner_summary={
            "intelligence_brief": {
                "demand_read": {
                    "top_topics": [
                        {
                            "topic": "agentic product discovery",
                            "matched_product_proof": True,
                        }
                    ]
                },
                "movement_map": {
                    "hot_capabilities": ["commerce AI agent"],
                    "heat_cells": [
                        {
                            "company_name": "Constructor",
                            "capability": "AI Shopping Agent",
                            "heat_level": "hot",
                        }
                    ],
                },
            }
        },
    )

    assert plan["missing_company_count"] == 0
    assert plan["candidate_url_count"] == 0
    assert plan["unknown_feature_cell_count"] == 1
    assert plan["prioritized_unknown_cell_count"] == 1
    assert plan["feature_unknown_candidate_url_count"] == 2
    assert plan["feature_unknown_collection_targets"] == [
        {
            "competitor_id": 9,
            "company_name": "Bloomreach",
            "domain": "bloomreach.com",
            "active_source_count": 4,
            "capability_text": "AI Shopping Agent",
            "capability_key": "shopping agent",
            "priority_score": 110,
            "priority_reasons": [
                "rising_demand: agentic product discovery",
                "market_movement: commerce AI agent",
                "captured_product_proof: Constructor",
            ],
            "candidate_surface_urls": [
                {
                    "surface_family": "docs",
                    "url": "https://documentation.bloomreach.com/discovery/",
                    "evidence_source_family": "docs",
                    "evidence_source_status": "active",
                },
                {
                    "surface_family": "product_page",
                    "url": "https://www.bloomreach.com/en/products/discovery",
                    "evidence_source_family": "product",
                    "evidence_source_status": "active",
                },
            ],
        }
    ]


def test_product_muscle_gap_discovery_plan_ignores_feature_proof_from_unmonitored_companies(
    daily_run,
):
    plan = daily_run.build_product_muscle_gap_discovery_plan(
        product_surface_plan_summary={
            "target_companies": ["Constructor", "Bloomreach"],
        },
        monitored_competitors=[
            {
                "competitor_id": 5,
                "competitor_name": "Constructor",
                "domain": "constructor.com",
                "active_source_count": 4,
            },
            {
                "competitor_id": 9,
                "competitor_name": "Bloomreach",
                "domain": "bloomreach.com",
                "active_source_count": 4,
                "monitored_sources": [
                    {
                        "source_family": "docs",
                        "url": "https://documentation.bloomreach.com/discovery/",
                        "status": "active",
                    }
                ],
            },
        ],
        feature_matrix_rows=[
            {
                "capability_text": "AI Shopping Agent",
                "company_name": "Constructor",
                "position_status": "proven",
            },
            {
                "capability_text": "AI Shopping Agent",
                "company_name": "Feature Matrix Test",
                "position_status": "proven",
            },
            {
                "capability_text": "Test-only Capability",
                "company_name": "Feature Matrix Test",
                "position_status": "proven",
            },
        ],
        runner_summary={
            "intelligence_brief": {
                "movement_map": {
                    "hot_capabilities": ["AI Shopping Agent", "Test-only Capability"],
                },
            },
        },
    )

    assert plan["unknown_feature_cell_count"] == 1
    assert plan["prioritized_unknown_cell_count"] == 1
    assert plan["feature_unknown_collection_targets"][0]["priority_reasons"] == [
        "market_movement: AI Shopping Agent",
        "captured_product_proof: Constructor",
    ]
    assert "Feature Matrix Test" not in json.dumps(plan)


def test_discover_product_market_looker_exports_reads_explicit_and_drop_folder(daily_run, tmp_path):
    explicit = tmp_path / "explicit.csv"
    explicit.write_text("topic,metric,value\nexplicit,engaged_sessions,10\n", encoding="utf-8")
    app_dir = tmp_path / "app"
    drop = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    drop.parent.mkdir(parents=True)
    drop.write_text("topic,metric,value\ndrop,engaged_sessions,20\n", encoding="utf-8")
    ignored = app_dir / "data" / "looker" / "algolia" / "notes.txt"
    ignored.write_text("not an export", encoding="utf-8")

    paths = daily_run.discover_product_market_looker_exports(
        slug="algolia",
        env={"CIOS_PRODUCT_MARKET_LOOKER_EXPORTS": str(explicit)},
        app_dir=app_dir,
    )

    assert paths == [explicit, drop]


def test_prepare_product_market_looker_exports_writes_manifest_and_normalized_files(daily_run, tmp_path):
    app_dir = tmp_path / "app"
    drop_dir = app_dir / "data" / "looker" / "algolia"
    good = drop_dir / "ga-pages.csv"
    bad = drop_dir / "bad-pages.csv"
    drop_dir.mkdir(parents=True)
    good.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    bad.write_text(
        "Page title,Page path,Engaged sessions\n"
        "Unknown page,/docs/unknown,17\n",
        encoding="utf-8",
    )

    result = daily_run.prepare_product_market_looker_exports(
        slug="algolia",
        env={},
        work_dir=tmp_path / "work",
        app_dir=app_dir,
    )

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    normalized_path = Path(result["payload_paths"][0])

    assert result["discovered_count"] == 2
    assert result["ready_count"] == 1
    assert result["normalized_row_count"] == 1
    assert result["skipped_row_count"] == 1
    assert normalized_path.name == "ga-pages.normalized.json"
    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    normalized_row = normalized_payload["records"][0]
    assert normalized_payload == {
        "records": [
            {
                "topic": "AI Shopping Agent",
                "metric": "engaged_sessions",
                "value": 240.0,
                "change_pct": 0.5,
                "period_start": "2026-07-01T00:00:00+00:00",
                "period_end": "2026-07-08T00:00:00+00:00",
                "source_label": "Looker Studio GA4 export",
                "source_url": "https://lookerstudio.google.com/reporting/abc",
                "excerpt": "Page title: AI Shopping Agent guide; Page path: /solutions/ai-shopping-agent",
                "source_file": "ga-pages.csv",
                "source_row_number": 1,
                "source_fingerprint": normalized_row["source_fingerprint"],
            }
        ]
    }
    assert len(normalized_row["source_fingerprint"]) == 64
    assert manifest["files"][0]["status"] == "empty"
    assert manifest["files"][0]["skipped_row_count"] == 1
    assert manifest["files"][0]["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "missing_topic",
            "missing_fields": ["topic", "period"],
            "source_file": "bad-pages.csv",
            "available_columns": ["Engaged sessions", "Page path", "Page title"],
        }
    ]
    assert manifest["files"][1]["status"] == "ready"
    assert manifest["files"][1]["normalized_row_count"] == 1


def test_product_market_chain_passes_discovered_looker_drop_folder_exports(daily_run, tmp_path, monkeypatch):
    calls = []
    scout_path = tmp_path / "surface-exports" / "000011-constructor-changelog.json"
    app_dir = tmp_path / "app"
    looker_path = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    looker_path.parent.mkdir(parents=True)
    looker_path.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        calls.append(cmd)
        script_name = Path(cmd[1]).name
        if script_name == "build_next_sweep_learning_plan.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"tenant_id": 1, "instructions": [], "skipped": []}), encoding="utf-8")
        elif script_name == "plan_product_surface_exports.py":
            output = Path(cmd[cmd.index("--plan-output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"tenant_id": 1, "target_count": 1, "items": []}), encoding="utf-8")
        elif script_name == "execute_product_surface_plan.py":
            scout_path.parent.mkdir(parents=True, exist_ok=True)
            scout_path.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")
            output = Path(cmd[cmd.index("--summary-output") + 1])
            output.write_text(json.dumps({"failed": 0, "succeeded": 1, "scout_paths": [str(scout_path)]}), encoding="utf-8")
        elif script_name == "build_product_market_payload.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.write_text(json.dumps({"tenant_id": 1}), encoding="utf-8")
        elif script_name == "run_product_market_intelligence.py":
            return SimpleNamespace(returncode=0, stdout='{"verdict":"quiet"}', stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)
    monkeypatch.setattr(daily_run, "SCRIPT_DIR", app_dir / "scripts")

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
            "CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME": "Algolia",
        },
    )

    payload_call = next(call for call in calls if Path(call[1]).name == "build_product_market_payload.py")
    payload_looker_path = Path(payload_call[payload_call.index("--looker") + 1])
    assert result["looker_export_count"] == 1
    assert result["looker_discovered_count"] == 1
    assert result["looker_ready_count"] == 1
    assert result["looker_normalized_row_count"] == 1
    assert result["looker_raw_paths"] == [str(looker_path)]
    assert result["looker_paths"] == [str(payload_looker_path)]
    assert result["looker_manifest_path"].endswith("looker-export-manifest.json")
    assert payload_looker_path.name == "ga-pages.normalized.json"
    assert not looker_path.exists()
    assert result["looker_archived_count"] == 1
    assert len(list((app_dir / "data" / "looker" / "algolia" / "_archive").glob("*/*.csv"))) == 1


def test_promoted_signals_become_product_market_conversation_records(daily_run):
    captured_at = datetime(2026, 7, 11, 5, 13, tzinfo=timezone.utc)

    records = daily_run.product_market_conversation_records_from_promoted_signals(
        [
            {
                "competitor_id": 42,
                "competitor_name": "Constructor",
                "signal_type": "agentic product discovery",
                "headline": "Constructor pushes AI shopping agent positioning",
                "what_changed": "Constructor is positioning AI shopping agents as the new product discovery layer.",
                "why_it_matters": "This changes the buying narrative for search and discovery teams.",
                "materiality_score": 0.83,
                "confidence": 0.74,
                "evidence_urls": ["https://constructor.com/blog/ai-shopping-agent"],
            },
            {
                "competitor_id": 77,
                "competitor_name": "No Evidence Co",
                "signal_type": "generic",
                "headline": "No evidence should not enter the intelligence spine",
                "what_changed": "This record is intentionally missing evidence.",
                "materiality_score": 0.5,
                "evidence_urls": [],
            },
        ],
        captured_at=captured_at,
    )

    assert records == [
        {
            "company_id": 42,
            "company_name": "Constructor",
            "theme": "agentic product discovery",
            "summary": "Constructor pushes AI shopping agent positioning: Constructor is positioning AI shopping agents as the new product discovery layer.",
            "intensity": 0.83,
            "source_url": "https://constructor.com/blog/ai-shopping-agent",
            "captured_at": "2026-07-11T05:13:00+00:00",
            "excerpt": "Constructor is positioning AI shopping agents as the new product discovery layer.",
            "method": "web_scan",
        }
    ]


def test_current_sweep_deltas_become_product_market_conversation_records(daily_run):
    captured_at = datetime(2026, 7, 11, 5, 13, tzinfo=timezone.utc)

    class Delta:
        def __init__(self, competitor_id, delta_type, what_changed, materiality_score, evidence_urls):
            self.competitor_id = competitor_id
            self.delta_type = delta_type
            self.what_changed = what_changed
            self.materiality_score = materiality_score
            self.evidence_urls = evidence_urls

    records = daily_run.product_market_conversation_records_from_current_sweep(
        promoted_signals=[],
        all_deltas_by_comp={
            20: [
                Delta(
                    20,
                    "commerce AI agent",
                    "Constructor says its shopping agent helps shoppers find products through natural language.",
                    0.71,
                    ["https://constructor.com/blog/ai-shopping-agent"],
                )
            ],
            30: [
                Delta(
                    30,
                    "empty evidence",
                    "This should be rejected because it has no evidence.",
                    0.95,
                    [],
                )
            ],
        },
        comp_names_by_id={20: "Constructor", 30: "Noise Co"},
        captured_at=captured_at,
    )

    assert records == [
        {
            "company_id": 20,
            "company_name": "Constructor",
            "theme": "AI Shopping Agent",
            "summary": "Constructor says its shopping agent helps shoppers find products through natural language.",
            "intensity": 0.71,
            "source_url": "https://constructor.com/blog/ai-shopping-agent",
            "captured_at": "2026-07-11T05:13:00+00:00",
            "excerpt": "Constructor says its shopping agent helps shoppers find products through natural language.",
            "method": "web_scan",
        }
    ]


def test_current_sweep_deltas_infer_capability_theme_from_statement_before_generic_delta_type(daily_run):
    captured_at = datetime(2026, 7, 11, 5, 13, tzinfo=timezone.utc)

    class Delta:
        def __init__(self):
            self.competitor_id = 20
            self.delta_type = "new_customer_proof"
            self.what_changed = "Constructor added customer proof for its AI Shopping Agent commerce workflow."
            self.materiality_score = 0.77
            self.evidence_urls = ["https://constructor.com/customers"]

    records = daily_run.product_market_conversation_records_from_current_sweep(
        promoted_signals=[],
        all_deltas_by_comp={20: [Delta()]},
        comp_names_by_id={20: "Constructor"},
        captured_at=captured_at,
    )

    assert records[0]["theme"] == "AI Shopping Agent"


def test_product_market_chain_runs_plan_execute_payload_and_runner(daily_run, tmp_path, monkeypatch):
    calls = []
    timeouts = {}
    scout_path = tmp_path / "surface-exports" / "000011-constructor-changelog.json"
    looker_path = tmp_path / "looker.csv"
    looker_path.write_text(
        "topic,metric,value,change_pct,period_start,period_end,source_label,source_url\n"
        "agentic product discovery,engaged_sessions,100,0.10,2026-07-01T00:00:00+00:00,2026-07-08T00:00:00+00:00,GA4,looker://algolia/a\n",
        encoding="utf-8",
    )

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, check
        calls.append(cmd)
        script_name = Path(cmd[1]).name
        timeouts[script_name] = timeout
        if script_name == "build_next_sweep_learning_plan.py":
            plan_output = Path(cmd[cmd.index("--output") + 1])
            plan_output.parent.mkdir(parents=True, exist_ok=True)
            plan_output.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "instructions": [
                            {
                                "tenant_id": 1,
                                "kind": "coverage_recheck",
                                "priority": "critical",
                                "summary": "Re-audit Coveo source coverage before ranking Constructor.",
                                "instruction": "Re-audit Coveo source coverage before ranking Constructor.",
                                "status": "ready_for_next_sweep",
                                "change": {"company": "Coveo"},
                                "evidence_event_ids": [101],
                                "source_improvement_ids": [202],
                            }
                        ],
                        "metadata": {
                            "db_instruction_count": 0,
                            "approved_policy_count": 1,
                            "policy_instruction_count": 1,
                            "duplicate_policy_instruction_count": 0,
                            "skipped_policy_instruction_count": 0,
                            "policy_sources": [
                                {
                                    "action_id": "abc123def4567890",
                                    "target": "source_coverage_policy",
                                    "package_path": "config/source-coverage-policy.yaml",
                                    "approved_by": "arijit",
                                    "kind": "coverage_recheck",
                                    "summary": "Re-audit Coveo source coverage before ranking Constructor.",
                                    "status": "loaded",
                                    "evidence_event_ids": [101],
                                    "source_improvement_ids": [202],
                                }
                            ],
                        },
                        "skipped": [],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "build_learning_apply_plan.py":
            apply_output = Path(cmd[cmd.index("--output") + 1])
            apply_output.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "actions": [
                            {
                                "kind": "coverage_recheck",
                                "package_scope": "ci-os",
                                "target": "source_coverage_policy",
                                "package_path": "config/source-coverage-policy.yaml",
                                "requires_human_approval": True,
                                "touches_hermes_core": False,
                                "evidence_event_ids": [101],
                                "source_improvement_ids": [202],
                            }
                        ],
                        "skipped": [],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "execute_learning_apply_plan.py":
            execution_output = Path(cmd[cmd.index("--output") + 1])
            execution_output.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "applied_count": 0,
                        "proposal_count": 1,
                        "applied": [],
                        "proposals": [
                            {
                                "action_id": "abc123def4567890",
                                "target": "source_coverage_policy",
                                "package_path": "config/source-coverage-policy.yaml",
                                "proposal_path": "docs/workspace/cios-learning-apply-plan/proposals/abc123def4567890-source_coverage_policy.json",
                                "status": "pending_human_approval",
                            }
                        ],
                        "skipped": [],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "plan_product_surface_exports.py":
            plan_output = Path(cmd[cmd.index("--plan-output") + 1])
            plan_output.parent.mkdir(parents=True, exist_ok=True)
            plan_output.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "target_count": 2,
                        "items": [
                            {
                                "target": {
                                    "company_name": "Coveo",
                                    "surface_family": "docs",
                                    "url": "https://www.coveo.com/en/docs",
                                },
                                "learning_priority": 100,
                                "learning_reasons": [
                                    "coverage_recheck: Re-audit Coveo source coverage before ranking Constructor again."
                                ],
                            },
                            {
                                "target": {
                                    "company_name": "Constructor",
                                    "surface_family": "changelog",
                                    "url": "https://constructor.com/changelog",
                                },
                                "learning_priority": 0,
                                "learning_reasons": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "execute_product_surface_plan.py":
            scout_path.parent.mkdir(parents=True, exist_ok=True)
            scout_path.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")
            summary_output = Path(cmd[cmd.index("--summary-output") + 1])
            summary_output.write_text(
                json.dumps(
                    {
                        "failed": 3,
                        "succeeded": 1,
                        "timed_out": 1,
                        "not_started": 2,
                        "batch_timed_out": True,
                        "batch_timeout_seconds": 600,
                        "scout_paths": [str(scout_path)],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "build_product_market_payload.py":
            payload_output = Path(cmd[cmd.index("--output") + 1])
            payload_output.write_text(json.dumps({"tenant_id": 1}), encoding="utf-8")
        elif script_name == "run_product_market_intelligence.py":
            return SimpleNamespace(returncode=0, stdout='{"verdict":"quiet"}', stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
            "CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME": "Algolia",
            "CIOS_PRODUCT_MARKET_PROVIDER": "gemini/gemini-2.5-flash",
            "CIOS_PRODUCT_MARKET_USE_JS": "1",
            "CIOS_PRODUCT_MARKET_LOOKER_EXPORTS": str(looker_path),
            "CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS": "4",
            "CIOS_PRODUCT_MARKET_COMMAND_TIMEOUT_SECONDS": "240",
            "CIOS_PRODUCT_MARKET_EXPORT_COMMAND_TIMEOUT_SECONDS": "300",
            "CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS": "600",
            "CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS": "630",
            "CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR": "0.03",
            "CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR": "25",
        },
        conversation_records=[
            {
                "company_id": 11,
                "company_name": "Constructor",
                "theme": "agentic product discovery",
                "summary": "Constructor is talking about agentic product discovery.",
                "intensity": 0.8,
                "source_url": "https://constructor.com/blog/ai-shopping-agent",
                "captured_at": "2026-07-11T05:13:00+00:00",
                "method": "web_scan",
            }
        ],
    )

    assert result["status"] == "ran"
    assert result["scout_paths"] == [str(scout_path)]
    assert result["next_sweep_plan_path"].endswith("next-sweep-learning-plan.json")
    assert result["next_sweep_plan_summary"] == {
        "instruction_count": 1,
        "skipped_count": 0,
        "approved_policy_count": 1,
        "policy_instruction_count": 1,
        "duplicate_policy_instruction_count": 0,
        "skipped_policy_instruction_count": 0,
        "policy_sources": [
            {
                "action_id": "abc123def4567890",
                "target": "source_coverage_policy",
                "package_path": "config/source-coverage-policy.yaml",
                "approved_by": "arijit",
                "kind": "coverage_recheck",
                "summary": "Re-audit Coveo source coverage before ranking Constructor.",
                "status": "loaded",
                "evidence_event_ids": [101],
                "source_improvement_ids": [202],
            }
        ],
    }
    assert result["learning_apply_plan_path"].endswith("learning-apply-plan.json")
    assert result["learning_apply_plan_summary"] == {
        "action_count": 1,
        "skipped_count": 0,
        "targets": ["source_coverage_policy"],
        "package_paths": ["config/source-coverage-policy.yaml"],
    }
    assert result["learning_apply_execution_path"].endswith("learning-apply-execution.json")
    assert result["learning_apply_execution_summary"] == {
        "applied_count": 0,
        "proposal_count": 1,
        "skipped_count": 0,
        "proposal_statuses": ["pending_human_approval"],
        "targets": ["source_coverage_policy"],
    }
    assert result["product_surface_plan_summary"] == {
        "target_count": 2,
        "target_company_count": 2,
        "target_companies": ["Constructor", "Coveo"],
        "surface_family_counts": {"changelog": 1, "docs": 1},
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
    }
    assert result["product_surface_execution_summary"]["timed_out"] == 1
    assert result["product_surface_execution_summary"]["not_started"] == 2
    assert result["product_surface_execution_summary"]["batch_timed_out"] is True
    assert result["product_surface_execution_summary"]["batch_timeout_seconds"] == 600.0
    assert [Path(call[1]).name for call in calls] == [
        "build_next_sweep_learning_plan.py",
        "build_learning_apply_plan.py",
        "execute_learning_apply_plan.py",
        "plan_product_surface_exports.py",
        "execute_product_surface_plan.py",
        "build_product_market_payload.py",
        "run_product_market_intelligence.py",
        "refresh_product_market_from_ledger.py",
    ]
    apply_call = calls[1]
    learning_execute_call = calls[2]
    plan_call = calls[3]
    execute_call = calls[4]
    payload_call = calls[5]
    assert apply_call[apply_call.index("--plan") + 1].endswith("next-sweep-learning-plan.json")
    assert apply_call[apply_call.index("--output") + 1].endswith("learning-apply-plan.json")
    assert learning_execute_call[learning_execute_call.index("--plan") + 1].endswith("learning-apply-plan.json")
    assert learning_execute_call[learning_execute_call.index("--output") + 1].endswith("learning-apply-execution.json")
    assert "--approved-by" not in learning_execute_call
    assert plan_call[plan_call.index("--learning-plan") + 1].endswith("next-sweep-learning-plan.json")
    assert execute_call[execute_call.index("--max-workers") + 1] == "4"
    assert execute_call[execute_call.index("--command-timeout-seconds") + 1] == "300"
    assert execute_call[execute_call.index("--batch-timeout-seconds") + 1] == "600"
    assert timeouts["execute_product_surface_plan.py"] == 630.0
    assert payload_call[payload_call.index("--scout") + 1] == str(scout_path)
    payload_looker_path = Path(payload_call[payload_call.index("--looker") + 1])
    assert payload_looker_path.name == "looker.normalized.json"
    assert payload_looker_path != looker_path
    assert looker_path.exists()
    assert result["looker_export_count"] == 1
    assert result["looker_discovered_count"] == 1
    assert result["looker_ready_count"] == 1
    assert result["looker_archived_count"] == 0
    assert result["looker_raw_paths"] == [str(looker_path)]
    assert result["looker_paths"] == [str(payload_looker_path)]
    assert result["looker_manifest_path"].endswith("looker-export-manifest.json")
    conversation_path = Path(payload_call[payload_call.index("--conversation") + 1])
    assert conversation_path.name == "conversation-records.json"
    assert json.loads(conversation_path.read_text(encoding="utf-8"))["records"][0]["company_name"] == "Constructor"
    assert result["conversation_record_count"] == 1
    assert result["conversation_path"] == str(conversation_path)
    assert payload_call[payload_call.index("--learning-plan") + 1].endswith("next-sweep-learning-plan.json")
    assert payload_call[payload_call.index("--demand-change-floor") + 1] == "0.03"
    assert payload_call[payload_call.index("--demand-value-floor") + 1] == "25"
    refresh_call = calls[7]
    assert refresh_call[refresh_call.index("--demand-change-floor") + 1] == "0.03"
    assert refresh_call[refresh_call.index("--demand-value-floor") + 1] == "25"


def test_product_market_chain_refreshes_ledger_with_learning_plan_after_synthesis(daily_run, tmp_path, monkeypatch):
    calls = []
    scout_path = tmp_path / "surface-exports" / "000011-constructor-changelog.json"

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        calls.append(cmd)
        script_name = Path(cmd[1]).name
        if script_name == "build_next_sweep_learning_plan.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    {
                        "tenant_id": 1,
                        "instructions": [
                            {
                                "kind": "coverage_recheck",
                                "instruction": "Re-audit Coveo before ranking Constructor again.",
                                "source_improvement_ids": [202],
                            }
                        ],
                        "skipped": [],
                    }
                ),
                encoding="utf-8",
            )
        elif script_name == "plan_product_surface_exports.py":
            output = Path(cmd[cmd.index("--plan-output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"tenant_id": 1, "target_count": 1, "items": []}), encoding="utf-8")
        elif script_name == "execute_product_surface_plan.py":
            scout_path.parent.mkdir(parents=True, exist_ok=True)
            scout_path.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")
            output = Path(cmd[cmd.index("--summary-output") + 1])
            output.write_text(json.dumps({"failed": 0, "succeeded": 1, "scout_paths": [str(scout_path)]}), encoding="utf-8")
        elif script_name == "build_product_market_payload.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.write_text(json.dumps({"tenant_id": 1}), encoding="utf-8")
        elif script_name == "run_product_market_intelligence.py":
            return SimpleNamespace(returncode=0, stdout='{"verdict":"actionable"}', stderr="")
        elif script_name == "refresh_product_market_from_ledger.py":
            return SimpleNamespace(
                returncode=0,
                stdout='{"verdict":"watch","learning_instruction_count":1}',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
            "CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME": "Algolia",
        },
    )

    script_names = [Path(call[1]).name for call in calls]
    assert script_names[-2:] == [
        "run_product_market_intelligence.py",
        "refresh_product_market_from_ledger.py",
    ]
    refresh_call = calls[-1]
    assert refresh_call[refresh_call.index("--tenant") + 1] == "algolia"
    assert refresh_call[refresh_call.index("--own-company-name") + 1] == "Algolia"
    assert refresh_call[refresh_call.index("--learning-plan") + 1].endswith("next-sweep-learning-plan.json")
    assert result["ledger_refresh_status"] == "ran"
    assert result["ledger_refresh_summary"] == {"verdict": "watch", "learning_instruction_count": 1}


def test_product_market_chain_can_export_ga4_demand_before_payload_build(daily_run, tmp_path, monkeypatch):
    calls = []
    scout_path = tmp_path / "surface-exports" / "000011-constructor-changelog.json"

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        calls.append(cmd)
        script_name = Path(cmd[1]).name
        if script_name == "build_next_sweep_learning_plan.py":
            plan_output = Path(cmd[cmd.index("--output") + 1])
            plan_output.parent.mkdir(parents=True, exist_ok=True)
            plan_output.write_text(json.dumps({"tenant_id": 1, "instructions": [], "skipped": []}), encoding="utf-8")
        elif script_name == "plan_product_surface_exports.py":
            plan_output = Path(cmd[cmd.index("--plan-output") + 1])
            plan_output.parent.mkdir(parents=True, exist_ok=True)
            plan_output.write_text(json.dumps({"tenant_id": 1, "target_count": 1, "items": []}), encoding="utf-8")
        elif script_name == "execute_product_surface_plan.py":
            scout_path.parent.mkdir(parents=True, exist_ok=True)
            scout_path.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")
            summary_output = Path(cmd[cmd.index("--summary-output") + 1])
            summary_output.write_text(
                json.dumps({"failed": 0, "succeeded": 1, "scout_paths": [str(scout_path)]}),
                encoding="utf-8",
            )
        elif script_name == "export_ga4_demand.py":
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
                                "source_url": "https://lookerstudio.google.com/reporting/algolia-demand",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout='{"record_count":1,"status":"ok"}', stderr="")
        elif script_name == "build_product_market_payload.py":
            payload_output = Path(cmd[cmd.index("--output") + 1])
            payload_output.write_text(json.dumps({"tenant_id": 1}), encoding="utf-8")
        elif script_name == "run_product_market_intelligence.py":
            return SimpleNamespace(returncode=0, stdout='{"verdict":"watch"}', stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
            "CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME": "Algolia",
            "CIOS_PRODUCT_MARKET_PROVIDER": "gemini/gemini-2.5-flash",
            "CIOS_GA4_EXPORT_ENABLED": "1",
            "CIOS_GA4_PROPERTY_ID": "123456",
            "CIOS_GA4_CURRENT_START": "2026-07-01",
            "CIOS_GA4_CURRENT_END": "2026-07-08",
            "CIOS_GA4_PREVIOUS_START": "2026-06-24",
            "CIOS_GA4_PREVIOUS_END": "2026-06-30",
            "CIOS_GA4_SOURCE_URL": "https://lookerstudio.google.com/reporting/algolia-demand",
        },
    )

    assert [Path(call[1]).name for call in calls] == [
        "build_next_sweep_learning_plan.py",
        "build_learning_apply_plan.py",
        "execute_learning_apply_plan.py",
        "plan_product_surface_exports.py",
        "execute_product_surface_plan.py",
        "export_ga4_demand.py",
        "build_product_market_payload.py",
        "run_product_market_intelligence.py",
        "refresh_product_market_from_ledger.py",
    ]
    ga4_call = next(call for call in calls if Path(call[1]).name == "export_ga4_demand.py")
    payload_call = next(call for call in calls if Path(call[1]).name == "build_product_market_payload.py")
    assert ga4_call[ga4_call.index("--property-id") + 1] == "123456"
    assert ga4_call[ga4_call.index("--current-start") + 1] == "2026-07-01"
    assert "--credentials-json" not in ga4_call
    payload_looker_path = Path(payload_call[payload_call.index("--looker") + 1])
    assert payload_looker_path.name == "ga4-demand.normalized.json"
    assert result["ga4_export_status"] == "ran"
    assert result["ga4_export_path"].endswith("ga4-demand.json")
    assert result["looker_export_count"] == 1
    assert result["looker_normalized_row_count"] == 1


def test_export_ga4_demand_if_enabled_uses_rolling_window_when_dates_are_omitted(daily_run, tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        calls.append([str(part) for part in cmd])
        return SimpleNamespace(returncode=0, stdout='{"record_count":3,"status":"ok"}', stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    summary = daily_run.export_ga4_demand_if_enabled(
        env={
            "CIOS_GA4_EXPORT_ENABLED": "1",
            "CIOS_GA4_PROPERTY_ID": "123456",
            "CIOS_GA4_TODAY": "2026-07-12",
        },
        work_dir=tmp_path,
        python_bin="python",
    )

    command = calls[0]
    assert command[command.index("--current-start") + 1] == "2026-07-05"
    assert command[command.index("--current-end") + 1] == "2026-07-11"
    assert command[command.index("--previous-start") + 1] == "2026-06-28"
    assert command[command.index("--previous-end") + 1] == "2026-07-04"
    assert summary == {
        "status": "ran",
        "path": str(tmp_path / "ga4-demand.json"),
        "record_count": 3,
    }


def test_product_market_chain_emits_hermes_stage_heartbeats(daily_run, tmp_path, monkeypatch, capsys):
    calls = []
    scout_path = tmp_path / "surface-exports" / "000011-constructor-changelog.json"

    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        calls.append(cmd)
        script_name = Path(cmd[1]).name
        if script_name == "build_next_sweep_learning_plan.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"tenant_id": 1, "instructions": [], "skipped": []}), encoding="utf-8")
        elif script_name == "plan_product_surface_exports.py":
            output = Path(cmd[cmd.index("--plan-output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"tenant_id": 1, "target_count": 1, "items": []}), encoding="utf-8")
        elif script_name == "execute_product_surface_plan.py":
            scout_path.parent.mkdir(parents=True, exist_ok=True)
            scout_path.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")
            output = Path(cmd[cmd.index("--summary-output") + 1])
            output.write_text(json.dumps({"failed": 0, "succeeded": 1, "scout_paths": [str(scout_path)]}), encoding="utf-8")
        elif script_name == "build_product_market_payload.py":
            output = Path(cmd[cmd.index("--output") + 1])
            output.write_text(json.dumps({"tenant_id": 1}), encoding="utf-8")
        elif script_name == "run_product_market_intelligence.py":
            return SimpleNamespace(returncode=0, stdout='{"verdict":"quiet"}', stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
            "CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME": "Algolia",
        },
    )

    captured = capsys.readouterr().out
    events = [
        json.loads(line.removeprefix("CIOS_PRODUCT_MARKET_STAGE "))
        for line in captured.splitlines()
        if line.startswith("CIOS_PRODUCT_MARKET_STAGE ")
    ]

    assert [event["stage"] for event in events if event["event"] == "start"] == [
        "next_sweep_learning_plan",
        "learning_apply_plan",
        "learning_apply_execute",
        "product_surface_plan",
        "product_surface_export",
        "demand_export",
        "looker_prepare",
        "product_market_payload",
        "product_market_synthesis",
        "product_market_ledger_refresh",
        "looker_archive",
    ]
    assert [event["stage"] for event in events if event["event"] == "done"] == [
        "next_sweep_learning_plan",
        "learning_apply_plan",
        "learning_apply_execute",
        "product_surface_plan",
        "product_surface_export",
        "demand_export",
        "looker_prepare",
        "product_market_payload",
        "product_market_synthesis",
        "product_market_ledger_refresh",
        "looker_archive",
    ]
    assert all(event["tenant"] == "algolia" for event in events)
    assert all("elapsed_s" in event for event in events if event["event"] == "done")
    assert [entry["stage"] for entry in result["stage_ledger"]] == [
        "next_sweep_learning_plan",
        "learning_apply_plan",
        "learning_apply_execute",
        "product_surface_plan",
        "product_surface_export",
        "demand_export",
        "looker_prepare",
        "product_market_payload",
        "product_market_synthesis",
        "product_market_ledger_refresh",
        "looker_archive",
    ]
    assert all(entry["status"] == "completed" for entry in result["stage_ledger"])
    assert all(entry["tenant"] == "algolia" for entry in result["stage_ledger"])
    assert all(entry["elapsed_s"] >= 0 for entry in result["stage_ledger"])
    assert all(entry["started_at"].endswith("Z") for entry in result["stage_ledger"])
    assert all(entry["ended_at"].endswith("Z") for entry in result["stage_ledger"])


def test_product_market_stage_ledger_records_failed_stage(daily_run):
    stage_ledger = []

    with pytest.raises(RuntimeError, match="boom"):
        daily_run._run_product_market_stage(
            slug="algolia",
            stage="product_market_synthesis",
            stage_ledger=stage_ledger,
            action=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    assert len(stage_ledger) == 1
    entry = stage_ledger[0]
    assert entry["tenant"] == "algolia"
    assert entry["stage"] == "product_market_synthesis"
    assert entry["status"] == "failed"
    assert entry["error_type"] == "RuntimeError"
    assert entry["error"] == "boom"
    assert entry["elapsed_s"] >= 0
    assert entry["started_at"].endswith("Z")
    assert entry["ended_at"].endswith("Z")


def test_product_market_stage_redacts_sensitive_environment_values(
    daily_run, monkeypatch, capsys
):
    stage_ledger = []
    monkeypatch.setenv("GEMINI_API_KEY", "phase-one-stage-secret")

    with pytest.raises(RuntimeError) as exc_info:
        daily_run._run_product_market_stage(
            slug="algolia",
            stage="product_market_synthesis",
            stage_ledger=stage_ledger,
            action=lambda: (_ for _ in ()).throw(RuntimeError("phase-one-stage-secret")),
        )

    assert stage_ledger[0]["error"] == "[redacted]"
    assert "phase-one-stage-secret" not in str(exc_info.value)
    assert "phase-one-stage-secret" not in capsys.readouterr().out


def test_run_checked_redacts_sensitive_environment_values(daily_run, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "phase-one-command-secret")

    with pytest.raises(RuntimeError) as exc_info:
        daily_run._run_checked(
            [
                sys.executable,
                "-c",
                "import os, sys; print(os.environ['GEMINI_API_KEY'], file=sys.stderr); sys.exit(1)",
            ],
            timeout_seconds=5,
        )

    assert "phase-one-command-secret" not in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)


def test_run_checked_timeout_kills_descendant_process_group(daily_run, tmp_path):
    orphan_marker = tmp_path / "daily-orphan-after-timeout.txt"
    child_code = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(0.8); "
        "pathlib.Path(sys.argv[1]).write_text('orphan', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, sys.argv[1]]); "
        "time.sleep(5)"
    )

    with pytest.raises(RuntimeError, match="timed out after 0.2s"):
        daily_run._run_checked(
            [sys.executable, "-c", parent_code, str(orphan_marker)],
            timeout_seconds=0.2,
        )
    time.sleep(1.0)

    assert not orphan_marker.exists()


def test_run_checked_timeout_kills_detached_descendant(daily_run, tmp_path):
    if not daily_run.PROCESS_GROUPS.cgroup_enabled:
        pytest.skip("requires delegated cgroup v2 containment")
    orphan_marker = tmp_path / "daily-detached-orphan.txt"
    child_code = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(0.8); "
        "pathlib.Path(sys.argv[1]).write_text('orphan', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, sys.argv[1]], start_new_session=True); "
        "time.sleep(5)"
    )

    with pytest.raises(RuntimeError, match="timed out after 0.2s"):
        daily_run._run_checked(
            [sys.executable, "-c", parent_code, str(orphan_marker)],
            timeout_seconds=0.2,
        )
    time.sleep(1.0)

    assert not orphan_marker.exists()


def test_run_main_redacts_uncaught_exception(daily_run, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "phase-one-main-secret")

    async def fail_main():
        raise RuntimeError("phase-one-main-secret")

    monkeypatch.setattr(daily_run, "main", fail_main)

    assert daily_run.run_main() == 2
    captured = capsys.readouterr()
    assert "phase-one-main-secret" not in captured.err
    assert "[redacted]" in captured.err


def test_product_market_chain_returns_failed_summary_with_stage_ledger(daily_run, tmp_path, monkeypatch):
    def fake_run(cmd, capture_output, text, timeout, check):
        del capture_output, text, timeout, check
        script_name = Path(cmd[1]).name
        if script_name == "build_next_sweep_learning_plan.py":
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily_run, "_run_process_group", fake_run)

    result = daily_run.run_product_market_chain_if_enabled(
        slug="algolia",
        tenant_id=1,
        env={
            "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE": "1",
            "CIOS_PRODUCT_MARKET_WORKDIR": str(tmp_path),
        },
    )

    assert result["status"] == "failed"
    assert "command failed: build_next_sweep_learning_plan.py: boom" in result["error"]
    assert result["stage_ledger"][0]["tenant"] == "algolia"
    assert result["stage_ledger"][0]["stage"] == "next_sweep_learning_plan"
    assert result["stage_ledger"][0]["status"] == "failed"
    assert result["stage_ledger"][0]["error_type"] == "RuntimeError"


def test_persist_product_market_stage_ledger_writes_through_repo(daily_run, monkeypatch):
    saved = []
    fake_conn = object()

    class FakeProductMarketRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def save_run_stage_ledger(self, **kwargs):
            saved.append(kwargs)
            return 789

    monkeypatch.setattr(daily_run, "PgProductMarketRepository", FakeProductMarketRepository)

    ledger_id = daily_run.persist_product_market_stage_ledger(
        fake_conn,
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        product_market_summary={
            "status": "ran",
            "stage_ledger": [
                {
                    "tenant": "algolia",
                    "stage": "product_surface_export",
                    "status": "completed",
                    "started_at": "2026-07-11T22:35:00Z",
                    "ended_at": "2026-07-11T22:35:05Z",
                    "elapsed_s": 5.1,
                }
            ],
        },
    )

    assert ledger_id == 789
    assert saved == [
        {
            "tenant_id": 1,
            "run_id": "daily-algolia-2026-07-11",
            "package_name": "cios.product_market",
            "status": "completed",
            "stage_ledger": [
                {
                    "tenant": "algolia",
                    "stage": "product_surface_export",
                    "status": "completed",
                    "started_at": "2026-07-11T22:35:00Z",
                    "ended_at": "2026-07-11T22:35:05Z",
                    "elapsed_s": 5.1,
                }
            ],
            "metadata": {"product_market_status": "ran"},
        }
    ]


def test_persist_product_market_stage_ledger_skips_empty_summary(daily_run, monkeypatch):
    class ExplodingProductMarketRepository:
        def __init__(self, conn):
            raise AssertionError("repository should not be constructed without stage ledger")

    monkeypatch.setattr(daily_run, "PgProductMarketRepository", ExplodingProductMarketRepository)

    assert daily_run.persist_product_market_stage_ledger(
        object(),
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        product_market_summary={"status": "skipped_disabled"},
    ) is None


def test_daily_run_stage_ledger_from_result_captures_core_run_state(daily_run):
    result = daily_run.TenantResult("algolia")
    result.sources_planned_count = 48
    result.sources_attempted_count = 48
    result.sources_fetched = [{"url": "https://ok.example"}] * 43
    result.sources_failed = [{"url": "https://fail.example"}] * 5
    result.sources_skipped = []
    result.facts_extracted = 469
    result.deltas_extracted = 469
    result.promoted_signals = [{"headline": "Constructor moved"}]
    result.synth_verdict = "signals"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.deliveries = [{"channel": "telegram", "status": "sent", "id": 101}]
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    ledger = daily_run.daily_run_stage_ledger_from_result(result)

    assert [(entry["stage"], entry["status"]) for entry in ledger] == [
        ("registry_resolution", "completed"),
        ("source_sweep", "completed"),
        ("synthesis", "completed"),
        ("quality_review", "completed"),
        ("false_negative_audit", "completed"),
        ("delivery", "completed"),
        ("product_market_chain", "completed"),
        ("dashboard_state_build", "completed"),
        ("publish_gate", "completed"),
    ]
    source_sweep = ledger[1]
    assert source_sweep["metadata"] == {
        "active_sources": 48,
        "attempted_sources": 48,
        "fetched_sources": 43,
        "failed_sources": 5,
        "skipped_sources": 0,
    }
    product_market = ledger[6]
    assert product_market["metadata"]["product_market_status"] == "ran"
    assert product_market["metadata"]["product_market_stage_ledger_id"] == 789


def test_persist_daily_run_stage_ledger_writes_coarse_run_truth(daily_run, monkeypatch):
    saved = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")
    result.sources_planned_count = 1
    result.sources_attempted_count = 1
    result.sources_fetched = [{"url": "https://ok.example"}]
    result.facts_extracted = 1
    result.deltas_extracted = 1
    result.synth_verdict = "quiet"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def save_run_stage_ledger(self, **kwargs):
            saved.append(kwargs)
            return 456

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)

    ledger_id = daily_run.persist_daily_run_stage_ledger(
        fake_conn,
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        result=result,
    )

    assert ledger_id == 456
    assert saved[0]["tenant_id"] == 1
    assert saved[0]["run_id"] == "daily-algolia-2026-07-11"
    assert saved[0]["package_name"] == "cios.daily"
    assert saved[0]["status"] == "completed"
    assert saved[0]["metadata"] == {
        "tenant": "algolia",
        "product_market_stage_ledger_id": 789,
    }
    assert [entry["stage"] for entry in saved[0]["stage_ledger"]] == [
        "registry_resolution",
        "source_sweep",
        "synthesis",
        "quality_review",
        "false_negative_audit",
        "delivery",
        "product_market_chain",
        "dashboard_state_build",
        "publish_gate",
    ]


def test_persist_daily_run_stage_ledger_finishes_existing_running_ledger(daily_run, monkeypatch):
    calls = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")
    result.daily_stage_ledger_id = 999
    result.sources_planned_count = 2
    result.sources_attempted_count = 2
    result.sources_fetched = [{"url": "https://ok.example"}]
    result.sources_failed = [{"url": "https://fail.example"}]
    result.facts_extracted = 1
    result.deltas_extracted = 1
    result.synth_verdict = "quiet"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def save_run_stage_ledger(self, **kwargs):
            raise AssertionError("existing running ledger should be finished, not duplicated")

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

        def finish_ledger(self, **kwargs):
            calls.append(("finish_ledger", kwargs))

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)

    ledger_id = daily_run.persist_daily_run_stage_ledger(
        fake_conn,
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        result=result,
    )

    assert ledger_id == 999
    start_calls = [call for call in calls if call[0] == "start_stage"]
    finish_calls = [call for call in calls if call[0] == "finish_stage"]
    assert len(start_calls) == 9
    assert len(finish_calls) == 9
    assert start_calls[0][1]["ledger_id"] == 999
    assert start_calls[0][1]["stage_order"] == 1
    assert start_calls[0][1]["stage"] == "registry_resolution"
    assert finish_calls[0][1]["event_id"] == 1001
    assert finish_calls[0][1]["status"] == "completed"
    assert calls[-1] == (
        "finish_ledger",
        {
            "tenant_id": 1,
            "ledger_id": 999,
            "status": "completed",
            "metadata": {
                "tenant": "algolia",
                "product_market_stage_ledger_id": 789,
            },
        },
    )


def test_daily_run_stage_recorder_starts_running_ledger(daily_run):
    calls = []

    class FakeRunStageRepository:
        def start_ledger(self, **kwargs):
            calls.append(("start_ledger", kwargs))
            return 999

    recorder = daily_run.DailyRunStageRecorder(
        FakeRunStageRepository(),
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        package_name="cios.daily",
    )

    ledger_id = recorder.start(metadata={"tenant": "algolia", "cadence": "daily"})

    assert ledger_id == 999
    assert recorder.ledger_id == 999
    assert calls == [
        (
            "start_ledger",
            {
                "tenant_id": 1,
                "run_id": "daily-algolia-2026-07-11",
                "package_name": "cios.daily",
                "metadata": {"tenant": "algolia", "cadence": "daily"},
            },
        )
    ]


def test_daily_run_stage_recorder_records_success_and_failure(daily_run):
    calls = []

    class FakeRunStageRepository:
        def start_ledger(self, **kwargs):
            calls.append(("start_ledger", kwargs))
            return 999

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

    recorder = daily_run.DailyRunStageRecorder(
        FakeRunStageRepository(),
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
    )

    assert recorder.run_stage(
        stage="product_market_chain",
        stage_order=7,
        action=lambda: "ok",
        metadata={"before": True},
        finish_metadata=lambda result: {"result": result},
    ) == "ok"
    with pytest.raises(RuntimeError, match="boom"):
        recorder.run_stage(
            stage="publish_gate",
            stage_order=9,
            action=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    assert calls[0][0] == "start_ledger"
    assert calls[1] == (
        "start_stage",
        {
            "tenant_id": 1,
            "ledger_id": 999,
            "stage_order": 7,
            "stage": "product_market_chain",
            "metadata": {"before": True},
        },
    )
    assert calls[2] == (
        "finish_stage",
        {
            "tenant_id": 1,
            "event_id": 1007,
            "status": "completed",
            "metadata": {"result": "ok"},
        },
    )
    assert calls[4][0] == "finish_stage"
    assert calls[4][1]["status"] == "failed"
    assert calls[4][1]["error_type"] == "RuntimeError"
    assert calls[4][1]["error"] == "boom"


def test_daily_run_stage_recorder_redacts_sensitive_failure(daily_run, monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://phase-one-ledger-secret")

    class FakeRunStageRepository:
        def start_ledger(self, **kwargs):
            return 999

        def start_stage(self, **kwargs):
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(kwargs)

    recorder = daily_run.DailyRunStageRecorder(
        FakeRunStageRepository(),
        tenant_id=1,
        run_id="daily-algolia-2026-07-14",
    )

    with pytest.raises(RuntimeError) as exc_info:
        recorder.run_stage(
            stage="publish_gate",
            stage_order=9,
            action=lambda: (_ for _ in ()).throw(
                RuntimeError("postgresql://phase-one-ledger-secret")
            ),
        )

    assert calls[-1]["error"] == "[redacted]"
    assert "phase-one-ledger-secret" not in str(exc_info.value)


def test_daily_run_stage_recorder_exposes_explicit_start_and_finish(daily_run):
    calls = []
    recorded_orders = set()

    class FakeRunStageRepository:
        def start_ledger(self, **kwargs):
            calls.append(("start_ledger", kwargs))
            return 999

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

    recorder = daily_run.DailyRunStageRecorder(
        FakeRunStageRepository(),
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        recorded_stage_orders=recorded_orders,
    )

    event_id = recorder.start_stage(
        stage="source_sweep",
        stage_order=2,
        metadata={"active_sources": 48},
    )
    recorder.finish_stage(
        event_id=event_id,
        status="completed",
        metadata={"fetched_sources": 43},
    )

    assert event_id == 1002
    assert recorded_orders == {2}
    assert calls[1] == (
        "start_stage",
        {
            "tenant_id": 1,
            "ledger_id": 999,
            "stage_order": 2,
            "stage": "source_sweep",
            "metadata": {"active_sources": 48},
        },
    )
    assert calls[2] == (
        "finish_stage",
        {
            "tenant_id": 1,
            "event_id": 1002,
            "status": "completed",
            "metadata": {"fetched_sources": 43},
        },
    )


def test_persist_daily_run_stage_ledger_does_not_overwrite_live_recorded_stages(daily_run, monkeypatch):
    calls = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")
    result.daily_stage_ledger_id = 999
    result.daily_live_stage_orders = {1, 2}
    result.sources_planned_count = 2
    result.sources_attempted_count = 2
    result.sources_fetched = [{"url": "https://ok.example"}]
    result.sources_failed = [{"url": "https://fail.example"}]
    result.facts_extracted = 1
    result.deltas_extracted = 1
    result.synth_verdict = "quiet"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

        def finish_ledger(self, **kwargs):
            calls.append(("finish_ledger", kwargs))

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)

    assert daily_run.persist_daily_run_stage_ledger(
        fake_conn,
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        result=result,
    ) == 999

    started_stage_orders = [
        call[1]["stage_order"]
        for call in calls
        if call[0] == "start_stage"
    ]
    assert started_stage_orders == [3, 4, 5, 6, 7, 8, 9]
    assert all(order not in started_stage_orders for order in result.daily_live_stage_orders)


def test_persist_daily_run_stage_ledger_can_defer_publish_gate_without_finishing(daily_run, monkeypatch):
    calls = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")
    result.daily_stage_ledger_id = 999
    result.daily_live_stage_orders = {1, 2, 3, 4, 6, 7, 8}
    result.sources_planned_count = 2
    result.sources_attempted_count = 2
    result.sources_fetched = [{"url": "https://ok.example"}]
    result.sources_failed = [{"url": "https://fail.example"}]
    result.facts_extracted = 1
    result.deltas_extracted = 1
    result.synth_verdict = "quiet"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

        def finish_ledger(self, **kwargs):
            calls.append(("finish_ledger", kwargs))

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)

    assert daily_run.persist_daily_run_stage_ledger(
        fake_conn,
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        result=result,
        deferred_stage_orders={9},
        finish_ledger=False,
    ) == 999

    assert [call[1]["stage_order"] for call in calls if call[0] == "start_stage"] == [5]
    assert not any(call[0] == "finish_ledger" for call in calls)


def test_start_daily_run_stage_ledger_sets_result_id(daily_run, monkeypatch):
    calls = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def start_ledger(self, **kwargs):
            calls.append(kwargs)
            return 999

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)

    ledger_id = daily_run.start_daily_run_stage_ledger(
        fake_conn,
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        result=result,
    )

    assert ledger_id == 999
    assert result.daily_stage_ledger_id == 999
    assert result.errors == []
    assert calls == [
        {
            "tenant_id": 1,
            "run_id": "daily-algolia-2026-07-11",
            "package_name": "cios.daily",
            "metadata": {"tenant": "algolia", "cadence": "daily"},
        }
    ]


def test_run_tenant_starts_daily_stage_ledger_before_registry_work() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    stage_ledger_start = source.index("start_daily_run_stage_ledger(", run_tenant_start)
    registry_start = source.index("comp_ids = seed_competitors", run_tenant_start)

    assert stage_ledger_start < registry_start


def test_run_tenant_streams_registry_resolution_stage_around_registry_work() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    stage_start = source.index('stage="registry_resolution"', run_tenant_start)
    registry_start = source.index("comp_ids = seed_competitors", run_tenant_start)
    registry_finish = source.index('status="completed"', registry_start)
    fetcher_setup = source.index("fetch_timeout, fetch_retries = fetch_settings", run_tenant_start)

    assert stage_start < registry_start < registry_finish < fetcher_setup


def test_run_tenant_streams_source_sweep_stage_around_collection_loop() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    source_stage_start = source.index('stage="source_sweep"', run_tenant_start)
    collection_loop = source.index("for c in runtime_source_plan:", run_tenant_start)
    source_stage_finish = source.index('source_sweep_done_marker = "source_sweep_done"', collection_loop)
    facts_assignment = source.index("res.facts_extracted = len(all_facts)", run_tenant_start)

    assert source_stage_start < collection_loop < facts_assignment < source_stage_finish


def test_run_tenant_streams_synthesis_stage_around_synthesis_work() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    synthesis_stage_start = source.index('stage="synthesis"', run_tenant_start)
    synthesis_settings_start = source.index("max_synth_competitors, max_synth_deltas", run_tenant_start)
    promoted_assignment = source.index("res.promoted_signals = promoted", synthesis_settings_start)
    synthesis_stage_finish = source.index('synthesis_done_marker = "synthesis_done"', promoted_assignment)
    quality_start = source.index("claims_for_review = [review_claim_for_signal", run_tenant_start)

    assert synthesis_stage_start < synthesis_settings_start < promoted_assignment < synthesis_stage_finish < quality_start


def test_run_tenant_streams_quality_review_stage_around_quality_work() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    quality_stage_start = source.index('stage="quality_review"', run_tenant_start)
    claims_start = source.index("claims_for_review = [review_claim_for_signal", run_tenant_start)
    quality_status_assignment = source.index("res.quality_status = qr.status.value", claims_start)
    quality_stage_finish = source.index('quality_review_done_marker = "quality_review_done"', quality_status_assignment)
    persistence_start = source.index("published_ids: list[int] = []", quality_status_assignment)

    assert quality_stage_start < claims_start < quality_status_assignment < quality_stage_finish < persistence_start


def test_run_tenant_streams_delivery_stage_around_delivery_work() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    delivery_stage_start = source.index('stage="delivery"', run_tenant_start)
    delivery_start = source.index("message_markdown = build_daily_message", run_tenant_start)
    delivery_assignment = source.index("res.deliveries = [", delivery_start)
    delivery_stage_finish = source.index('delivery_done_marker = "delivery_done"', delivery_assignment)
    product_market_start = source.index("product_market_conversation_records =", run_tenant_start)

    assert delivery_stage_start < delivery_start < delivery_assignment < delivery_stage_finish < product_market_start


def test_run_tenant_streams_product_market_stage_around_product_market_work() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    product_market_stage_start = source.index('stage="product_market_chain"', run_tenant_start)
    product_market_input_start = source.index("product_market_conversation_records =", run_tenant_start)
    product_market_summary_assignment = source.index(
        'run_dict["product_market_summary"] = res.product_market_summary',
        product_market_input_start,
    )
    product_market_stage_finish = source.index(
        'product_market_done_marker = "product_market_done"',
        product_market_summary_assignment,
    )
    dashboard_start = source.index("builder = DashboardStateBuilder", run_tenant_start)

    assert (
        product_market_stage_start
        < product_market_input_start
        < product_market_summary_assignment
        < product_market_stage_finish
        < dashboard_start
    )


def test_run_tenant_streams_dashboard_state_stage_around_dashboard_build() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    run_tenant_start = source.index("async def run_tenant")
    dashboard_stage_start = source.index('stage="dashboard_state_build"', run_tenant_start)
    builder_start = source.index("builder = DashboardStateBuilder", run_tenant_start)
    insert_dashboard = source.index("insert_dashboard_state(", builder_start)
    dashboard_stage_finish = source.index('dashboard_state_done_marker = "dashboard_state_done"', insert_dashboard)
    daily_persist = source.index("res.daily_stage_ledger_id = persist_daily_run_stage_ledger", run_tenant_start)

    assert dashboard_stage_start < builder_start < insert_dashboard < dashboard_stage_finish < daily_persist


def test_main_defers_publish_gate_until_public_artifact_publish() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    helper_start = source.index("def record_daily_publish_gate_stage")
    artifact_writer = source.index("write_dashboard_artifacts(", helper_start)
    main_start = source.index("async def main")
    run_tenant_call = source.index("r = await run_tenant(", main_start)
    defer_arg = source.index("defer_publish_gate=(slug == deliver_tenant)", run_tenant_call)
    delivered_result_lookup = source.index("delivered_result = next(", run_tenant_call)
    publish_gate_recording = source.index("record_daily_publish_gate_stage(", delivered_result_lookup)

    assert helper_start < artifact_writer < main_start
    assert run_tenant_call < defer_arg < delivered_result_lookup < publish_gate_recording


def test_record_daily_publish_gate_stage_writes_artifacts_and_finishes_ledger(daily_run, monkeypatch, tmp_path):
    calls = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")
    result.tenant_id = 1
    result.daily_stage_ledger_id = 999
    result.sources_attempted_count = 1
    result.sources_fetched = [{"url": "https://ok.example"}]
    result.facts_extracted = 1
    result.deltas_extracted = 1
    result.synth_verdict = "quiet"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

        def finish_ledger(self, **kwargs):
            calls.append(("finish_ledger", kwargs))

    def fake_write_dashboard_artifacts(*args, **kwargs):
        calls.append(("write_dashboard_artifacts", kwargs))
        return {
            "cockpit": tmp_path / "index.html",
            "full_brief": tmp_path / "brief.html",
            "json": tmp_path / "data.json",
            "competitor_briefs": [tmp_path / "constructor.html"],
        }

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)
    monkeypatch.setattr(daily_run, "write_dashboard_artifacts", fake_write_dashboard_artifacts)

    paths = daily_run.record_daily_publish_gate_stage(
        fake_conn,
        tenant_id=1,
        deliver_tenant="algolia",
        result=result,
        html_path=tmp_path / "argus-dashboard.html",
        cockpit_path=tmp_path / "index.html",
        report_date=daily_run.date(2026, 7, 11),
    )

    assert paths is not None
    assert calls[0][0] == "start_stage"
    assert calls[0][1]["stage_order"] == 9
    assert calls[0][1]["stage"] == "publish_gate"
    assert calls[1][0] == "write_dashboard_artifacts"
    assert calls[2][0] == "finish_stage"
    assert calls[2][1]["status"] == "completed"
    assert calls[2][1]["metadata"]["publish_allowed"] is True
    assert calls[2][1]["metadata"]["competitor_brief_count"] == 1
    assert calls[3] == (
        "finish_ledger",
        {
            "tenant_id": 1,
            "ledger_id": 999,
            "status": "completed",
            "metadata": {
                "tenant": "algolia",
                "product_market_stage_ledger_id": 789,
                "publish_artifacts": {
                    "cockpit": str(tmp_path / "index.html"),
                    "full_brief": str(tmp_path / "brief.html"),
                    "json": str(tmp_path / "data.json"),
                    "competitor_brief_count": 1,
                },
            },
        },
    )


def test_record_daily_publish_gate_stage_blocks_public_publish_but_writes_local_artifacts(
    daily_run, monkeypatch, tmp_path
):
    calls = []
    fake_conn = object()
    result = daily_run.TenantResult("algolia")
    result.tenant_id = 1
    result.daily_stage_ledger_id = 999
    result.sources_attempted_count = 1
    result.sources_fetched = [{"url": "https://ok.example"}]
    result.facts_extracted = 1
    result.deltas_extracted = 1
    result.synth_verdict = "coverage_failure"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True
    result.dashboard_state = object()
    result.product_market_summary = {"status": "ran", "stage_ledger_id": 789}

    class FakeRunStageRepository:
        def __init__(self, conn):
            assert conn is fake_conn

        def start_stage(self, **kwargs):
            calls.append(("start_stage", kwargs))
            return 1000 + kwargs["stage_order"]

        def finish_stage(self, **kwargs):
            calls.append(("finish_stage", kwargs))

        def finish_ledger(self, **kwargs):
            calls.append(("finish_ledger", kwargs))

    def fake_write_dashboard_artifacts(*args, **kwargs):
        calls.append(("write_dashboard_artifacts", kwargs))
        return {
            "cockpit": tmp_path / "argus-dashboard.html",
            "full_brief": tmp_path / "brief.html",
            "json": tmp_path / "argus-dashboard.json",
            "competitor_briefs": [],
        }

    monkeypatch.setattr(daily_run, "PgRunStageRepository", FakeRunStageRepository)
    monkeypatch.setattr(daily_run, "write_dashboard_artifacts", fake_write_dashboard_artifacts)

    paths = daily_run.record_daily_publish_gate_stage(
        fake_conn,
        tenant_id=1,
        deliver_tenant="algolia",
        result=result,
        html_path=tmp_path / "argus-dashboard.html",
        cockpit_path=tmp_path / "index.html",
        report_date=daily_run.date(2026, 7, 11),
    )

    assert paths is not None
    assert calls[0][0] == "start_stage"
    assert calls[1][0] == "write_dashboard_artifacts"
    assert calls[2][0] == "finish_stage"
    assert calls[2][1]["status"] == "failed"
    assert calls[2][1]["metadata"]["publish_allowed"] is False
    assert calls[2][1]["metadata"]["block_reason"] == "coverage_failure"
    assert calls[2][1]["metadata"]["json"] == str(tmp_path / "argus-dashboard.json")
    assert calls[3][0] == "finish_ledger"
    assert calls[3][1]["status"] == "failed"
    assert calls[3][1]["metadata"]["publish_artifacts"]["json"] == str(tmp_path / "argus-dashboard.json")


@pytest.mark.asyncio
async def test_deliver_cadence_report_uses_tenant_scoped_quality_review(daily_run, monkeypatch):
    delivered = []

    class FakeRepo:
        def __init__(self, _conn):
            pass

    class FakeCommander:
        def __init__(self, **_kwargs):
            pass

        async def deliver(self, request, quality_verdict):
            delivered.append((request, quality_verdict))

    monkeypatch.setattr(daily_run, "PgLearningEventRepository", FakeRepo)
    monkeypatch.setattr(daily_run, "PgImprovementQueueRepository", FakeRepo)
    monkeypatch.setattr(daily_run, "PgBotDeliveryRepository", FakeRepo)
    monkeypatch.setattr(daily_run, "PgDeliveryAttemptRepository", FakeRepo)
    monkeypatch.setattr(daily_run, "GatedDeliveryCommander", FakeCommander)

    await daily_run._deliver_cadence_report(
        object(),
        tenant_id=7,
        slug="algolia",
        adapter=object(),
        cadence=daily_run.Cadence.WEEKLY,
        report_id=42,
        title="Argus weekly review - algolia",
        markdown_body="Weekly body",
    )

    assert delivered
    request, quality_verdict = delivered[0]
    assert request.tenant_id == 7
    assert quality_verdict.tenant_id == 7
    assert quality_verdict.status.value == "passed"


def test_dashboard_publish_requires_passed_quality(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "failed"

    assert daily_run.should_publish_dashboard(result) is False

    result.quality_status = "passed"
    assert daily_run.should_publish_dashboard(result) is True


def test_dashboard_publish_blocks_failed_product_market_chain(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {
        "status": "failed",
        "error": "TimeoutExpired: command timed out",
    }

    assert daily_run.should_publish_dashboard(result) is False


def test_dashboard_publish_blocks_product_market_run_with_no_surface_outputs(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {
        "status": "skipped_no_product_surface_outputs",
        "scout_paths": [],
    }

    assert daily_run.should_publish_dashboard(result) is False


def test_dashboard_publish_blocks_product_market_run_without_demand_source(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {
        "status": "ran",
        "scout_paths": ["/tmp/product.json"],
        "conversation_record_count": 12,
        "ga4_export_status": "skipped_disabled",
        "ga4_export_record_count": 0,
        "looker_ready_count": 0,
        "looker_normalized_row_count": 0,
        "runner_summary": {"demand_signal_count": 0},
        "ledger_refresh_summary": {"demand_signal_count": 0},
    }

    assert daily_run.should_publish_dashboard(result) is False
    assert daily_run.product_market_publish_block_reason(result).startswith("demand_source_status=missing")
    assert daily_run.publish_gate_exit_code(result) == 3


def test_publish_gate_exit_code_keeps_runtime_failure_distinct_from_readiness_block(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {
        "status": "failed",
        "error": "TimeoutExpired: command timed out",
    }

    assert daily_run.publish_gate_exit_code(result) == 2


def test_dashboard_publish_allows_product_market_run_with_ledger_demand(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {
        "status": "ran",
        "scout_paths": ["/tmp/product.json"],
        "conversation_record_count": 12,
        "ga4_export_status": "skipped_disabled",
        "ga4_export_record_count": 0,
        "looker_ready_count": 0,
        "looker_normalized_row_count": 0,
        "runner_summary": {"demand_signal_count": 0},
        "ledger_refresh_summary": {"demand_signal_count": 2},
    }

    assert daily_run.should_publish_dashboard(result) is True


def test_dashboard_publish_allows_product_market_run_with_manual_looker_demand(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {
        "status": "ran",
        "scout_paths": ["/tmp/product.json"],
        "conversation_record_count": 12,
        "ga4_export_status": "skipped_disabled",
        "ga4_export_record_count": 0,
        "looker_ready_count": 1,
        "looker_normalized_row_count": 4,
        "runner_summary": {"demand_signal_count": 4},
        "ledger_refresh_summary": {"demand_signal_count": 4},
    }

    assert daily_run.should_publish_dashboard(result) is True


def test_dashboard_publish_allows_disabled_product_market_chain(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = daily_run.Verdict.SIGNALS.value
    result.product_market_summary = {"status": "skipped_disabled"}

    assert daily_run.should_publish_dashboard(result) is True


def test_dashboard_publish_blocks_coverage_failure_even_if_quality_passed(daily_run):
    result = daily_run.TenantResult("algolia")
    result.dashboard_state = object()
    result.quality_status = "passed"
    result.synth_verdict = "coverage_failure"

    assert daily_run.should_publish_dashboard(result) is False


def test_quality_evidence_block_only_includes_cited_claim_sources(daily_run):
    claim = daily_run._ReviewClaim(
        text="Constructor positions AI Shopping Agent for natural language product discovery.",
        source_url="https://constructor.com/blog/ai-shopping-agent",
    )

    block = daily_run.ClaudeQualityReviewer._build_evidence_block(
        {
            "https://doofinder.com/blog": "Doofinder unrelated excerpt should not enter this review.",
            "https://constructor.com/blog/ai-shopping-agent": (
                "Constructor describes its AI Shopping Agent for natural language product discovery."
            ),
            "https://klevu.com/blog": "Klevu unrelated excerpt should not enter this review.",
        },
        claims=[claim],
    )

    assert "Constructor describes its AI Shopping Agent" in block
    assert "Doofinder unrelated excerpt" not in block
    assert "Klevu unrelated excerpt" not in block


def test_quality_review_claim_text_includes_signal_body_not_only_headline(daily_run):
    signal = {
        "headline": "Constructor pushes natural language shopping",
        "what_changed": "Constructor describes an AI Shopping Agent for commerce discovery.",
        "why_it_matters": "This appears to position discovery around agent-led guidance.",
        "implication": "Sales should watch whether this becomes the category story.",
        "evidence_urls": ["https://constructor.com/blog/ai-shopping-agent"],
    }

    claim = daily_run.review_claim_for_signal(signal)

    assert "Constructor pushes natural language shopping" in claim.text
    assert "Constructor describes an AI Shopping Agent" in claim.text
    assert "agent-led guidance" in claim.text
    assert "category story" in claim.text
    assert claim.source_url == "https://constructor.com/blog/ai-shopping-agent"


def test_tenant_run_summary_separates_active_attempted_fetched_failed_and_skipped(daily_run):
    result = daily_run.TenantResult("algolia")
    result.sources_planned_count = 48
    result.sources_attempted_count = 47
    result.sources_fetched = [{"url": "https://ok.example"}] * 42
    result.sources_failed = [{"url": "https://fail.example"}] * 5
    result.sources_skipped = [{"url": "https://skip.example"}]
    result.facts_extracted = 469
    result.deltas_extracted = 469
    result.synth_verdict = "quiet"
    result.quality_status = "passed"
    result.fn_status = "clean"
    result.delivered = True

    summary = daily_run.format_tenant_run_summary(result)

    assert "active_sources=48" in summary
    assert "attempted=47" in summary
    assert "fetched=42" in summary
    assert "failed=5" in summary
    assert "skipped=1" in summary
    assert "sources=42" not in summary


def test_write_dashboard_artifacts_publishes_competitor_briefs_and_stamped_cockpit(daily_run, tmp_path):
    from cios.dashboard.types import AttentionLevel, CompetitorSignalCard, DashboardState, MonitoredCompetitor

    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        competitor_cards=[
            CompetitorSignalCard(
                competitor_id=5,
                competitor_name="Constructor",
                attention_score=90,
                attention_level=AttentionLevel.ACT_NOW,
                action_cue="Act on Constructor.",
                top_signal_headline="Constructor ships AI shopping agent.",
                what_changed="Constructor changed the commerce agent narrative.",
                why_it_matters="This is a direct Algolia-facing movement.",
                evidence_ids=["https://constructor.example/agent"],
                delta_id=50,
            ),
            CompetitorSignalCard(
                competitor_id=6,
                competitor_name="Elastic",
                attention_score=70,
                attention_level=AttentionLevel.WATCH,
                action_cue="Watch Elastic.",
                top_signal_headline="Elastic pushes context engineering.",
                what_changed="Elastic changed its AI search story.",
                why_it_matters="This is a different market narrative.",
                evidence_ids=["https://elastic.example/context"],
                delta_id=60,
            ),
        ],
        monitored_competitors=[
            MonitoredCompetitor(
                competitor_id=5,
                competitor_name="Constructor",
                domain="constructor.example",
                active_source_count=2,
                checked_today=True,
                material_signal_count=1,
            ),
            MonitoredCompetitor(
                competitor_id=6,
                competitor_name="Elastic",
                domain="elastic.example",
                active_source_count=2,
                checked_today=True,
                material_signal_count=1,
            ),
            MonitoredCompetitor(
                competitor_id=7,
                competitor_name="Algonomy",
                domain="algonomy.example",
                active_source_count=2,
                checked_today=True,
                material_signal_count=0,
            ),
        ],
    )

    paths = daily_run.write_dashboard_artifacts(
        state,
        tenant_slug="algolia",
        html_path=tmp_path / "argus-dashboard.html",
        report_date="2026-07-10",
    )

    cockpit_html = paths["cockpit"].read_text(encoding="utf-8")
    constructor_brief = (tmp_path / "briefs" / "algolia" / "constructor-2026-07-10.html").read_text(
        encoding="utf-8"
    )

    assert paths["cockpit"] == tmp_path / "argus-dashboard.html"
    assert paths["full_brief"] == tmp_path / "brief.html"
    assert paths["json"] == tmp_path / "argus-dashboard.json"
    assert (tmp_path / "briefs" / "algolia" / "elastic-2026-07-10.html").exists()
    assert (tmp_path / "briefs" / "algolia" / "algonomy-2026-07-10.html").exists()
    assert 'href="./briefs/algolia/constructor-2026-07-10.html"' in cockpit_html
    assert 'href="./briefs/algolia/elastic-2026-07-10.html"' in cockpit_html
    assert 'href="./briefs/algolia/algonomy-2026-07-10.html"' in cockpit_html
    assert "Constructor ships AI shopping agent" in constructor_brief
    assert "Elastic pushes context engineering." not in constructor_brief


def test_select_synthesis_targets_caps_and_dedupes_prompt_inputs(daily_run):
    class Delta:
        def __init__(self, competitor_id, what_changed, materiality_score):
            self.competitor_id = competitor_id
            self.what_changed = what_changed
            self.materiality_score = materiality_score

    class Fact:
        def __init__(self, competitor_id, statement, materiality_score=0.0):
            self.competitor_id = competitor_id
            self.statement = statement
            self.materiality_score = materiality_score

    deltas_by_comp = {
        1: [Delta(1, "same nav fragment", 0.1)] * 20,
        2: [Delta(2, f"Constructor fact {i}", i / 10) for i in range(20)],
        3: [Delta(3, f"Elastic fact {i}", i / 10) for i in range(10)],
        4: [Delta(4, "should not be reached", 0.9)] * 8,
    }
    facts = [Fact(2, f"Constructor fact {i}", i / 10) for i in range(40)]
    facts += [Fact(3, f"Elastic fact {i}", i / 10) for i in range(40)]

    targets = daily_run.select_synthesis_targets(
        deltas_by_comp,
        facts,
        {1: "Noisy", 2: "Constructor", 3: "Elastic", 4: "Overflow"},
        max_competitors=2,
        max_deltas_per_competitor=5,
        max_facts_per_competitor=6,
    )

    assert [name for _, name, _, _ in targets] == ["Noisy", "Constructor"]
    assert len(targets[0][2]) == 1
    assert len(targets[1][2]) == 5
    assert len(targets[1][3]) == 6


def test_thesis_update_text_is_deterministic_and_competitor_specific(daily_run):
    text = daily_run.thesis_update_text({
        "competitor_name": "Constructor",
        "signal_type": "product narrative",
        "headline": "Constructor pushes agentic commerce search.",
    })

    assert text == "Constructor shows a product narrative pattern: Constructor pushes agentic commerce search."


def test_decide_synthesis_verdict_treats_all_target_errors_as_coverage_failure(daily_run):
    verdict = daily_run.decide_synthesis_verdict(
        promoted_count=0,
        verdicts_seen=[],
        synthesis_target_count=1,
        synthesis_error_count=1,
        coverage_all_ran=True,
    )

    assert verdict == "coverage_failure"


def test_decide_synthesis_verdict_allows_true_quiet_when_model_returns_quiet(daily_run):
    verdict = daily_run.decide_synthesis_verdict(
        promoted_count=0,
        verdicts_seen=[daily_run.Verdict.QUIET],
        synthesis_target_count=1,
        synthesis_error_count=0,
        coverage_all_ran=True,
    )

    assert verdict == "quiet"


def test_build_daily_message_starts_with_marker(daily_run):
    message = daily_run.build_daily_message("some brief body")
    assert message.startswith("ARGUS — Daily Competitive Brief")
    assert "some brief body" in message


def test_is_weekly_due_true_on_sunday(daily_run):
    # 2026-07-12 is a Sunday.
    sunday = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_weekly_due(sunday) is True


def test_is_weekly_due_false_on_non_sunday(daily_run):
    # 2026-07-13 is a Monday.
    monday = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_weekly_due(monday) is False


def test_is_monthly_due_true_on_first_monday(daily_run):
    # 2026-08-03 is the first Monday of August 2026.
    first_monday = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_monthly_due(first_monday) is True


def test_is_monthly_due_false_on_other_monday(daily_run):
    # 2026-08-10 is a Monday but not the first Monday of the month.
    other_monday = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_monthly_due(other_monday) is False


@pytest.mark.asyncio
async def test_run_weekly_if_due_is_disabled_by_default_even_on_sunday(daily_run, monkeypatch):
    monkeypatch.delenv("CIOS_ENABLE_WEEKLY_ROLLUP", raising=False)
    sunday = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)

    await daily_run.run_weekly_if_due(object(), 1, "algolia", object(), object(), sunday)


@pytest.mark.asyncio
async def test_run_monthly_if_due_is_disabled_by_default_even_on_first_monday(daily_run, monkeypatch):
    monkeypatch.delenv("CIOS_ENABLE_MONTHLY_ROLLUP", raising=False)
    first_monday = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)

    await daily_run.run_monthly_if_due(object(), 1, "algolia", object(), object(), first_monday)


def test_select_adapter_for_tenant_capturing_for_non_delivered(daily_run):
    telegram_env = {"TELEGRAM_BOT_TOKEN": "tok", "CIOS_TELEGRAM_CHAT_ID": "chat"}
    adapter = daily_run.select_adapter_for_tenant("spryker", "algolia", telegram_env)
    assert isinstance(adapter, daily_run.CapturingTelegramAdapter)


def test_select_adapter_for_tenant_real_for_delivered(daily_run):
    telegram_env = {"TELEGRAM_BOT_TOKEN": "tok-123", "CIOS_TELEGRAM_CHAT_ID": "chat-456"}
    adapter = daily_run.select_adapter_for_tenant("algolia", "algolia", telegram_env)
    assert isinstance(adapter, daily_run.TelegramAdapter)
    assert not isinstance(adapter, daily_run.CapturingTelegramAdapter)
    assert adapter.bot_token == "tok-123"
    assert adapter.default_chat_id == "chat-456"


def test_llm_budget_raised_to_35(daily_run):
    assert daily_run.LLM_BUDGET == 35


def _prescription(
    title: str = "Counter-position the price cut",
    urgency: UrgencyWindow = UrgencyWindow.ACT_NOW,
    team: Team = Team.MARKETING,
) -> Prescription:
    return Prescription(
        tenant_id=1,
        title=title,
        play=["Brief the field by EOD", "Publish a comparison one-pager"],
        team=team,
        urgency_window=urgency,
        grounding=Grounding(
            signal_evidence_urls=["https://rival.com/pricing"],
            evidence_urls=["https://rival.com/pricing"],
        ),
        expected_effect="Neutralizes the price objection before it spreads.",
        effort=Effort.M,
        materiality_score=0.8,
    )


class _StubPrescriptionEngine:
    """No-live-LLM stand-in for cios.prescribe.engine.PrescriptionEngine,
    matching its async .prescribe(...) signature."""

    def __init__(self, prescriptions: list[Prescription]) -> None:
        self._prescriptions = prescriptions

    async def prescribe(self, tenant_id, signals, connections=None, theses=None, brand_position=None):
        return self._prescriptions


# -- "YOUR PLAYS" brief section (via a fake/stub PrescriptionEngine) --------


@pytest.mark.asyncio
async def test_stub_prescription_engine_feeds_your_plays_section():
    stub = _StubPrescriptionEngine([_prescription()])
    prescriptions = await stub.prescribe(tenant_id=1, signals=[])
    from datetime import date as _date

    md = compose_daily_brief([], "Acme Corp", _date(2026, 7, 8), prescriptions=prescriptions)
    assert "## YOUR PLAYS" in md
    assert "Counter-position the price cut" in md
    assert "Brief the field by EOD" in md


# -- brief.py prescription rendering (unit test the render function) -------


def test_format_your_plays_renders_title_steps_team_urgency(daily_run):
    from cios.brain.brief import _format_your_plays

    lines = _format_your_plays([_prescription()])
    text = "\n".join(lines)
    assert "## YOUR PLAYS" in text
    assert "Counter-position the price cut" in text
    assert "Marketing" in text
    assert "act now" in text
    assert "Brief the field by EOD" in text
    assert "Expected effect: Neutralizes the price objection before it spreads." in text


def test_format_your_plays_sorts_act_now_first(daily_run):
    from cios.brain.brief import _format_your_plays

    later = _prescription(title="This-month play", urgency=UrgencyWindow.THIS_MONTH)
    now_play = _prescription(title="Act-now play", urgency=UrgencyWindow.ACT_NOW)
    text = "\n".join(_format_your_plays([later, now_play]))
    assert text.index("Act-now play") < text.index("This-month play")


def test_format_your_plays_empty_when_no_prescriptions(daily_run):
    from cios.brain.brief import _format_your_plays

    assert _format_your_plays([]) == []
    assert _format_your_plays(None) == []


# -- action_items mapping from a Prescription -------------------------------


def test_prescription_to_action_item_maps_evidence_and_team(daily_run):
    p = _prescription()
    row = daily_run.prescription_to_action_item(p, report_id=99)
    assert row["tenant_id"] == 1
    assert row["owner"] == "Marketing"
    assert "Counter-position the price cut" in row["recommendation"]
    assert "Brief the field by EOD" in row["recommendation"]
    assert row["evidence_ids"] == ["https://rival.com/pricing"]
    assert row["priority"] == "act_now"
    assert row["due_window"] == "act_now"
    assert row["report_id"] == 99
    # action_items schema CHECK: evidence_ids must be non-empty.
    assert len(row["evidence_ids"]) > 0


def test_prescription_to_action_item_no_report_id_is_none(daily_run):
    row = daily_run.prescription_to_action_item(_prescription())
    assert row["report_id"] is None
