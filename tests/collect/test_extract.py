"""Tests for ported V0 semantic extraction behavior: long-line segmentation,
source classification, multi-fact narrative extraction with generic-title
filtering and dedup, and delta scoring.
"""

from __future__ import annotations

from cios.collect.extract import (
    GENERIC_NARRATIVE_TITLE,
    content_hash,
    extract_content_narrative_facts,
    extract_customer_proof_facts,
    extract_semantic_facts,
    infer_content_topic,
    is_content_source,
    is_customer_source,
    materiality_for_delta,
    semantic_diff,
    semantic_lines,
)
from cios.collect.types import Delta, SourceContext


def blog_source(competitor_id: int = 1, competitor_name: str = "Constructor") -> SourceContext:
    return SourceContext(
        competitor_id=competitor_id,
        competitor_name=competitor_name,
        url="https://constructor.io/blog",
        source_type="blog",
        priority=2,
    )


def customer_source() -> SourceContext:
    return SourceContext(
        competitor_id=2,
        competitor_name="Coveo",
        url="https://coveo.com/customer-stories",
        source_type="case_study",
        priority=3,
    )


# ---------------------------------------------------------------------------
# content_hash / classification
# ---------------------------------------------------------------------------

def test_content_hash_is_stable_sha256():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")
    assert len(content_hash("hello")) == 64


def test_is_content_source_matches_expanded_markers():
    assert is_content_source(blog_source())
    assert is_content_source(SourceContext(
        competitor_id=1, competitor_name="X", url="https://x.com/changelog", source_type="changelog",
    ))
    assert not is_content_source(SourceContext(
        competitor_id=1, competitor_name="X", url="https://x.com/pricing", source_type="pricing",
    ))


def test_is_customer_source_matches_case_customer_story_markers():
    assert is_customer_source(customer_source())
    assert not is_customer_source(blog_source())


# ---------------------------------------------------------------------------
# semantic_lines: long-line segmentation (the recent prod hotfix)
# ---------------------------------------------------------------------------

def test_semantic_lines_segments_long_whitespace_collapsed_blob():
    # A single 240+ char "line" with no newlines -- the failure mode the
    # hotfix addressed (a line-oriented extractor saw one giant line and
    # found no facts because two distinct sentences never separated).
    blob = (
        "Constructor launches AI search for agentic commerce workflows across enterprise catalogs. "
        "The new agentic search product connects retrieval to product discovery pipelines "
        "for enterprise merchandising teams evaluating semantic search vendors this quarter. "
        "Buyers are comparing agentic retrieval against legacy keyword search deployments broadly."
    )
    assert len(blob) > 240
    lines = semantic_lines(blob)
    assert len(lines) >= 2
    assert any("Constructor launches AI search" in line for line in lines)


def test_semantic_lines_drops_boilerplate_and_cookie_markers():
    text = "Cookie preferences accept all decline all\nReal narrative sentence about AI search launch today."
    lines = semantic_lines(text)
    assert all("cookie" not in line.lower() for line in lines)
    assert any("AI search launch" in line for line in lines)


# ---------------------------------------------------------------------------
# infer_content_topic
# ---------------------------------------------------------------------------

def test_infer_content_topic_classifies_agentic_and_ai_search():
    assert infer_content_topic("our new agentic search for commerce discovery") == "agentic_search"
    assert infer_content_topic("introducing semantic search for retrieval") == "ai_search"
    assert infer_content_topic("improving product discovery and merchandising relevance") == "product_discovery"
    assert infer_content_topic("just a generic update") == "market_narrative"


# ---------------------------------------------------------------------------
# extract_content_narrative_facts: multi-fact, generic-title filter, dedup
# ---------------------------------------------------------------------------

def test_extract_content_narrative_facts_returns_multiple_facts_up_to_eight():
    lines = [
        f"Introducing AI search feature number {i} for agentic product discovery workflows today"
        for i in range(1, 11)
    ]
    text = "\n".join(lines)
    facts = extract_content_narrative_facts(text, blog_source(), "2026-07-07")
    assert 1 <= len(facts) <= 8
    assert all(fact.fact_type == "content_narrative" for fact in facts)


