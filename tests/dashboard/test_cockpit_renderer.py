from __future__ import annotations

from datetime import date, datetime, timezone

from cios.dashboard.cockpit_renderer import render_cockpit_html
from cios.dashboard.types import (
    ArgusEvidenceNeedSummary,
    ArgusRecommendationSummary,
    ArgusRecommendationScorecard,
    ArgusRubricDimension,
    AttentionLevel,
    CompetitorSignalCard,
    DashboardState,
    DashboardOperatorCommand,
    DashboardOperatorHandoff,
    DemandFeatureAlignmentCompany,
    DemandFeatureAlignmentRow,
    DemandFeatureAlignmentState,
    DemandSignalSummary,
    FeatureMatrixRow,
    IntelligencePlaneSummary,
    IntelligenceSpine,
    LivingThesis,
    MarketFieldAction,
    MarketFieldHotspot,
    MarketFieldNode,
    MarketFieldProofItem,
    MarketFieldState,
    MonitoredCompetitor,
    PrescriptionSummary,
    ProductFeatureComparisonCell,
    ProductFeatureComparisonCompany,
    ProductFeatureComparisonRow,
    ProductFeatureComparisonState,
    ProductMarketHeatmapCell,
    ProductMarketHistoryEntry,
    ProductMarketEntityVelocitySummary,
    ProductMarketPatternSummary,
    ProductMarketRunHistoryEntry,
    ProductMarketThemeHeatmapCell,
    ProductMarketTrendSummary,
    ProductMarketWindowDeltaSummary,
    RunHealth,
    SourceHealthEntry,
)


def _card(**overrides) -> CompetitorSignalCard:
    base = dict(
        competitor_id=5,
        competitor_name="Constructor",
        attention_score=88.0,
        attention_level=AttentionLevel.ACT_NOW,
        action_cue="Watch Constructor's AI shopping agent narrative.",
        top_signal_headline="Constructor pushes AI shopping agents.",
        what_changed="Constructor is staking a claim in conversational product discovery.",
        why_it_matters="This competes directly with AI-powered site search positioning.",
        recommended_action="Brief PMM and sales on the AI shopping agent narrative.",
        evidence_ids=["https://constructor.com/product"],
        delta_id=387,
        brief_href="./briefs/algolia/constructor-2026-07-10.html",
    )
    base.update(overrides)
    return CompetitorSignalCard(**base)


def test_renders_new_intelligence_brief_shell() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()]))

    assert "<!doctype html>" in html.lower()
    assert "Argus Competitive Intelligence Cockpit" in html
    assert "Today’s competitive brief" in html
    assert "What happened" in html
    assert "Why it matters" in html
    assert "Recommended action" in html
    assert "Priority moves" in html
    assert "Selected competitor" in html
    assert "Role implications" in html
    assert "Evidence and source health" in html


def test_renders_market_field_first_experience() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        market_field=MarketFieldState(
            selected_hotspot_id="ai-commerce",
            nodes=[
                MarketFieldNode(node_id="ai-commerce", label="AI commerce ownership", node_type="theme"),
                MarketFieldNode(node_id="constructor", label="Constructor", node_type="competitor"),
                MarketFieldNode(
                    node_id="unknown-ai-agent",
                    label="Unknown boundary",
                    node_type="unknown_boundary",
                    status="confidence_limit",
                    summary="Unknown is not absence.",
                ),
            ],
            hotspots=[
                MarketFieldHotspot(
                    hotspot_id="ai-commerce",
                    label="AI commerce ownership",
                    argus_read="AI commerce ownership is becoming the active competitive frame.",
                    movement="rising",
                    confidence_label="medium-high",
                    proof_status="partial",
                    unknowns=["Unknown is not absence."],
                )
            ],
            actions=[
                MarketFieldAction(
                    owner="PMM",
                    priority="P1",
                    action="Sharpen AI commerce positioning.",
                    why_now="Competitor narrative is moving faster than Algolia's visible story.",
                    confidence_label="medium-high",
                )
            ],
            proof=[
                MarketFieldProofItem(
                    plane="audience_demand",
                    summary="Audience demand overlaps the selected movement.",
                    source_count=3,
                )
            ],
        ),
    )

    html = render_cockpit_html(state)

    assert 'id="market-field"' in html
    assert 'id="selected-movement"' in html
    assert 'id="action-layer"' in html
    assert 'id="proof-drawer"' in html
    assert 'id="evidence-lab"' in html
    assert 'id="admin"' in html
    assert "Where the market is concentrating" in html
    assert "AI commerce ownership" in html
    assert "Sharpen AI commerce positioning." in html
    assert "Unknown is not absence." in html
    assert "confirmed absence" not in html.lower()


def test_market_field_renders_3d_runtime_shell_from_vendored_contract() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        market_field=MarketFieldState(
            selected_hotspot_id="agent-studio",
            nodes=[
                MarketFieldNode(node_id="agent-studio", label="Agent Studio", node_type="theme"),
                MarketFieldNode(node_id="google-vertex-ai-search", label="Google Vertex AI Search", node_type="competitor"),
                MarketFieldNode(node_id="audience-demand", label="Audience Demand", node_type="audience_demand"),
            ],
            hotspots=[
                MarketFieldHotspot(
                    hotspot_id="agent-studio",
                    label="Agent Studio",
                    argus_read="Agent Studio has product proof and a closing demand window.",
                    movement="rising",
                    confidence_label="medium-high",
                    proof_status="partial",
                    connected_node_ids=["agent-studio", "google-vertex-ai-search", "audience-demand"],
                )
            ],
            actions=[
                MarketFieldAction(
                    owner="Product Marketing",
                    priority="P1",
                    action="Turn Agent Studio into an evidence-backed market narrative.",
                    why_now="The demand window is cooling.",
                    confidence_label="medium-high",
                )
            ],
            proof=[
                MarketFieldProofItem(
                    plane="product_reality",
                    summary="Agent Studio shipped and has public product proof.",
                    source_count=4,
                )
            ],
        ),
    )

    html = render_cockpit_html(state)

    assert 'id="market-field-3d"' in html
    assert 'data-market-field-3d' in html
    assert 'data-three-runtime-version="0.160.0"' in html
    assert 'data-three-runtime="src/cios/dashboard/static/vendor/three/0.160.0/three.module.min.js"' in html
    assert 'id="market-field-state"' in html
    assert '"nodes":' in html
    assert '"edges":' in html
    assert '"hotspots":' in html
    assert "Agent Studio has product proof and a closing demand window." in html
    assert "https://unpkg.com" not in html
    assert "https://cdn.jsdelivr.net" not in html
    assert "https://esm.sh" not in html
    assert "<script src=" not in html


