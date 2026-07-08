from __future__ import annotations

from cios.common.dedup import cluster_by_similarity, token_set_similarity


def test_token_set_similarity_identical_text_is_one():
    assert token_set_similarity("Heap rebrands as Contentsquare", "Heap rebrands as Contentsquare") == 1.0


def test_token_set_similarity_empty_text_is_zero():
    assert token_set_similarity("", "anything") == 0.0
    assert token_set_similarity("anything", "") == 0.0


def test_token_set_similarity_unrelated_text_is_low():
    assert token_set_similarity("Heap rebrands to Contentsquare", "Coveo raises Series F funding") < 0.2


def test_cluster_merges_same_story_same_competitor():
    items = [
        {"competitor_id": 1, "headline": "Heap rebrands its product as Contentsquare"},
        {"competitor_id": 1, "headline": "Heap has rebranded its product as Contentsquare"},
    ]
    clusters = cluster_by_similarity(
        items, group_key=lambda d: d["competitor_id"], text=lambda d: d["headline"]
    )
    assert len(clusters) == 1
    assert clusters[0].count == 2


def test_cluster_keeps_different_stories_separate():
    items = [
        {"competitor_id": 1, "headline": "Heap rebrands as Contentsquare product"},
        {"competitor_id": 1, "headline": "Heap raises new funding round from investors"},
    ]
    clusters = cluster_by_similarity(
        items, group_key=lambda d: d["competitor_id"], text=lambda d: d["headline"]
    )
    assert len(clusters) == 2
    assert all(c.count == 1 for c in clusters)


def test_cluster_never_merges_across_group_key_even_if_text_identical():
    items = [
        {"competitor_id": 1, "headline": "Launches a new AI search feature"},
        {"competitor_id": 2, "headline": "Launches a new AI search feature"},
    ]
    clusters = cluster_by_similarity(
        items, group_key=lambda d: d["competitor_id"], text=lambda d: d["headline"]
    )
    assert len(clusters) == 2



def test_match_any_links_paraphrase_chains():
    """Transitive linking regression (2026-07-08 live theses): six rewordings
    of one hypothesis form a chain where the ends are not similar enough to
    the representative, only to intermediate members. match="any" must merge
    the chain; unrelated text must stay out."""
    from cios.common.dedup import cluster_by_similarity

    items = [
        {"k": 1, "t": "Elastic is reframing search infrastructure as the retrieval layer for agentic AI, signaling that context engineering will become a contested battleground."},
        {"k": 1, "t": "Elastic is repositioning from search vendor to AI agent infrastructure layer, signaling that context engineering will become the new battleground for incumbents."},
        {"k": 1, "t": "Elastic is pivoting from search-for-humans to retrieval-for-agents, positioning Elasticsearch as infrastructure that AI systems call rather than humans query."},
        {"k": 1, "t": "Constructor is staking a claim that agentic commerce will be the next category frame, repositioning itself as an autonomous reasoning engine."},
    ]
    clusters = cluster_by_similarity(
        items, group_key=lambda d: d["k"], text=lambda d: d["t"],
        threshold=0.4, match="any",
    )
    sizes = sorted(c.count for c in clusters)
    assert sizes == [1, 3]
