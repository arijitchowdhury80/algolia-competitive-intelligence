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

import json
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

# Quoted spans (>=4 chars inside straight or curly double quotes) and
# specific figures (currency amounts, percentages) that a claim asserts as
# fact -- these are exactly the things a reader can verify against the
# source, so they are exactly what evidence-or-silence should check.
QUOTE_SPAN_PATTERN = re.compile(r'["“]([^"”]{4,})["”]')
FIGURE_PATTERN = re.compile(r"\$\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?%")

# first standalone JSON object in a blob of text (fenced or with leading
# prose), used both here and by the synthesizer so both places tolerate the
# same shapes of "almost JSON" model output.


def extract_json_object(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from an LLM reply. Tolerates
    a ```json fenced block, leading/trailing prose around the object, or a
    bare object. Returns None (never raises) if nothing parseable is found."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    # fall back to the first {...} block -- handles leading prose the model
    # added despite being asked for JSON only.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(stripped[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class Claim(Protocol):
    """Structural shape a reviewed claim must have -- duck-typed so callers
    can pass their own synthesis dataclasses without importing this module's
    types into the synthesizer."""

    text: str
    source_url: Optional[str]


class ReviewInput(Protocol):
    """Structural shape of what gets reviewed: a batch of claims plus the
    reader-facing text and the quiet-verdict/coverage flags needed for the
    'quiet day requires healthy coverage' check (manifesto + eval plan).

    `evidence_texts` maps source URL -> the fetched source snapshot text, so
    the deterministic quote-verification check (and the LLM reviewer) can
    confirm a quoted string or figure in a claim actually appears in the
    source, not just that a URL was cited. Callers that cannot supply it
    (or don't need the extra rigor) may omit the attribute; it is read via
    getattr with an empty-dict default, so the check is skipped rather than
    failing closed."""

    tenant_id: int
    run_id: Optional[str]
    claims: list[Claim]
    reader_text: str
    quiet_verdict: bool
    coverage_ran_clean: bool
    evidence_texts: dict[str, str]


class UnparseableVerdict(RuntimeError):
    """Raised by a QualityLLMReviewer implementation when the model's reply
    could not be parsed into a verdict. QualityReviewer retries once with a
    corrective re-prompt (mirrors Synthesizer._call_model_with_retry's
    malformed-JSON retry); only after a second failure does it fail closed
    itself -- never fabricate a passing verdict to look done."""


class QualityLLMReviewer(Protocol):
    """Extension point for the LLM half of the review (voice, materiality,
    hallucination sniff) -- called via src/cios/platform/models/router.py's
    quality tier in production. Returns a structured verdict; tests inject
    a fake.

    `evidence_texts` (URL -> source text, truncated per-source by the
    caller) lets the LLM check quotes against the source rather than just
    demanding a citation exists. `attempt` is 1 on the first call and 2 on
    the retry after an UnparseableVerdict, so an implementation can
    strengthen its prompt ("return ONLY JSON") the second time, the same
    pattern the synthesizer uses."""

    def review(
        self,
        tenant_id: int,
        run_id: Optional[str],
        reader_text: str,
        claims: list[Claim],
        evidence_texts: dict[str, str],
        attempt: int = 1,
    ) -> dict:
        """Must return {"pass": bool, "required_fixes": list[str], "notes": str},
        or raise UnparseableVerdict if the model's reply could not be parsed."""
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


def _check_quotes_verbatim(claims: list[Claim], evidence_texts: dict[str, str]) -> list[str]:
    """A claim that quotes a string or cites a specific figure must have
    that text appear, verbatim (modulo whitespace/case), in the evidence
    text for its cited source. Without an evidence corpus we cannot verify
    this deterministically, so the check is a no-op rather than a false
    failure -- it only runs when the caller supplies `evidence_texts`."""
    if not evidence_texts:
        return []
    fixes: list[str] = []
    for claim in claims:
        text = getattr(claim, "text", "") or ""
        spans: list[str] = [m.group(1) for m in QUOTE_SPAN_PATTERN.finditer(text)]
        spans += [m.group(0) for m in FIGURE_PATTERN.finditer(text)]
        if not spans:
            continue
        url = getattr(claim, "source_url", None)
        source_text = _normalize_text(evidence_texts.get(url, "")) if url else ""
        for span in spans:
            if _normalize_text(span) not in source_text:
                snippet = text[:80]
                fixes.append(
                    f"quote not found verbatim in source: '{span}' (claim: '{snippet}')"
                )
    return fixes


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
        evidence_texts = getattr(review_input, "evidence_texts", None) or {}

        deterministic_fixes: list[str] = []
        deterministic_fixes += _check_claim_sources(review_input.claims)
        deterministic_fixes += _check_em_dashes(review_input.reader_text)
        deterministic_fixes += _check_banned_phrases(review_input.reader_text)
        deterministic_fixes += _check_quotes_verbatim(review_input.claims, evidence_texts)
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

        if review_input.quiet_verdict and not review_input.claims and review_input.coverage_ran_clean:
            return QualityReview(
                tenant_id=review_input.tenant_id,
                run_id=review_input.run_id,
                review_type="pre-delivery",
                status=QualityReviewStatus.PASSED,
                findings=[{"source": "deterministic", "note": "quiet verdict with clean coverage and no claims"}],
                required_fixes=[],
            )

        verdict: Optional[dict] = None
        unparseable_error: Optional[UnparseableVerdict] = None
        for attempt in (1, 2):
            try:
                verdict = self._llm_reviewer.review(
                    review_input.tenant_id,
                    review_input.run_id,
                    review_input.reader_text,
                    review_input.claims,
                    evidence_texts,
                    attempt=attempt,
                )
                unparseable_error = None
                break
            except UnparseableVerdict as exc:
                unparseable_error = exc
                continue

        if verdict is None:
            # Both the initial call and the corrective retry came back
            # unparseable. Fail closed ourselves -- never fabricate a pass
            # to look done (evidence-or-silence extends to verdicts too).
            fix = "quality reviewer returned an unparseable verdict twice; failing closed"
            return QualityReview(
                tenant_id=review_input.tenant_id,
                run_id=review_input.run_id,
                review_type="pre-delivery",
                status=QualityReviewStatus.FAILED,
                findings=[{"source": "llm", "issue": fix, "note": str(unparseable_error)}],
                required_fixes=[{"fix": fix}],
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