def test_quiet_current_run_does_not_label_rolling_cards_as_todays_moves() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        run_health=RunHealth(material_delta_count=0, rolling_material_delta_count=2, quality_review_status="passed"),
        competitor_cards=[
            _card(competitor_id=5, competitor_name="Constructor"),
            _card(competitor_id=6, competitor_name="Elastic"),
        ],
    )

    html = render_cockpit_html(state)

    assert "No new material moves were promoted today." in html
    assert "Quiet new-signal day" in html
    assert "0 promoted moves" in html
    assert "2 recent material cards" in html
    assert "Argus promoted 2 current material moves" not in html
    assert "Act on the top signal" not in html


def test_cockpit_renders_intelligence_spine_as_argus_proof_chain() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        intelligence_spine=IntelligenceSpine(
            verdict="watch",
            top_insight="Constructor moved first, but demand proof is missing.",
            confidence_limits=["Recommendation withheld until demand evidence is uploaded."],
            planes=[
                IntelligencePlaneSummary(
                    plane="product_reality",
                    label="Product reality",
                    status="present",
                    signal_count=4,
                    evidence_count=3,
                    summary="Scout saw shipped product proof.",
                ),
                IntelligencePlaneSummary(
                    plane="market_conversation",
                    label="Market conversation",
                    status="present",
                    signal_count=3,
                    evidence_count=2,
                    summary="Competitor positioning is visible.",
                ),
                IntelligencePlaneSummary(
                    plane="audience_demand",
                    label="Audience demand",
                    status="missing",
                    signal_count=0,
                    evidence_count=0,
                    summary="Upload GA4 / Looker export before promoting action.",
                ),
            ],
            pattern_count=3,
            recommendation_count=0,
            evidence_need_count=1,
            leading_entities=["Constructor", "Elastic"],
            leading_capabilities=["agentic product discovery"],
            blocked_actions=["owner recommendations"],
            can_recommend=False,
            next_operator_action="Upload GA4 / Looker demand export for the current and previous periods.",
        ),
    )

    html = render_cockpit_html(state)

    assert 'id="intelligence-spine"' in html
    assert "How Argus earned this read" in html
    assert "Constructor moved first, but demand proof is missing." in html
    assert "Product reality" in html
    assert "Scout saw shipped product proof." in html
    assert "Audience demand" in html
    assert "Upload GA4 / Looker export before promoting action." in html
    assert "Blocked action: owner recommendations" in html
    assert "Next operator action" in html
    assert "Upload GA4 / Looker demand export for the current and previous periods." in html


def test_cockpit_renders_argus_operator_handoff_as_public_actionability_contract() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        intelligence_spine=IntelligenceSpine(
            verdict="watch",
            top_insight="Constructor moved first, but demand proof is missing.",
            can_recommend=False,
            next_operator_action="Upload GA4 / Looker demand export for the current and previous periods.",
        ),
        operator_handoff=DashboardOperatorHandoff(
            tenant_slug="algolia",
            tenant_id=1,
            generated_at="2026-07-11T20:02:00Z",
            status="blocked_on_evidence",
            argus_readiness="not_actionable",
            summary="Argus is blocked by 1 evidence gap before it can promote this run to action.",
            next_operator_action="Upload GA4 / Looker demand export for the current and previous periods.",
            top_blocker={
                "work_item_id": "argus-evidence:17:demand",
                "evidence_plane": "demand",
                "severity": "blocks_action",
                "title": "Demand plane missing",
                "why_needed": "Demand evidence is missing, so Argus withheld owner recommendations.",
                "blocks": ["owner recommendations", "priority ranking"],
            },
            primary_command=DashboardOperatorCommand(
                label="Download demand template",
                href="/api/tenants/algolia/argus/demand-imports/template",
                method="get",
                surface="Demand imports",
            ),
            operator_commands=[
                {
                    "label": "Download demand template",
                    "method": "get",
                    "surface": "Demand imports",
                    "route_kind": "api",
                },
                {
                    "label": "Open demand admin",
                    "method": "get",
                    "surface": "Admin",
                    "route_kind": "admin",
                },
                {
                    "label": "Run GA4 export now",
                    "method": "post",
                    "surface": "GA4 connector",
                    "route_kind": "admin",
                },
            ],
            demand_collection_plan={
                "status": "needs_demand_source",
                "topic_count": 2,
                "topics": [
                    {
                        "topic": "Shopping Assistant",
                        "related_competitors": ["Constructor"],
                        "evidence_url_count": 3,
                    },
                    {
                        "topic": "AI Assistant",
                        "related_competitors": ["Elastic"],
                        "evidence_url_count": 2,
                    },
                ],
            },
            demand_plan_template={
                "status": "generated",
                "format": "csv",
                "filename": "argus-demand-plan-template.csv",
            },
            operator_brief=[
                "Argus withheld action because Demand plane missing is open on the demand plane.",
                "Next step: Upload GA4 / Looker demand export for the current and previous periods.",
            ],
            work_queue={
                "work_item_count": 1,
                "blocking_count": 1,
                "limiting_count": 0,
                "item_ids": ["argus-evidence:17:demand"],
            },
            artifact_found=True,
        ),
    )

    html = render_cockpit_html(state)

    assert "Argus operator handoff" in html
    assert "blocked_on_evidence" in html
    assert "not_actionable" in html
    assert "Argus is blocked by 1 evidence gap before it can promote this run to action." in html
    assert "Demand plane missing" in html
    assert "owner recommendations" in html
    assert "Upload GA4 / Looker demand export for the current and previous periods." in html
    assert "Download demand template" in html
    assert "Open demand admin" in html
    assert "Run GA4 export now" in html
    assert "Demand imports" in html
    assert "GA4 connector" in html
    assert "Demand work order" in html
    assert "2 topics to collect" in html
    assert "Shopping Assistant" in html
    assert "Constructor" in html
    assert "3 evidence refs" in html
    assert "AI Assistant" in html
    assert "Elastic" in html
    assert "argus-demand-plan-template.csv" in html
    assert "/api/tenants/algolia/argus/demand-imports/template" not in html
    assert "/admin?tenant=algolia#inward-demand" not in html
    assert "/admin/algolia/argus/ga4-export" not in html


def test_preserves_argus_brand_mark_and_editorial_design_assets() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()]))

    assert 'class="argus-mark"' in html
    assert 'src="data:image/png;base64,' in html
    assert 'alt="Argus"' in html
    assert '<strong>Argus</strong>' in html
    assert '<strong>Argus CI-OS</strong>' not in html
    assert 'class="editorial-image"' in html
    assert 'src="data:image/jpeg;base64,' in html


