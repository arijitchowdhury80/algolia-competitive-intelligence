"""Tests for the claim ledger: evidence invariant, supersedence, contradictions."""

from __future__ import annotations

import pytest

from cios.brain.claim_ledger import ClaimEvidenceError, ClaimLedger

from .conftest import FakeModel


def test_claim_without_url_is_rejected() -> None:
    ledger = ClaimLedger()
    with pytest.raises(ClaimEvidenceError):
        ledger.register(
            tenant_id=1, competitor_id=7, claim_text="fastest search on the market", evidence_urls=[]
        )


def test_claim_with_url_registers() -> None:
    ledger = ClaimLedger()
    claim = ledger.register(
        tenant_id=1,
        competitor_id=7,
        claim_text="fastest search on the market",
        evidence_urls=["https://rival.com/claims"],
    )
    assert claim.id == 1
    assert claim.evidence_urls == ["https://rival.com/claims"]


def test_duplicate_claim_bumps_repetition_and_merges_evidence() -> None:
    ledger = ClaimLedger()
    ledger.register(tenant_id=1, competitor_id=7, claim_text="fastest search", evidence_urls=["https://a"])
    again = ledger.register(
        tenant_id=1, competitor_id=7, claim_text="fastest  search", evidence_urls=["https://b"]
    )
    assert again.repetition_count == 2
    assert set(again.evidence_urls) == {"https://a", "https://b"}
    assert len(ledger.active_claims()) == 1


def test_supersedence_is_non_destructive() -> None:
    ledger = ClaimLedger()
    old = ledger.register(
        tenant_id=1, competitor_id=7, claim_text="ships weekly", evidence_urls=["https://a"]
    )
    new = ledger.register(
        tenant_id=1, competitor_id=7, claim_text="ships daily", evidence_urls=["https://b"]
    )
    ledger.supersede(old.id, new)
    assert old.active is False
    assert old.superseded_by_id == new.id
    assert new.supersedes_id == old.id
    assert len(ledger.all_claims()) == 2  # old is kept, not deleted


def test_contradiction_flagged_on_incompatible_assertion() -> None:
    ledger = ClaimLedger()
    ledger.register(
        tenant_id=1,
        competitor_id=7,
        claim_text="pricing is usage-based",
        evidence_urls=["https://a"],
        subject="pricing model",
        assertion="usage-based",
    )
    ledger.register(
        tenant_id=1,
        competitor_id=7,
        claim_text="pricing is seat-based",
        evidence_urls=["https://b"],
        subject="pricing model",
        assertion="seat-based",
    )
    contradictions = ledger.find_contradictions()
    assert len(contradictions) == 1
    assert contradictions[0].subject == "pricing model"


def test_no_contradiction_across_different_competitors() -> None:
    ledger = ClaimLedger()
    ledger.register(
        tenant_id=1, competitor_id=7, claim_text="x", evidence_urls=["https://a"],
        subject="s", assertion="one",
    )
    ledger.register(
        tenant_id=1, competitor_id=8, claim_text="y", evidence_urls=["https://b"],
        subject="s", assertion="two",
    )
    assert ledger.find_contradictions() == []


async def test_llm_contradiction_extension() -> None:
    model = FakeModel([{"contradicts": True, "reason": "cannot both be true"}])
    ledger = ClaimLedger(model=model)
    a = ledger.register(
        tenant_id=1, competitor_id=7, claim_text="on-prem only", evidence_urls=["https://a"]
    )
    b = ledger.register(
        tenant_id=1, competitor_id=7, claim_text="cloud native", evidence_urls=["https://b"]
    )
    contradiction = await ledger.llm_contradicts(a, b)
    assert contradiction is not None
    assert contradiction.method == "llm"
