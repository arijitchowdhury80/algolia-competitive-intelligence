"""Tests for the lens-plays-empty fix.

Two things needed to be true and neither was: (1) the daily runner's
DashboardStateBuilder call (scripts/daily_production_run.py) didn't pass a
`prescriptions` repo at all, so state_builder._build_prescriptions()
unconditionally returned [] even though action_items rows existed; (2) there
was no Postgres-backed PrescriptionsRepository reading `action_items` (the
table prescription_to_action_item + insert_action_item actually persist to).

This file covers both: the pure row-mapping function that reverses
prescription_to_action_item's fold, and an end-to-end fake-repo test proving
a persisted action_items-shaped row reaches the correct cockpit lens.
"""

from __future__ import annotations

from cios.dashboard.cockpit_renderer import render_cockpit_html
from cios.db.repos.dashboard import _action_item_to_prescription_row

from .conftest import full_coverage
from .test_state_builder import make_builder


def _action_item_row(**overrides) -> dict:
    base = dict(
        owner="Sales Enablement",
        recommendation="Brief sales on the AWS packaging shift: Send a Slack summary; Add a battlecard note",
        evidence_ids=["https://example.com/aws-pricing"],
        priority="this_week",
        due_window="this_week",
    )
    base.update(overrides)
    return base


def test_action_item_to_prescription_row_splits_title_and_steps():
    row = _action_item_to_prescription_row(_action_item_row())
    assert row["title"] == "Brief sales on the AWS packaging shift"
    assert row["play"] == ["Send a Slack summary", "Add a battlecard note"]
    assert row["team"] == "Sales Enablement"
    assert row["urgency_window"] == "this_week"
    assert row["evidence_urls"] == ["https://example.com/aws-pricing"]
    assert row["expected_effect"] is None


def test_action_item_to_prescription_row_handles_title_only_no_steps():
    row = _action_item_to_prescription_row(
        _action_item_row(recommendation="Validate whether this is pricing or packaging")
    )
    assert row["title"] == "Validate whether this is pricing or packaging"
    assert row["play"] == []


def test_persisted_action_item_reaches_the_matching_lens():
    # 4 tenant-1 action_items, same shape PgPrescriptionsRepository would
    # return for "today's" rows, one per team.
    action_items = [
        _action_item_row(owner="Marketing", recommendation="Publish the pricing rebuttal: Draft it; Ship it",
                         priority="act_now"),
        _action_item_row(owner="Content", recommendation="Prep the objection one-pager: List objections",
                         priority="this_week"),
        _action_item_row(owner="Sales Enablement",
                         recommendation="Brief sales on the AWS packaging shift: Send a Slack summary",
                         priority="this_week"),
        _action_item_row(owner="Product", recommendation="Validate pricing vs packaging: Pull the docs diff",
                         priority="this_month"),
    ]
    prescriptions_rows = [_action_item_to_prescription_row(r) for r in action_items]

    builder = make_builder(
        signals={1: []},
        coverage={1: full_coverage()},
        prescriptions={1: prescriptions_rows},
    )
    state = builder.build(tenant_id=1, cadence="daily")
    assert len(state.prescriptions) == 4

    html_out = render_cockpit_html(state)
    marketing_start = html_out.index('id="role-marketing"')
    sales_start = html_out.index('id="role-sales"')
    product_start = html_out.index('id="role-product"')
    eye_start = html_out.index("The eye behind the lenses")

    marketing_html = html_out[marketing_start:sales_start]
    sales_html = html_out[sales_start:product_start]
    product_html = html_out[product_start:eye_start]

    assert "Publish the pricing rebuttal" in marketing_html
    assert "Prep the objection one-pager" in marketing_html
    assert "Brief sales on the AWS packaging shift" not in marketing_html

    assert "Brief sales on the AWS packaging shift" in sales_html
    assert "Publish the pricing rebuttal" not in sales_html

    assert "Validate pricing vs packaging" in product_html
    assert "Brief sales on the AWS packaging shift" not in product_html

    # No lens falls back to the honest empty state when a real play exists.
    assert "No prescribed plays for this lens this cycle." not in html_out