def test_navigation_has_state_contract_and_distinct_section_targets() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()]))

    assert 'data-nav-link="today-read"' in html
    assert 'data-nav-link="intelligence-spine"' in html
    assert 'data-nav-link="market-timeline"' in html
    assert 'data-nav-link="semantic-layer"' in html
    assert 'data-nav-link="priority-moves"' in html
    assert 'data-nav-link="role-implications"' in html
    assert 'data-nav-link="evidence-coverage"' in html
    assert 'href="#today-read" data-nav-link="today-read" aria-current="page"' in html
    assert 'href="#intelligence-spine" data-nav-link="intelligence-spine"' in html
    assert 'href="#market-timeline" data-nav-link="market-timeline"' in html
    assert 'href="#semantic-layer" data-nav-link="semantic-layer"' in html
    assert 'href="#priority-moves" data-nav-link="priority-moves"' in html
    assert 'href="#role-implications" data-nav-link="role-implications"' in html
    assert 'href="#evidence-coverage" data-nav-link="evidence-coverage"' in html


def test_evidence_appendix_is_open_so_anchor_has_real_destination() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()]))

    assert html.count('<details class="appendix" open>') == 2


def test_information_order_is_read_then_priority_then_roles_then_evidence() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()]))

    today = html.index('id="today-read"')
    spine = html.index('id="intelligence-spine"')
    timeline = html.index('id="market-timeline"')
    priority = html.index('id="priority-moves"')
    selected = html.index('id="selected-competitor"')
    roles = html.index('id="role-implications"')
    evidence = html.index('id="evidence-coverage"')

    assert today < spine < timeline < priority < selected < roles < evidence


def test_priority_moves_group_competitors_and_preserve_top_rank() -> None:
    cards = [
        _card(competitor_id=6, competitor_name="Elastic", attention_score=92.0, delta_id=1),
        _card(competitor_id=5, competitor_name="Constructor", attention_score=80.0, delta_id=2),
        _card(competitor_id=6, competitor_name="Elastic", attention_score=40.0, delta_id=3),
    ]
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=cards))

    assert html.count('data-select-competitor="6"') == 1
    assert html.count('data-select-competitor="5"') == 1
    assert html.index('data-select-competitor="6"') < html.index('data-select-competitor="5"')
    assert "Elastic" in html
    assert "Constructor" in html


def test_selected_competitor_panel_contains_action_evidence_and_brief_link() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()]))

    assert 'data-competitor-panel="5"' in html
    assert "Constructor is staking a claim in conversational product discovery." in html
    assert "This competes directly with AI-powered site search positioning." in html
    assert "Brief PMM and sales on the AI shopping agent narrative." in html
    assert "https://constructor.com/product" in html
    assert "./briefs/algolia/constructor-2026-07-10.html" in html


def test_role_implications_update_by_competitor_contract() -> None:
    html = render_cockpit_html(
        DashboardState(
            tenant_id=1,
            cadence="daily",
            competitor_cards=[
                _card(competitor_id=5, competitor_name="Constructor", delta_id=1),
                _card(
                    competitor_id=6,
                    competitor_name="Elastic",
                    attention_score=72.0,
                    attention_level=AttentionLevel.WATCH,
                    delta_id=2,
                    action_cue="Watch Elastic's context engineering narrative.",
                    what_changed="Elastic is pushing context engineering for agents.",
                    why_it_matters="This reframes search infrastructure as agent infrastructure.",
                    recommended_action="Review Elastic's docs and battlecard implications.",
                    brief_href="./briefs/algolia/elastic-2026-07-10.html",
                ),
            ],
        )
    )

    assert 'data-role-set="5"' in html
    assert 'data-role-set="6"' in html
    assert "Marketing read for Constructor" in html
    assert "Sales read for Constructor" in html
    assert "Product read for Constructor" in html
    assert "Marketing read for Elastic" in html
    assert "Sales read for Elastic" in html
    assert "Product read for Elastic" in html


def test_quiet_state_is_explicit_not_empty_wall() -> None:
    html = render_cockpit_html(DashboardState(tenant_id=1, cadence="daily"))

    assert "No new competitor move crossed the action threshold in this run." in html
    assert "No priority moves were promoted in this run." in html
    assert "No current move crossed the action threshold." in html


def test_coverage_and_source_failures_are_appendix_material() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        monitored_competitors=[
            MonitoredCompetitor(
                competitor_id=5,
                competitor_name="Constructor",
                checked_today=True,
                active_source_count=4,
                failed_source_count=0,
                material_signal_count=3,
            ),
            MonitoredCompetitor(
                competitor_id=6,
                competitor_name="Coveo",
                checked_today=True,
                active_source_count=6,
                failed_source_count=5,
            ),
        ],
        source_health=[
            SourceHealthEntry(
                source_id=1,
                competitor_id=6,
                competitor_name="Coveo",
                source_family="blog",
                url="https://www.coveo.com/en/blog",
                status="active",
                latest_event_type="fetch_error",
                http_status=202,
                detail="empty",
            )
        ],
    )
    html = render_cockpit_html(state)

    assert "<summary><h2>Market coverage</h2>" in html
    assert "<summary><h2>Evidence and source health</h2>" in html
    assert "Constructor" in html
    assert "Coveo" in html
    assert "fetch_error" in html
    assert "https://www.coveo.com/en/blog" in html


def test_generated_timestamp_is_visible() -> None:
    state = DashboardState(tenant_id=1, cadence="daily", competitor_cards=[_card()])
    html = render_cockpit_html(state)
    stamp = state.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    assert f"Generated {stamp}" in html


def test_report_history_fallback_brief_link_when_no_competitor_href() -> None:
    card = _card(brief_href=None)
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        competitor_cards=[card],
        report_history=[{
            "report_id": 1,
            "report_date": date.today().isoformat(),
            "cadence": "daily",
            "title": "Argus daily brief",
            "summary": "summary",
            "status": "rendered",
            "html_path": None,
        }],
    )
    html = render_cockpit_html(state)

    assert "./brief.html?v=" in html


