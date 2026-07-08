"""Tests for argus-quality-reviewer (src/cios/brain/quality.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cios.brain.quality import QualityReviewer, UnparseableVerdict, extract_json_object
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
    evidence_texts: dict = field(default_factory=dict)


class FakeLLMReviewer:
    """Fake router-backed reviewer: scripted verdict, records calls."""

    def __init__(self, verdict: dict) -> None:
        self.verdict = verdict
        self.calls: list = []

    def review(self, tenant_id, run_id, reader_text, claims, evidence_texts=None, attempt: int = 1):
        self.calls.append((tenant_id, run_id, reader_text, claims, evidence_texts, attempt))
        return self.verdict


class UnparseableThenValidLLMReviewer:
    """Raises UnparseableVerdict on the first attempt, returns a valid verdict
    on the corrective retry -- mirrors the synthesizer's malformed-then-valid
    retry behavior."""

    def __init__(self, verdict: dict) -> None:
        self.verdict = verdict
        self.calls: list = []

    def review(self, tenant_id, run_id, reader_text, claims, evidence_texts=None, attempt: int = 1):
        self.calls.append(attempt)
        if attempt == 1:
            raise UnparseableVerdict("not valid JSON")
        return self.verdict


class AlwaysUnparseableLLMReviewer:
    """Raises UnparseableVerdict on every attempt -- the reviewer must fail
    closed after the retry, never fabricate a pass."""

    def __init__(self) -> None:
        self.calls: list = []

    def review(self, tenant_id, run_id, reader_text, claims, evidence_texts=None, attempt: int = 1):
        self.calls.append(attempt)
        raise UnparseableVerdict("still not valid JSON")


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


# -- quote-verification (deterministic, before the LLM call) ----------------


def test_quote_present_verbatim_in_evidence_is_not_flagged():
    reviewer, fake = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(
            text='Competitor X said "we are pivoting to AI search" last week.',
            source_url="https://example.com/a",
        )],
        reader_text="Competitor X pivoted to AI search.",
        evidence_texts={"https://example.com/a": "In the call they said we are pivoting to AI search."},
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.PASSED
    assert len(fake.calls) == 1


def test_quote_absent_from_evidence_is_a_required_fix():
    reviewer, fake = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(
            text='Competitor X said "we are killing our biggest rival" last week.',
            source_url="https://example.com/a",
        )],
        reader_text="Competitor X made a bold claim.",
        evidence_texts={"https://example.com/a": "The company discussed its roadmap for next year."},
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert any("quote not found verbatim in source" in f["fix"] for f in result.required_fixes)
    assert fake.calls == []  # deterministic failure short-circuits the LLM call


def test_figure_only_claim_verified_against_evidence():
    reviewer, fake = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(
            text="Revenue grew 42% year over year, the company said.",
            source_url="https://example.com/a",
        )],
        reader_text="Revenue is up sharply.",
        evidence_texts={"https://example.com/a": "Full-year revenue grew 42% versus last year."},
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.PASSED
    assert len(fake.calls) == 1


def test_figure_only_claim_not_in_evidence_is_a_required_fix():
    reviewer, _ = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(
            text="Revenue grew 42% year over year, the company said.",
            source_url="https://example.com/a",
        )],
        reader_text="Revenue is up sharply.",
        evidence_texts={"https://example.com/a": "The company declined to share specific growth figures."},
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert any("quote not found verbatim in source" in f["fix"] for f in result.required_fixes)


def test_no_evidence_texts_supplied_skips_quote_check_entirely():
    # Backward compatible with callers that don't supply an evidence corpus:
    # the deterministic check is a no-op, not a false failure.
    reviewer, fake = make_reviewer()
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text='Competitor X said "anything at all" today.', source_url="https://example.com/a")],
        reader_text="Fine text.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.PASSED
    assert len(fake.calls) == 1


# -- unparseable LLM verdict: retry once, then fail closed -------------------


def test_unparseable_llm_verdict_retries_once_and_then_passes():
    fake = UnparseableThenValidLLMReviewer({"pass": True, "required_fixes": [], "notes": ""})
    reviewer = QualityReviewer(fake)
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Claim.", source_url="https://example.com/a")],
        reader_text="Fine text.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.PASSED
    assert fake.calls == [1, 2]


def test_unparseable_llm_verdict_twice_fails_closed():
    fake = AlwaysUnparseableLLMReviewer()
    reviewer = QualityReviewer(fake)
    review_input = FakeReviewInput(
        tenant_id=1,
        run_id="run-1",
        claims=[FakeClaim(text="Claim.", source_url="https://example.com/a")],
        reader_text="Fine text.",
    )

    result = reviewer.review(review_input)

    assert result.status == QualityReviewStatus.FAILED
    assert fake.calls == [1, 2]
    assert any("unparseable verdict twice" in f["fix"] for f in result.required_fixes)


# -- shared JSON extraction helper -------------------------------------------


def test_extract_json_object_handles_fenced_block():
    text = '```json\n{"pass": true, "required_fixes": [], "notes": "ok"}\n```'
    obj = extract_json_object(text)
    assert obj == {"pass": True, "required_fixes": [], "notes": "ok"}


def test_extract_json_object_handles_leading_prose():
    text = 'Sure, here is the verdict:\n{"pass": false, "required_fixes": ["fix it"], "notes": ""}\nThanks!'
    obj = extract_json_object(text)
    assert obj == {"pass": False, "required_fixes": ["fix it"], "notes": ""}


def test_extract_json_object_returns_none_for_garbage():
    assert extract_json_object("not json at all") is None
    assert extract_json_object("") is None
