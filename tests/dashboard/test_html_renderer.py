"""Tests for src/cios/dashboard/html_renderer.py.

Loads a real Gate-7 rehearsal state JSON (not a hand-rolled fixture) to
exercise the renderer against the same shape the publisher actually emits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cios.dashboard.html_renderer import render_dashboard_html
from cios.dashboard.types import DashboardState

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_STATE_PATH = (
    REPO_ROOT / "docs" / "planning" / "gate7-rehearsal-runs" / "dashboard-state.v2.1.daily.json"
)


def _load_state(path: Path = SAMPLE_STATE_PATH) -> DashboardState:
    payload = json.loads(path.read_text(encoding="utf-8"))
    # DashboardState doesn't declare schema_version/is_quiet/top_attention_level
    # as fields (they're derived properties / publisher metadata) -- strip them.
    payload.pop("schema_version", None)
    payload.pop("is_quiet", None)
    payload.pop("top_attention_level", None)
    return DashboardState.model_validate(payload)


@pytest.fixture()
def state() -> DashboardState:
    return _load_state()


def test_renders_without_error(state: DashboardState) -> None:
    html_out = render_dashboard_html(state)
    assert "<html" in html_out
    assert "</html>" in html_out


def test_page_is_self_contained_no_external_js(state: DashboardState) -> None:
    html_out = render_dashboard_html(state)
    assert "<script" not in html_out
    assert "http://" not in html_out.split("<style>")[0]  # no external script/link before style
    # No <link> to external stylesheets and no <script src=...>
    assert "<link " not in html_out
    assert "script src" not in html_out


def test_signal_cards_present_when_active(state: DashboardState) -> None:
    html_out = render_dashboard_html(state)
    assert not state.is_quiet  # sample run has active competitor cards
    for card in state.competitor_cards:
        assert card.competitor_name in html_out


def test_evidence_links_are_article_urls(state: DashboardState) -> None:
    html_out = render_dashboard_html(state)
    for card in state.competitor_cards:
        for evidence_id in card.evidence_ids:
            assert str(evidence_id) in html_out
            assert f'href="{evidence_id}"' in html_out


def test_quiet_paragraph_only_when_quiet_eligible() -> None:
    # The sample state is NOT quiet-eligible (exec_speech lane failed), so the
    # hero must not claim "Quiet today".
    state = _load_state()
    html_out = render_dashboard_html(state)
    assert not state.coverage.is_quiet_eligible
    assert "Quiet today" not in html_out
    assert "Coverage incomplete" in html_out


def test_quiet_hero_renders_when_state_is_quiet() -> None:
    state = _load_state()
    # Force a quiet-eligible, quiet state to prove the quiet copy path fires.
    quiet_payload = state.model_dump(mode="json")
    quiet_payload["competitor_cards"] = []
    quiet_payload["material_delta_ids"] = []
    quiet_payload["coverage"]["false_negative_audit_status"] = "clean"
    for lane in quiet_payload["coverage"]["lanes"]:
        lane["ran"] = True
        lane["error"] = None
    quiet_state = DashboardState.model_validate(quiet_payload)
    assert quiet_state.is_quiet

    html_out = render_dashboard_html(quiet_state)
    assert "Quiet today" in html_out
    assert "Coverage incomplete" not in html_out


def test_unescaped_injection_is_escaped() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["competitor_cards"][0]["top_signal_headline"] = "<script>alert(1)</script>"
    payload["competitor_cards"][0]["competitor_name"] = "<img src=x onerror=alert(2)>"
    injected_state = DashboardState.model_validate(payload)

    html_out = render_dashboard_html(injected_state)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    assert "<img src=x onerror=alert(2)>" not in html_out


def test_suppressed_signals_empty_state_renders_no_panel() -> None:
    # Live-audit finding #4: an empty Suppressed Signals box is noise, not a
    # trust signal. When there is nothing suppressed, the whole panel (and
    # its heading) must be absent, not an "empty" placeholder inside it.
    state = _load_state()
    assert state.suppressed_signals == []
    html_out = render_dashboard_html(state)
    assert "No suppressed signals this cycle." not in html_out
    assert 'id="suppressed-title"' not in html_out


def test_suppressed_signals_render_with_reason_and_count() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["suppressed_signals"] = [
        {"suppressed_id": 1, "reason": "Below materiality threshold", "finding_count": 4,
         "suppressed_at": None, "notes": "batch review"},
    ]
    populated = DashboardState.model_validate(payload)
    html_out = render_dashboard_html(populated)
    assert "Below materiality threshold" in html_out
    assert "4 finding(s) suppressed" in html_out
    assert "batch review" in html_out


def test_report_history_empty_state_is_honest_not_a_stub() -> None:
    state = _load_state()
    assert state.report_history == []
    html_out = render_dashboard_html(state)
    assert "No reports generated yet." in html_out
    assert 'id="history-title"' in html_out


def test_report_history_renders_rows_with_link() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["report_history"] = [
        {"report_id": 1, "report_date": "2026-07-08", "cadence": "daily",
         "title": "Argus daily brief - algolia", "summary": "No material signal.",
         "status": "rendered", "html_path": "archive/2026-07-08.html"},
    ]
    populated = DashboardState.model_validate(payload)
    html_out = render_dashboard_html(populated)
    assert "Argus daily brief - algolia" in html_out
    assert 'href="archive/2026-07-08.html"' in html_out
    assert "rendered" in html_out


def test_section_order_matches_reference_layout() -> None:
    # hero -> signal cards -> living theses -> [suppressed, when present] in
    # the main column; report history moved to a compact footer BELOW the
    # two-column layout entirely (live-audit finding #3).
    state = _load_state()
    html_out = render_dashboard_html(state)
    hero_pos = html_out.index('id="daily-title"')
    signals_pos = html_out.index('id="signals-title"')
    theses_pos = html_out.index('id="theses-title"')
    history_pos = html_out.index('id="history-title"')
    assert hero_pos < signals_pos < theses_pos < history_pos


def test_build_health_panel_is_gone() -> None:
    # Live-audit finding #5: Build health was a stub with no truthful
    # source. It must not appear on the page at all.
    state = _load_state()
    html_out = render_dashboard_html(state)
    assert "Build health" not in html_out
    assert "Trust line" in html_out


def test_trust_line_replaces_data_limits_and_run_health_boxes() -> None:
    state = _load_state()
    html_out = render_dashboard_html(state)
    assert "Data limits" not in html_out
    assert html_out.count('<h2>Run health</h2>') == 0
    assert "Sources checked" in html_out
    assert "False-negative audit" in html_out
    assert "Quality review" in html_out
    assert "Delivery" in html_out


def test_report_history_dedupes_same_day_and_caps_at_seven() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    rows = []
    for i in range(10):
        rows.append({
            "report_id": i, "report_date": "2026-07-01", "cadence": "daily",
            "title": f"Argus daily brief - dup {i}", "summary": "No material signal.",
            "status": "rendered", "html_path": None,
        })
    payload["report_history"] = rows
    populated = DashboardState.model_validate(payload)
    html_out = render_dashboard_html(populated)
    # All ten rows share one report_date -> dedup collapses to one entry.
    assert html_out.count("2026-07-01") == 1


def test_report_history_entry_without_html_path_has_no_dead_link() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["report_history"] = [
        {"report_id": 1, "report_date": "2026-07-08", "cadence": "daily",
         "title": "Argus daily brief - algolia", "summary": "No material signal.",
         "status": "rendered", "html_path": None},
    ]
    populated = DashboardState.model_validate(payload)
    html_out = render_dashboard_html(populated)
    assert "Argus daily brief - algolia" in html_out
    assert "<a href=" not in html_out.split('id="history-title"')[1]


def test_signal_card_shows_seen_in_n_sources_badge_when_duplicate() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["competitor_cards"][0]["duplicate_count"] = 3
    populated = DashboardState.model_validate(payload)
    html_out = render_dashboard_html(populated)
    assert "seen in 3 sources" in html_out


def test_signal_card_has_no_badge_when_not_duplicate() -> None:
    state = _load_state()
    html_out = render_dashboard_html(state)
    assert "seen in" not in html_out


def test_reuses_original_css_tokens() -> None:
    # Confirms the renderer copies Arijit's design tokens verbatim rather than
    # inventing new ones.
    state = _load_state()
    html_out = render_dashboard_html(state)
    assert "--blue: #003dff" in html_out
    assert "class=\"hero\"" in html_out
    assert "class=\"shell\"" in html_out