def test_semantic_layer_surfaces_selector_heatmap_recommendation_and_rubric() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        run_health=RunHealth(quality_review_status="passed", source_family_count=5, material_delta_count=6),
        competitor_cards=[
            _card(
                competitor_id=5,
                competitor_name="Constructor",
                what_changed="Constructor is pushing AI shopping agents and conversational product discovery.",
                why_it_matters="Agentic commerce is becoming a buying narrative.",
                recommended_action="Own the AI shopping journey proof before Constructor frames it.",
                evidence_ids=["https://constructor.com/ai"],
            ),
            _card(
                competitor_id=6,
                competitor_name="Elastic",
                attention_score=71,
                attention_level=AttentionLevel.WATCH,
                what_changed="Elastic is pushing context engineering for agents and retrieval infrastructure.",
                why_it_matters="Search infrastructure is being reframed as agent infrastructure.",
                recommended_action="Update technical battlecards on context engineering.",
                evidence_ids=["https://elastic.co/context"],
            ),
        ],
        monitored_competitors=[
            MonitoredCompetitor(competitor_id=5, competitor_name="Constructor", active_source_count=4, checked_today=True, material_signal_count=2),
            MonitoredCompetitor(competitor_id=6, competitor_name="Elastic", active_source_count=3, checked_today=True, material_signal_count=1),
            MonitoredCompetitor(competitor_id=7, competitor_name="Coveo", active_source_count=6, failed_source_count=5, checked_today=True),
        ],
        prescriptions=[
            PrescriptionSummary(
                title="Write an AI shopping journey proof guide",
                team="Content",
                play=["Compare guided shopping outcomes by query type."],
                urgency_window="this_week",
                evidence_urls=["https://constructor.com/ai"],
                competitor_id=5,
                competitor_name="Constructor",
            )
        ],
        theses=[
            LivingThesis(
                thesis_id=1,
                competitor_id=6,
                competitor_name="Elastic",
                thesis="Elastic is moving search infrastructure into context engineering for agents.",
                status="active",
                confidence=0.6,
            )
        ],
        source_health=[
            SourceHealthEntry(source_id=1, competitor_id=5, competitor_name="Constructor", source_family="product", url="https://constructor.com/ai", status="active", latest_event_type="ok", http_status=200),
            SourceHealthEntry(source_id=2, competitor_id=6, competitor_name="Elastic", source_family="docs", url="https://elastic.co/context", status="active", latest_event_type="ok", http_status=200),
            SourceHealthEntry(source_id=3, competitor_id=7, competitor_name="Coveo", source_family="blog", url="https://coveo.com/blog", status="active", latest_event_type="fetch_error", http_status=202, detail="empty"),
        ],
    )

    html = render_cockpit_html(state)

    assert 'id="semantic-layer"' in html
    assert 'id="partner-selector"' in html
    assert '<option value="5">Constructor</option>' in html
    assert '<option value="7">Coveo</option>' in html
    assert 'data-heat-map' in html
    assert 'data-heat-cell' in html
    assert "Pattern across partners" in html
    assert "Where the market is heading" in html
    assert "Argus recommendation" in html
    assert "Confidence rubric" in html
    assert "Not scored" in html
    assert "No backend recommendation scorecard exists" in html
    assert "Agentic commerce" in html or "agentic commerce" in html


def test_semantic_layer_refuses_confidence_score_without_backend_scorecard() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_market_run={
            "status": "ran",
            "runner_verdict": "watch",
            "demand_plane_status": "missing",
            "product_event_count": 12,
            "conversation_theme_count": 9,
            "demand_signal_count": 0,
            "pattern_count": 2,
            "recommendation_count": 0,
        },
        intelligence_spine=IntelligenceSpine(
            verdict="watch",
            top_insight="Constructor has product and conversation movement, but demand is absent.",
            confidence_limits=["No tenant-side demand evidence was captured in this run."],
            planes=[
                IntelligencePlaneSummary(
                    plane="product_reality",
                    label="Product reality",
                    status="present",
                    signal_count=12,
                    evidence_count=12,
                    summary="Product proof exists.",
                ),
                IntelligencePlaneSummary(
                    plane="audience_demand",
                    label="Audience demand",
                    status="missing",
                    signal_count=0,
                    evidence_count=0,
                    summary="No tenant-side demand evidence was captured.",
                ),
            ],
            pattern_count=2,
            recommendation_count=0,
        ),
        monitored_competitors=[
            MonitoredCompetitor(competitor_id=5, competitor_name="Constructor", active_source_count=4, checked_today=True),
        ],
        product_market_patterns=[
            ProductMarketPatternSummary(
                pattern_id=91,
                pattern_type="competitive_pressure",
                capability_text="AI shopping agents",
                summary="Constructor has product proof and positioning, but demand is missing.",
                involved_companies=["Constructor"],
                confidence=0.58,
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
    )

    html = render_cockpit_html(state)

    assert 'data-confidence-score="not-scored"' in html
    assert "Not scored" in html
    assert "No backend recommendation scorecard exists" in html
    assert "No tenant-side demand evidence was captured in this run." in html
    assert "Materiality separation" not in html


def test_cockpit_renders_product_market_run_trace_in_trust_area() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_market_run={
            "status": "ran",
            "target_count": 2,
            "target_company_count": 2,
            "target_companies": ["Constructor", "Coveo"],
            "surface_family_counts": {"changelog": 1, "docs": 1},
            "product_muscle_gap_plan": {
                "monitored_company_count": 4,
                "covered_company_count": 2,
                "missing_company_count": 2,
                "candidate_url_count": 12,
                "candidate_surface_family_counts": {"docs": 2, "pricing": 2},
                "missing_companies": [
                    {"company_name": "Elastic", "candidate_surface_urls": []},
                    {"company_name": "Bloomreach", "candidate_surface_urls": []},
                ],
            },
            "post_run_product_muscle_gap_discovery": {
                "status": "completed",
                "stored_candidate_count": 6,
                "rejected_count": 1,
            },
            "post_run_product_surface_promotion": {
                "status": "completed",
                "promoted_count": 2,
            },
            "post_run_next_sweep_status": (
                "Hermes queued 6 candidate product surfaces and activated 2 validated sources "
                "for the next sweep."
            ),
            "learning_apply_plan_path": "/tmp/cios-product-market/algolia/learning-apply-plan.json",
            "learning_apply_plan_summary": {
                "action_count": 1,
                "skipped_count": 0,
                "targets": ["source_coverage_policy"],
                "package_paths": ["config/source-coverage-policy.yaml"],
            },
            "learning_prioritized_count": 1,
            "runner_verdict": "watch",
            "product_event_count": 4,
            "conversation_theme_count": 3,
            "demand_signal_count": 2,
            "pattern_count": 1,
            "recommendation_count": 0,
            "learning_instruction_count": 1,
            "consumed_learning_ids": [202],
            "scout_artifact_count": 1,
            "intelligence_brief": {
                "verdict": "watch",
                "top_insight": "Constructor moved first, but coverage learning demoted the action.",
                "primary_action": None,
                "watchlist": ["Re-audit Coveo before restoring Constructor priority."],
                "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                "confidence_limits": ["Recommendation withheld by approved coverage learning."],
                "next_questions": ["Did Coveo ship a competing capability in docs?"],
                "demand_read": {
                    "summary": (
                        "2 rising demand topics found; 1 matched product proof and 1 still needs product proof."
                    ),
                    "top_topics": [
                        {
                            "topic": "context engineering",
                            "metric": "engaged_sessions",
                            "value": 180,
                            "change_pct": 0.41,
                            "matched_product_proof": False,
                            "matched_market_conversation": False,
                            "missing_planes": ["product_proof", "market_conversation"],
                            "source_files": ["ga-pages.csv"],
                            "evidence_urls": ["https://lookerstudio.google.com/reporting/context"],
                        },
                        {
                            "topic": "agentic product discovery",
                            "metric": "engaged_sessions",
                            "value": 240,
                            "change_pct": 0.22,
                            "matched_product_proof": True,
                            "matched_market_conversation": True,
                            "missing_planes": [],
                            "source_files": ["ga-pages.csv"],
                            "evidence_urls": ["https://lookerstudio.google.com/reporting/agentic"],
                        },
                    ],
                },
                "movement_map": {
                    "direction_summary": "agentic product discovery is heating up across Constructor and Algolia.",
                    "hot_capabilities": ["agentic product discovery"],
                    "heat_cells": [
                        {
                            "company_name": "Constructor",
                            "capability": "agentic product discovery",
                            "heat_level": "hot",
                            "signal_count": 2,
                            "recent_count": 2,
                            "prior_count": 0,
                            "confidence": 0.78,
                            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                        }
                    ],
                    "entity_velocity": [
                        {
                            "company_name": "Constructor",
                            "heat_level": "hot",
                            "signal_count": 2,
                            "hot_capabilities": ["agentic product discovery"],
                            "summary": "Constructor has 2 movement signals, led by agentic product discovery.",
                            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                        }
                    ],
                    "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                    "confidence_limits": [
                        "Movement is derived from captured product-market pattern memory."
                    ],
                },
                "window_comparison": {
                    "summary": (
                        "Last 7 days: 2 product events, 1 conversation theme, 1 demand signal. "
                        "Last 30 days: 4 product events, 3 conversation themes, 2 demand signals."
                    ),
                    "windows": [
                        {
                            "days": 7,
                            "hot_capabilities": ["agentic product discovery"],
                            "leading_companies": ["Constructor", "Algolia"],
                        },
                        {
                            "days": 30,
                            "hot_capabilities": ["agentic product discovery", "vector merchandizing"],
                            "leading_companies": ["Constructor", "Bloomreach", "Algolia"],
                        },
                    ],
                },
            },
            "conversion_diagnostics": {
                "summary": (
                    "2 Scout/product records converted to 2 product events and 2 feature positions; "
                    "1 product-market pattern qualified."
                ),
                "blockers": [],
            },
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
        monitored_competitors=[
            {"competitor_id": 5, "competitor_name": "Constructor", "active_source_count": 4},
            {"competitor_id": 6, "competitor_name": "Coveo", "active_source_count": 6},
            {"competitor_id": 7, "competitor_name": "Elastic", "active_source_count": 3},
            {"competitor_id": 8, "competitor_name": "Bloomreach", "active_source_count": 4},
        ],
    )

    html = render_cockpit_html(state)

    assert "Hermes / Argus run trace" in html
    assert "Product-market chain" in html
    assert "ran" in html
    assert "2 product surfaces planned" in html
    assert "Product muscle coverage" in html
    assert "2 of 4 monitored entities" in html
    assert "Elastic, Bloomreach need product-surface coverage" in html
    assert "changelog: 1" in html
    assert "docs: 1" in html
    assert "Product surface discovery plan" in html
    assert "2 companies queued" in html
    assert "12 candidate URLs" in html
    assert "Post-run learning loop" in html
    assert "Hermes queued 6 candidate product surfaces" in html
    assert "activated 2 validated sources" in html
    assert "Learning apply plan" in html
    assert "1 package action" in html
    assert "source_coverage_policy" in html
    assert "config/source-coverage-policy.yaml" in html
    assert "1 learning-prioritized" in html
    assert "Ledger replay read" in html
    assert "4 product · 3 conversation · 2 demand · 1 pattern · 0 recommendations" in html
    assert "Coveo · docs" in html
    assert "coverage_recheck" in html
    assert "What Argus learned" in html
    assert "Constructor moved first" in html
    assert "Market movement" in html
    assert "agentic product discovery is heating up" in html
    assert "Evidence window" in html
    assert "Last 7 days: 2 product events" in html
    assert "7d: agentic product discovery" in html
    assert "30d: agentic product discovery, vector merchandizing" in html
    assert "Demand read" in html
    assert "2 rising demand topics found" in html
    assert "context engineering needs product proof, market conversation" in html
    assert "Recommendation withheld" in html