def test_extract_content_narrative_facts_filters_generic_section_titles():
    assert GENERIC_NARRATIVE_TITLE.match("Roadmap & Product Updates")
    text = "Roadmap & Product Updates\nAI & Machine Learning"
    facts = extract_content_narrative_facts(text, blog_source(), "2026-07-07")
    assert facts == []


def test_extract_content_narrative_facts_dedups_by_title_identity():
    text = (
        "Introducing our new AI search launch for agentic commerce today\n"
        "Introducing our new AI search launch for agentic commerce today\n"
    )
    facts = extract_content_narrative_facts(text, blog_source(), "2026-07-07")
    assert len(facts) == 1


def test_extract_content_narrative_facts_requires_relevance_keyword():
    text = "This is just a long generic sentence about nothing relevant to our watch list at all today"
    facts = extract_content_narrative_facts(text, blog_source(), "2026-07-07")
    assert facts == []


# ---------------------------------------------------------------------------
# extract_customer_proof_facts
# ---------------------------------------------------------------------------

def test_extract_customer_proof_facts_extracts_named_customer_with_metric():
    text = "Acme Corp uses Coveo and saw a 25% increase in conversion after launch."
    facts = extract_customer_proof_facts(text, customer_source(), "2026-07-07")
    assert len(facts) >= 1
    assert facts[0].fact_type == "customer_proof"
    assert facts[0].fact_json["customer_name"] == "Acme Corp"
    assert facts[0].fact_json["metric"] == "25%"
    assert facts[0].confidence == 0.82


# ---------------------------------------------------------------------------
# extract_semantic_facts dispatch
# ---------------------------------------------------------------------------

def test_extract_semantic_facts_dispatches_by_source_classification():
    assert extract_semantic_facts("", blog_source(), "2026-07-07") == []
    unrelated = SourceContext(competitor_id=1, competitor_name="X", url="https://x.com/pricing", source_type="pricing")
    assert extract_semantic_facts("anything", unrelated, "2026-07-07") == []


# ---------------------------------------------------------------------------
# materiality_for_delta / semantic_diff
# ---------------------------------------------------------------------------

def test_materiality_for_delta_scores_customer_proof_above_threshold_with_evidence():
    delta = Delta(
        competitor_id=2,
        delta_type="new_customer_proof",
        what_changed="Coveo added customer proof for Acme Corp.",
        evidence_urls=["https://coveo.com/customer-stories"],
        metadata={"after_json": {
            "customer_name": "Acme Corp",
            "metric": "25%",
            "product_area": "AI search",
            "proof_strength": "high",
        }},
    )
    scored = materiality_for_delta(delta, customer_source())
    assert scored.materiality_score >= 0.65
    assert scored.quality_status == "review"


def test_materiality_for_delta_penalizes_missing_evidence():
    delta = Delta(
        competitor_id=2,
        delta_type="new_customer_proof",
        what_changed="Coveo added customer proof for Acme Corp.",
        evidence_urls=[],
        metadata={"after_json": {"customer_name": "Acme Corp"}},
    )
    scored = materiality_for_delta(delta, customer_source())
    assert scored.quality_status == "suppressed"


def test_semantic_diff_fires_delta_only_for_new_fact_not_seen_before():
    old_text = "Acme Corp uses Coveo and saw a 25% increase in conversion."
    new_text = old_text  # unchanged content -> no new fact identity
    facts, deltas = semantic_diff(customer_source(), old_text, new_text, "2026-07-07")
    assert facts  # extraction still runs against new_text
    assert len(deltas) == 1
    assert deltas[0].delta_type == "suppressed_non_semantic_change"


def test_semantic_diff_fires_real_delta_for_genuinely_new_customer():
    # Two distinct customer-proof lines need a line break between them --
    # semantic_lines() only separates facts within one blob when it exceeds
    # 240 chars; a plain single short line yields one merged fact (ported
    # V0 behavior, not a bug this test should paper over).
    old_text = "Acme Corp uses Coveo."
    new_text = old_text + "\nWidget Inc uses Coveo and saw a 40% increase in conversion after launch."
    facts, deltas = semantic_diff(customer_source(), old_text, new_text, "2026-07-07")
    delta_types = {d.delta_type for d in deltas}
    assert "new_customer_proof" in delta_types
