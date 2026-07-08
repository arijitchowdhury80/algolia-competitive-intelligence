"""Tests for argus-quality-reviewer (src/cios/brain/quality.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cios.brain.quality import QualityReviewer
from cios.learn.types import QualityReviewStatus


@dataclass
class FakeClaim:
    text: str
    source_url: Optional[str] = None


@dataclass
class FakeReviewInput:
    tenant_id: int
    run_id: Optional[str]
    claims: list = field(default_factory=list)
    reader_text: str = ""
    quiet_verdict: bool = False
    coverage_ran_clean: bool = True


class FakeLLMReviewer:
    """Fake router-backed reviewer: scripted verdict, records calls."""

    def __init__(self, verdict: dict) -> None:
        self.verdict = verdict
        self.calls: list = []

    def review(self, tenant_id, run_id, reader_text, claims):
        self.calls.append((tenant_id, run_id, reader_text, claims))
        return self.verdict


def make_reviewer(verdict: dict | None = None) -> tuple[QualityReviewer, FakeLLMReviewer]:
    fake = FakeLLMReviewer(verdict or {"pass": True, "required_fixes": [], "notes": ""})
    return QualityReviewer(fake), fake


def test_rejects_bare_claim_without_source_url():
    reviewer, fake = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Competitor X raised prices 10%.", source_url=None)],
        reader_text="Competitor X raised prices 10%.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert any("source URL" in f["fix"] for f in result.required_fixes)
    assert fake.calls == []  # deterministic failure short-circuits the LLM call


def test_rejects_claim_with_non_url_source():
    reviewer, _ = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Claim.", source_url="see internal notes")],
        reader_text="Claim.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED


def test_detects_em_dash_in_reader_text():
    reviewer, _ = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Claim.", source_url="https://example.com/a")],
        reader_text="Competitor X pivoted — a material move.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert any("em dash" in f["fix"] for f in result.required_fixes)


def test_detects_banned_generic_ai_phrase():
    reviewer, _ = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Claim.", source_url="https://example.com/a")],
        reader_text="This is a cutting-edge platform with seamless integration.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    fixes = " ".join(f["fix"] for f in result.required_fixes)
    assert "cutting-edge" in fixes
    assert "seamless" in fixes


def test_quiet_verdict_without_coverage_proof_fails():
    reviewer, _ = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[],
        reader_text="Market was quiet today.",
        quiet_verdict=True,
        coverage_ran_clean=False,
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert any("coverage proof" in f["fix"] for f in result.required_fixes)


def test_quiet_verdict_with_clean_coverage_passes_deterministic_gate():
    reviewer, fake = make_reviewer({"pass": True, "required_fixes": [], "notes": ""})
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[],
        reader_text="Market was quiet today.",
        quiet_verdict=True,
        coverage_ran_clean=True,
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.PASSED
    assert len(fake.calls) == 1


def test_llm_fail_verdict_surfaces_required_fixes():
    reviewer, _ = make_reviewer(
        {
            "pass": False,
            "required_fixes": ["claim about pricing lacks materiality context"],
            "notes": "voice reads flat, no sharp POV",
        }
    )
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Claim.", source_url="https://example.com/a")],
        reader_text="Competitor X raised prices.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert result.required_fixes == [{"fix": "claim about pricing lacks materiality context"}]
    assert any(f.get("note") == "voice reads flat, no sharp POV" for f in result.findings)


def test_tenant_id_is_carried_through_to_review():
    reviewer, fake = make_reviewer({"pass": True, "required_fixes": [], "notes": ""})
    review_input = FakeReviewInput(
        tenant_id=42,
        run_id="run-9",
        claims=[FakeClaim(text="Claim.", source_url="https://example.com/a")],
        reader_text="Fine text.",
    )

    result = reviewer.review(review_input)

    assert result.tenant_id == 42
    assert result.run_id == "run-9"
    assert fake.calls[0][0] == 42