def test_cockpit_run_trace_renders_argus_decision_read() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_market_run={
            "status": "ran",
            "runner_verdict": "actionable",
            "product_event_count": 2,
            "conversation_theme_count": 1,
            "demand_signal_count": 1,
            "pattern_count": 1,
            "recommendation_count": 1,
            "intelligence_brief": {
                "top_insight": "Constructor is shipping and saying agentic product discovery.",
                "next_monitoring_actions": [
                    {
                        "owner": "Hermes",
                        "plane": "source_coverage",
                        "priority": "medium",
                        "instruction": (
                            "Recheck Constructor and Algolia source coverage for agentic product discovery."
                        ),
                        "reason": "Keep the promoted recommendation tied to fresh evidence.",
                        "source_families": ["scout_changelog", "web_scan", "ga4_api_export"],
                        "evidence_urls": [
                            "https://constructor.com/changelog/ai-shopping-agent",
                            "looker://algolia/ga4/topics",
                        ],
                    }
                ],
                "decision_read": {
                    "status": "actionable",
                    "market_direction": "agentic product discovery is heating up around Constructor and Algolia.",
                    "priority_reason": (
                        "Constructor is priority because product proof, public narrative, "
                        "and tenant-side demand evidence all align."
                    ),
                    "confidence_basis": [
                        {
                            "plane": "product_reality",
                            "status": "present",
                            "evidence_count": 2,
                            "summary": "2 product-reality event(s) captured.",
                        },
                        {
                            "plane": "market_conversation",
                            "status": "present",
                            "evidence_count": 1,
                            "summary": "1 market-conversation theme captured.",
                        },
                        {
                            "plane": "audience_demand",
                            "status": "present",
                            "evidence_count": 1,
                            "summary": "1 tenant-side demand signal captured.",
                        },
                    ],
                    "strategic_insights": [
                        {
                            "insight_type": "own_narrative_gap",
                            "summary": "Algolia has product proof but no matching narrative.",
                        }
                    ],
                    "tactical_actions": [
                        {
                            "owner": "PMM",
                            "action": "Create an evidence-backed agentic product discovery narrative.",
                            "why_now": "Competitor proof and audience demand align.",
                            "urgency": "this_week",
                            "score": 78,
                            "confidence": 0.78,
                        }
                    ],
                    "blockers": [],
                    "evidence_urls": [
                        "https://constructor.com/changelog/ai-shopping-agent",
                        "looker://algolia/ga4/topics",
                    ],
                },
            },
        },
    )

    html = render_cockpit_html(state)

    assert "Argus decision read" in html
    assert "actionable · agentic product discovery is heating up" in html
    assert "Constructor is priority because" in html
    assert "Decision confidence" in html
    assert "product reality present (2)" in html
    assert "market conversation present (1)" in html
    assert "audience demand present (1)" in html
    assert "Decision action" in html
    assert "PMM · Create an evidence-backed agentic product discovery narrative. · score 78" in html
    assert "Hermes next monitor" in html
    assert "source coverage · medium · Recheck Constructor and Algolia source coverage" in html
    assert "Decision blocker" not in html


