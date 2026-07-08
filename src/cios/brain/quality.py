"""argus-quality-reviewer: challenge every report before delivery.

Manifesto Phase 6 (docs/planning/Argus-project-manifesto.md): the reviewer
gates delivery -- a failed verdict must never ship. Checks run deterministic
first (cheap, catches the manifesto's top failure modes -- unsourced claims,
voice violations, quiet-without-coverage) and only escalate to an LLM
review (voice/materiality/hallucination sniff) once the deterministic gate
is clean, since a deterministic failure already answers "does this ship."

Reuses: src/cios/learn/types.py QualityReview/QualityReviewStatus models
(schema: quality_reviews) rather than redefining them. Depends on the LLM
via a narrow injected Protocol -- not src/cios/platform/models/router.py
directly -- because the router's ModelProvider.generate() is async and the
brain-core Protocol convention here (fn_audit.py's LLMAuditor) is sync; a
thin adapter (asyncio.run over router.select_model() + provider.generate())
satisfies QualityLLMReviewer in production. Tests use a fake.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol

from cios.learn.types import QualityReview, QualityReviewStatus

# House rule (manifesto section 6 "Non-negotiable product doctrine"):
# no em dashes in reader-facing text. U+2014 only -- a plain ASCII "--" is
# not an em dash and is left alone.
EM_DASH = "—"

# Generic-AI-slop phrases banned from Argus voice (manifesto: "no generic
# AI slop"). Matched case-insensitively as substrings.
BANNED_PHRASES: tuple[str, ...] = (
    "cutting-edge",
    "cutting edge",
    "seamless",
    "robust solution",
    "in today's fast-paced",
    "leverage synergies",
    "game-changer",
    "game changer",
    "unlock the power",
    "comprehensive overview",
    "delve into",
    "it is important to note",
    "in conclusion",
)

URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


class Claim(Protocol):
    """Structural shape a reviewed claim must have -- duck-typed so callers
    can pass their own synthesis dataclasses without importing this module's
    types into the synthesizer."""

    text: str
    source_url: Optional[str]


class ReviewInput(Protocol):
    """Structural shape of what gets reviewed: a batch of claims plus the
    reader-facing text and the quiet-verdict/coverage flags needed for the
    'quiet day requires healthy coverage' check (manifesto + eval plan)."""

    tenant_id: int
    run_id: Optional[str]
    claims: list[Claim]
    reader_text: str
    quiet_verdict: bool
    coverage_ran_clean: bool


class QualityLLMReviewer(Protocol):
    """Extension point for the LLM half of the review (voice, materiality,
    hallucination sniff) -- called via src/cios/platform/models/router.py's
    quality tier in production. Returns a structured verdict; tests inject
    a fake."""

    def review(
        self,
        tenant_id: int,
        run_id: Optional[str],
        reader_text: str,
        claims: list[Claim],
    ) -> dict:
        """Must return {"pass": bool, "required_fixes": list[str], "notes": str}."""
        ...


def _check_claim_sources(claims: list[Claim]) -> list[str]:
    fixes = []
    for claim in claims:
        url = getattr(claim, "source_url", None)
        if not url or not URL_PATTERN.match(url):
            snippet = claim.text[:80]
            fixes.append(f"claim missing a live-format source URL: '{snippet}'")
    return fixes


def _check_em_dashes(reader_text: str) -> list[str]:
    if EM_DASH in reader_text:
        return ["reader-facing text contains an em dash (house rule: none allowed)"]
    return []


def _check_banned_phrases(reader_text: str) -> list[str]:
    lowered = reader_text.lower()
    return [
        f"generic-AI-slop phrase found: '{phrase}'"
        for phrase in BANNED_PHRASES
        if phrase in lowered
    ]


def _check_quiet_coverage(quiet_verdict: bool, coverage_ran_clean: bool) -> list[str]:
    if quiet_verdict and not coverage_ran_clean:
        return [
            "quiet verdict without coverage proof: a quiet day is only "
            "reportable if every required lane provably ran clean"
        ]
    return []


class QualityReviewer:
    """Reviews a synthesized brief/signal batch before delivery. A failed
    review must never be delivered -- this class returns the verdict; the
    caller (delivery gate) is responsible for enforcing it."""

    def __init__(self, llm_reviewer: QualityLLMReviewer) -> None:
        self._llm_reviewer = llm_reviewer

    def review(self, review_input: ReviewInput) -> QualityReview:
        deterministic_fixes: list[str] = []
        deterministic_fixes += _check_claim_sources(review_input.claims)
        deterministic_fixes += _check_em_dashes(review_input.reader_text)
        deterministic_fixes += _check_banned_phrases(review_input.reader_text)
        deterministic_fixes += _check_quiet_coverage(
            review_input.quiet_verdict, review_input.coverage_ran_clean
        )

        if deterministic_fixes:
            return QualityReview(
                tenant_id=review_input.tenant_id,
                run_id=review_input.run_id,
                review_type="pre-delivery",
                status=QualityReviewStatus.FAILED,
                findings=[{"source": "deterministic", "issue": f} for f in deterministic_fixes],
                required_fixes=[{"fix": f} for f in deterministic_fixes],
            )

        verdict = self._llm_reviewer.review(
            review_input.tenant_id,
            review_input.run_id,
            review_input.reader_text,
            review_input.claims,
        )

        llm_passed = bool(verdict.get("pass"))
        llm_fixes = list(verdict.get("required_fixes") or [])
        notes = verdict.get("notes")

        findings = [{"source": "llm", "issue": fix} for fix in llm_fixes]
        if notes:
            findings.append({"source": "llm", "note": notes})

        return QualityReview(
            tenant_id=review_input.tenant_id,
            run_id=review_input.run_id,
            review_type="pre-delivery",
            status=QualityReviewStatus.PASSED if llm_passed else QualityReviewStatus.FAILED,
            findings=findings,
            required_fixes=[{"fix": fix} for fix in llm_fixes],
        )