def test_cockpit_run_trace_shows_missing_demand_plane_as_operator_blocker() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_market_run={
            "status": "ran",
            "runner_verdict": "watch",
            "target_count": 4,
            "scout_artifact_count": 2,
            "demand_plane_status": "missing",
            "looker_discovered_count": 0,
            "looker_ready_count": 0,
            "looker_normalized_row_count": 0,
            "demand_readiness": {
                "status": "blocked_missing_configuration",
                "summary": (
                    "GA4 export is enabled but missing required configuration; no usable manual export is queued."
                ),
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "manual_import": {"inbox_file_count": 0, "ready_preview_count": 0},
                "ga4_connector": {"enabled": True, "ready": False},
            },
            "intelligence_brief": {
                "top_insight": (
                    "Constructor has outward evidence, but no Algolia-side demand proof was captured."
                ),
                "confidence_limits": ["No tenant-side demand evidence was captured in this run."],
            },
            "conversion_diagnostics": {
                "summary": (
                    "2 Scout/product records converted to 2 product events and 2 feature positions; "
                    "1 product-market pattern qualified."
                ),
                "blockers": ["No tenant-side demand evidence was captured."],
            },
        },
    )

    html = render_cockpit_html(state)

    assert "Inward demand: missing" in html
    assert "Demand readiness" in html
    assert "blocked_missing_configuration" in html
    assert "configure_ga4_or_upload_demand_export" in html
    assert "0 demand rows" in html
    assert "Upload GA / Looker export before promoting recommendations." in html
    assert "Conversion diagnostics" in html
    assert "2 Scout/product records converted to 2 product events" in html


def test_cockpit_run_trace_distinguishes_duplicate_rechecks_from_new_candidate_queue() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_market_run={
            "status": "ran",
            "target_count": 38,
            "scout_artifact_count": 35,
            "post_run_product_muscle_gap_discovery": {
                "status": "completed",
                "candidate_url_count": 46,
                "stored_candidate_count": 0,
                "rejected_count": 46,
                "duplicate_source_count": 46,
                "new_candidate_rejected_count": 0,
            },
            "post_run_next_sweep_status": (
                "Hermes rechecked 46 already-monitored product surfaces; no new sweepable sources "
                "were added for the next sweep."
            ),
        },
    )

    html = render_cockpit_html(state)

    assert "Post-run learning loop" in html
    assert "rechecked 46 already-monitored product surfaces" in html
    assert "46 candidate product surfaces queued" not in html


def test_semantic_layer_uses_product_market_intelligence_state_before_keyword_heuristics() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        monitored_competitors=[
            MonitoredCompetitor(competitor_id=5, competitor_name="Constructor", active_source_count=4, checked_today=True),
            MonitoredCompetitor(competitor_id=1, competitor_name="Algolia", active_source_count=3, checked_today=True),
        ],
        product_market_patterns=[
            ProductMarketPatternSummary(
                pattern_id=91,
                pattern_type="own_narrative_gap",
                capability_text="agentic product discovery",
                summary=(
                    "Constructor is shipping and saying agentic product discovery while "
                    "Algolia has product proof but no matching narrative."
                ),
                involved_companies=["Algolia", "Constructor"],
                confidence=0.78,
                evidence_refs=[
                    {"source_url": "https://constructor.example/changelog"},
                    {"source_url": "https://www.algolia.com/changelog/agentic-discovery"},
                ],
            )
        ],
        argus_recommendations=[
            ArgusRecommendationSummary(
                recommendation_id=7,
                pattern_observation_id=91,
                owner="PMM",
                action="Create an evidence-backed agentic product discovery narrative.",
                why_now="Competitor release proof, public narrative, and demand are aligned.",
                urgency="this_week",
                confidence=0.78,
                scorecard=ArgusRecommendationScorecard(
                    total_score=78,
                    verdict="actionable",
                    summary="Competitor product proof, public narrative, and demand all align.",
                    dimension_scores=[
                        ArgusRubricDimension(
                            dimension="product_reality",
                            score=20,
                            max_score=25,
                            rationale="Constructor has release evidence.",
                            evidence_urls=["https://constructor.example/changelog"],
                        ),
                        ArgusRubricDimension(
                            dimension="market_conversation",
                            score=18,
                            max_score=20,
                            rationale="Constructor is publicly positioning the theme.",
                            evidence_urls=["https://constructor.example/blog"],
                        ),
                        ArgusRubricDimension(
                            dimension="audience_demand",
                            score=20,
                            max_score=20,
                            rationale="Algolia audience demand is rising.",
                            evidence_urls=["looker://algolia/ga4/topics"],
                        ),
                        ArgusRubricDimension(
                            dimension="own_response_gap",
                            score=10,
                            max_score=15,
                            rationale="Algolia has product proof but no matching narrative.",
                            evidence_urls=["https://www.algolia.com/changelog/agentic-discovery"],
                        ),
                        ArgusRubricDimension(
                            dimension="evidence_breadth",
                            score=10,
                            max_score=20,
                            rationale="Four distinct evidence refs support the recommendation.",
                            evidence_urls=[
                                "https://constructor.example/changelog",
                                "https://constructor.example/blog",
                                "looker://algolia/ga4/topics",
                                "https://www.algolia.com/changelog/agentic-discovery",
                            ],
                        ),
                    ],
                ),
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        demand_signals=[
            DemandSignalSummary(
                demand_signal_id=3,
                topic="agentic product discovery",
                metric="engaged_sessions",
                value=1234,
                change_pct=0.23,
                source_label="Looker Studio GA4 export",
                evidence_refs=[{"source_url": "looker://algolia/ga4/topics"}],
                argus_plan_context={
                    "assessment": "own_product_gap",
                    "related_competitors": ["Constructor", "Elastic"],
                    "why_collect": "Validate demand behind the AI Assistant gap.",
                },
            )
        ],
        feature_matrix=[
            FeatureMatrixRow(
                capability_text="agentic product discovery",
                company_name="Algolia",
                company_role="own",
                position_status="has_proof",
                summary="Algolia has release evidence.",
                confidence=0.7,
                evidence_refs=[{"source_url": "https://www.algolia.com/changelog/agentic-discovery"}],
            )
        ],
    )

    html = render_cockpit_html(state)

    assert "agentic product discovery" in html
    assert "Constructor is shipping and saying" in html
    assert "Create an evidence-backed agentic product discovery narrative." in html
    assert "Product reality" in html
    assert "20/25" in html
    assert "Constructor has release evidence." in html
    assert "Looker Studio GA4 export" in html
    assert "own_product_gap" in html
    assert "Constructor, Elastic" in html
    assert "Validate demand behind the AI Assistant gap." in html
    assert "Algolia has release evidence." in html


def test_semantic_layer_renders_cross_company_product_feature_comparison() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_feature_comparison=ProductFeatureComparisonState(
            companies=[
                ProductFeatureComparisonCompany(
                    company_name="Algolia",
                    company_role="own",
                    active_source_count=2,
                    has_product_evidence=True,
                ),
                ProductFeatureComparisonCompany(
                    company_name="Constructor",
                    company_role="competitor",
                    active_source_count=4,
                    has_product_evidence=True,
                ),
                ProductFeatureComparisonCompany(
                    company_name="Bloomreach",
                    company_role="competitor",
                    active_source_count=4,
                    has_product_evidence=False,
                ),
            ],
            rows=[
                ProductFeatureComparisonRow(
                    capability_text="AI Shopping Agent",
                    cells=[
                        ProductFeatureComparisonCell(
                            company_name="Algolia",
                            position_status="proven",
                            summary="Algolia has AI shopping proof.",
                            confidence=0.82,
                            evidence_count=1,
                            first_evidence_url="https://www.algolia.com/doc/ai-shopping",
                        ),
                        ProductFeatureComparisonCell(
                            company_name="Constructor",
                            position_status="proven",
                            summary="Constructor positions an AI Shopping Agent.",
                            confidence=0.76,
                            evidence_count=1,
                            first_evidence_url="https://constructor.com/products/ai-shopping-agent",
                        ),
                        ProductFeatureComparisonCell(
                            company_name="Bloomreach",
                            position_status="unknown",
                            summary=(
                                "No product proof captured for Bloomreach on AI Shopping Agent "
                                "in this evidence set."
                            ),
                            evidence_count=0,
                        ),
                    ],
                    proven_count=2,
                    claimed_count=0,
                    unknown_count=1,
                    evidence_count=2,
                )
            ],
            row_count_total=1,
            company_count_total=3,
        ),
    )

    html = render_cockpit_html(state)

    assert "Product feature comparison" in html
    assert "AI Shopping Agent" in html
    assert "Algolia" in html
    assert "Constructor" in html
    assert "Bloomreach" in html
    assert "proven" in html
    assert "unknown" in html
    assert "No product proof captured for Bloomreach" in html
    assert "https://constructor.com/products/ai-shopping-agent" in html


def test_run_trace_renders_argus_product_feature_comparison_read() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        product_market_run={
            "status": "ran",
            "runner_verdict": "watch",
            "product_event_count": 2,
            "conversation_theme_count": 1,
            "demand_signal_count": 1,
            "pattern_count": 1,
            "recommendation_count": 0,
            "intelligence_brief": {
                "top_insight": "Constructor moved first, but Algolia has product proof.",
                "product_feature_comparison": {
                    "summary": (
                        "1 capability compared; 0 product gaps, 1 narrative gap, "
                        "1 demand-backed row."
                    ),
                    "rows": [
                        {
                            "capability": "agentic product discovery",
                            "assessment": "own_narrative_gap",
                            "own_status": "proven",
                            "competitors_with_product_proof": ["Constructor"],
                            "competitors_with_conversation": ["Constructor"],
                            "has_rising_demand": True,
                            "recommended_action": (
                                "Create an Algolia narrative for agentic product discovery "
                                "using existing product proof."
                            ),
                        }
                    ],
                },
            },
        },
    )

    html = render_cockpit_html(state)

    assert "Product comparison read" in html
    assert "1 capability compared" in html
    assert "own_narrative_gap" in html
    assert "Create an Algolia narrative for agentic product discovery" in html


def test_semantic_layer_renders_audience_demand_alignment() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        demand_feature_alignment=DemandFeatureAlignmentState(
            status="matched",
            signal_count_total=1,
            matched_signal_count=1,
            unmatched_signal_count=0,
            rows=[
                DemandFeatureAlignmentRow(
                    demand_signal_id=501,
                    topic="AI shopping agent",
                    metric="engaged_sessions",
                    value=912,
                    change_pct=0.31,
                    source_label="Looker Studio GA4 export",
                    demand_evidence_url="looker://algolia/ga4/ai-shopping-agent",
                    match_status="matched",
                    matched_capability="AI Shopping Agent",
                    related_companies=[
                        DemandFeatureAlignmentCompany(
                            company_name="Algolia",
                            company_role="own",
                            position_status="proven",
                            evidence_count=1,
                            first_evidence_url="https://www.algolia.com/doc/ai-shopping",
                        ),
                        DemandFeatureAlignmentCompany(
                            company_name="Constructor",
                            company_role="competitor",
                            position_status="proven",
                            evidence_count=1,
                            first_evidence_url="https://constructor.com/products/ai-shopping-agent",
                        ),
                    ],
                    product_evidence_count=2,
                    summary=(
                        "Audience demand for AI shopping agent maps to AI Shopping Agent; "
                        "product proof is captured for Algolia and Constructor."
                    ),
                    next_step="Compare matched product proof before promoting owner recommendations.",
                )
            ],
        ),
    )

    html = render_cockpit_html(state)

    assert "Audience demand alignment" in html
    assert "AI shopping agent" in html
    assert "+31%" in html
    assert "maps to AI Shopping Agent" in html
    assert "Algolia" in html
    assert "Constructor" in html
    assert "looker://algolia/ga4/ai-shopping-agent" in html


def test_cockpit_renders_argus_evidence_needs_for_withheld_actions() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        argus_evidence_needs=[
            ArgusEvidenceNeedSummary(
                evidence_plane="demand",
                status="missing",
                severity="blocks_action",
                title="Demand plane missing",
                why_needed=(
                    "Argus found product-market patterns, but no tenant-side demand evidence "
                    "was captured in this run."
                ),
                blocks=["owner recommendations", "priority ranking"],
                next_step="Upload GA4 / Looker demand export for the current and previous periods.",
                related_run_intelligence_id=42,
                observed_pattern_count=3,
                accepted_input_formats=["csv", "json", "jsonl"],
                required_fields=[
                    "Page title",
                    "Page path",
                    "Engaged sessions",
                    "Engaged sessions previous period",
                    "Period start",
                    "Period end",
                    "Looker Studio URL",
                ],
                operator_surface="CI-OS local admin demand imports",
                observed_state={
                    "demand_plane_status": "missing",
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "looker_manifest_path": "/tmp/cios-product-market/algolia/looker-export-manifest.json",
                },
            )
        ],
    )

    html = render_cockpit_html(state)

    assert "What Argus needs next" in html
    assert "Demand plane missing" in html
    assert "owner recommendations" in html
    assert "Upload GA4 / Looker demand export" in html
    assert "CSV, JSON, JSONL" in html
    assert "Page title" in html
    assert "Demand checked: missing" in html
    assert "0 files discovered" in html
    assert "0 accepted rows" in html
    assert "looker-export-manifest.json" in html


def test_partner_selector_includes_quiet_monitored_competitors_not_only_priority_moves() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        competitor_cards=[_card(competitor_id=5, competitor_name="Constructor")],
        monitored_competitors=[
            MonitoredCompetitor(competitor_id=5, competitor_name="Constructor", active_source_count=4, checked_today=True, material_signal_count=1),
            MonitoredCompetitor(competitor_id=9, competitor_name="Typesense", active_source_count=2, checked_today=True, material_signal_count=0, brief_href="./briefs/algolia/typesense-2026-07-10.html"),
        ],
    )

    html = render_cockpit_html(state)

    assert 'data-select-competitor="5"' in html
    assert 'data-select-competitor="9"' not in html
    assert '<option value="9">Typesense</option>' in html
    assert 'data-competitor-panel="9"' in html
    assert "Typesense" in html
    assert "No material move crossed the action threshold for this partner." in html


def test_market_timeline_renders_product_market_history_from_argus_memory() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        generated_at=datetime(2026, 7, 10, 5, 13, tzinfo=timezone.utc),
        product_market_history=[
            ProductMarketHistoryEntry(
                pattern_id=44,
                observed_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                pattern_type="own_product_gap",
                capability_text="agentic product discovery",
                summary="Constructor showed product proof while Algolia had no public proof in the evidence set.",
                involved_companies=["Algolia", "Constructor"],
                confidence=0.74,
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        product_market_trends=[
            ProductMarketTrendSummary(
                capability_text="agentic product discovery",
                direction="accelerating",
                pattern_count_7d=2,
                pattern_count_30d=3,
                involved_companies=["Constructor", "Coveo"],
                latest_summary="Constructor and Coveo are reinforcing agentic discovery.",
                latest_observed_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                confidence=0.76,
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        product_market_heatmap=[
            ProductMarketHeatmapCell(
                entity_name="Constructor",
                capability_text="agentic product discovery",
                heat_level="hot",
                intensity_score=92.0,
                pattern_count_7d=2,
                pattern_count_30d=3,
                latest_observed_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                latest_summary="Constructor and Coveo are reinforcing agentic discovery.",
                confidence=0.76,
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        product_market_entity_velocity=[
            ProductMarketEntityVelocitySummary(
                entity_name="Constructor",
                direction="accelerating",
                total_patterns_7d=2,
                total_patterns_30d=3,
                hot_capability_count=1,
                warm_capability_count=0,
                top_capabilities=["agentic product discovery"],
                latest_summary="Constructor is accelerating around agentic discovery.",
                latest_observed_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                confidence=0.78,
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        product_market_theme_heatmap=[
            ProductMarketThemeHeatmapCell(
                theme_text="agentic product discovery",
                heat_level="hot",
                direction="accelerating",
                intensity_score=96.0,
                pattern_count_7d=2,
                pattern_count_30d=3,
                entity_count=2,
                leading_entities=["Constructor", "Coveo"],
                pattern_types=["own_narrative_gap", "competitive_pressure"],
                latest_summary="Agentic discovery is heating up across commerce search competitors.",
                latest_observed_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                confidence=0.78,
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        product_market_window_deltas=[
            ProductMarketWindowDeltaSummary(
                subject_type="theme",
                subject_name="agentic product discovery",
                direction="rising",
                current_window_label="last_7d",
                previous_window_label="prior_7d",
                current_pattern_count=2,
                previous_pattern_count=1,
                delta=1,
                related_entities=["Constructor", "Coveo", "Elastic"],
                related_capabilities=["agentic product discovery"],
                latest_summary="Agentic discovery added one more current-window pattern than the prior window.",
                latest_observed_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
                evidence_refs=[{"source_url": "https://constructor.example/changelog"}],
            )
        ],
        product_market_run_history=[
            ProductMarketRunHistoryEntry(
                run_intelligence_id=77,
                observed_at=datetime(2026, 7, 10, 5, 13, tzinfo=timezone.utc),
                verdict="watch",
                top_insight="Argus learned Constructor is moving, but the action is held by coverage learning.",
                primary_action=None,
                evidence_urls=["https://constructor.example/changelog"],
                confidence_limits=["Coverage learning gate was active."],
                product_event_count=2,
                conversation_theme_count=1,
                demand_signal_count=1,
                pattern_count=1,
                recommendation_count=0,
                learning_instruction_count=1,
                learning_instruction_improvement_ids=[202],
            )
        ],
    )

    html = render_cockpit_html(state)

    assert "Product-market memory" in html
    assert "Constructor showed product proof" in html
    assert "agentic product discovery" in html
    assert "own_product_gap" in html
    assert "Trend direction" in html
    assert "accelerating" in html
    assert "Market heat map" in html
    assert "Constructor" in html
    assert "92" in html
    assert "Entity velocity" in html
    assert "accelerating" in html
    assert "Argus run reads" in html
    assert "Constructor is moving" in html
    assert "watch" in html
    assert "Constructor is accelerating around agentic discovery." in html
    assert "Theme heat map" in html
    assert "Agentic discovery is heating up across commerce search competitors." in html
    assert "Constructor, Coveo" in html
    assert "Window deltas" in html
    assert "last_7d vs prior_7d" in html
    assert "Agentic discovery added one more current-window pattern than the prior window." in html


def test_timeline_history_calendar_and_holistic_daily_coverage_are_visible() -> None:
    state = DashboardState(
        tenant_id=1,
        cadence="daily",
        generated_at=datetime(2026, 7, 10, 5, 13, tzinfo=timezone.utc),
        competitor_cards=[_card(competitor_id=5, competitor_name="Constructor", attention_score=88)],
        monitored_competitors=[
            MonitoredCompetitor(competitor_id=5, competitor_name="Constructor", active_source_count=4, checked_today=True, material_signal_count=2),
            MonitoredCompetitor(competitor_id=6, competitor_name="Coveo", active_source_count=6, failed_source_count=5, checked_today=True),
            MonitoredCompetitor(competitor_id=8, competitor_name="Bloomreach", active_source_count=4, checked_today=True),
        ],
        report_history=[
            {"report_id": 10, "report_date": "2026-07-10", "cadence": "daily", "title": "Today", "summary": "Today summary", "status": "rendered", "html_path": "./brief.html"},
            {"report_id": 9, "report_date": "2026-07-09", "cadence": "daily", "title": "Yesterday", "summary": "Yesterday summary", "status": "rendered", "html_path": "./archive/2026-07-09.html"},
            {"report_id": 3, "report_date": "2026-07-03", "cadence": "weekly", "title": "Last week", "summary": "Last week summary", "status": "rendered", "html_path": "./archive/2026-07-03.html"},
        ],
    )

    html = render_cockpit_html(state)

    assert 'id="market-timeline"' in html
    assert 'id="history-calendar"' in html
    assert 'id="history-selector"' in html
    assert "Market timeline" in html
    assert "Yesterday" in html
    assert "Last 7 days" in html
    assert "Last 30 days" in html
    assert "Report history" in html
    assert "Yesterday summary" in html
    assert "Last week summary" in html
    assert "Holistic daily coverage" in html
    assert "Why this priority" in html
    assert "Constructor is first because" in html
    assert "Coveo" in html
    assert "Bloomreach" in html
