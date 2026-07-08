"""Gate 4 LIVE acceptance run — certifies the brain against real evidence and
a real Claude model. No fakes: the model is ClaudeCliShimProvider talking to
the local `claude -p` shim (deploy/claude-shim/shim.py), and the evidence is
fetched live from public competitor blogs via HttpContentFetcher.

Certifies the acceptance criteria at docs/planning/CI-OS-Fable-build-goal-spec.md
line 116:
  (a) on a known-active day the system promotes real signals
  (b) quiet verdict only if coverage ran clean (else COVERAGE_FAILURE)
  (c) the FN auditor catches a planted miss
  (d) every published claim carries a source URL
  (e) a competitor thesis updates with evidence + confidence

Plus a bonus pass: the adversarial refute panel run live over the signals
promoted in (a), reporting survivors/kills.

Run: PRE-REQUISITE — the claude-shim must be up at 127.0.0.1:8663:
  uvicorn deploy.claude-shim.shim:app --app-dir . --port 8663 &
Then:
  python scripts/gate4_live_acceptance.py

Bounded: <=4 page fetches, <=15 LLM calls. Reports PASS/FAIL per criterion
with full evidence (signals JSON, quotes, URLs). If a criterion fails, this
script reports it honestly — it does not massage inputs to force a pass.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from cios.brain.fn_auditor import (
    FNSemanticLLMClient,
    PromotedSignalsProvider,
    RawObservationsProvider,
    SemanticFNAuditor,
)
from cios.brain.synthesizer import Synthesizer
from cios.brain.thesis import ThesisEngine
from cios.brain.types import CoverageReport, LaneStatus, SynthesisInput, Verdict
from cios.brain.verify_panel import VerifyPanel
from cios.collect.extract import semantic_diff
from cios.collect.fetcher import HttpContentFetcher
from cios.collect.types import SourceContext
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider
from cios.platform.models.types import ModelRequest

LLM_CALLS = {"count": 0}


class CountingModel:
    """Wraps a BrainModel to enforce the <=15 live-LLM-call budget."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def generate(self, request: ModelRequest):
        LLM_CALLS["count"] += 1
        if LLM_CALLS["count"] > 15:
            raise RuntimeError("LLM call budget (15) exceeded — aborting run")
        return await self._inner.generate(request)


REAL_SOURCES = [
    (1, "Elastic", "https://www.elastic.co/blog"),
    (2, "Coveo", "https://www.coveo.com/blog"),
    (3, "Constructor", "https://www.constructor.com/blog"),
    (4, "Bloomreach", "https://www.bloomreach.com/en/blog"),
]

RESULTS: list[tuple[str, bool, str]] = []


def record(criterion: str, passed: bool, detail: str) -> None:
    RESULTS.append((criterion, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"\n=== [{status}] {criterion} ===\n{detail}")


async def fetch_evidence() -> dict[str, tuple[SourceContext, list, list]]:
    """Fetch real pages (<=4) and run them through the real extraction layer.
    Returns competitor_name -> (source, facts, deltas)."""
    fetcher = HttpContentFetcher()
    out: dict[str, tuple[SourceContext, list, list]] = {}
    for competitor_id, name, url in REAL_SOURCES:
        result = fetcher.fetch_content(url)
        print(f"fetched {url}: status={result.status} http={result.http_status} chars={len(result.text)}")
        if result.status.value != "ok" or not result.text:
            print(f"  WARNING: fetch failed for {name}, skipping ({result.error})")
            continue
        source = SourceContext(competitor_id=competitor_id, competitor_name=name, url=url, source_type="blog", priority=2)
        facts, deltas = semantic_diff(source, "", result.text, "2026-07-08")
        out[name] = (source, facts, deltas)
    return out


def make_coverage(all_ran: bool) -> CoverageReport:
    if all_ran:
        return CoverageReport(
            lanes=[
                LaneStatus(lane="collection", ran=True, error=None),
                LaneStatus(lane="extraction", ran=True, error=None),
                LaneStatus(lane="exec_speech", ran=True, error=None),
            ]
        )
    return CoverageReport(
        lanes=[
            LaneStatus(lane="collection", ran=True, error=None),
            LaneStatus(lane="extraction", ran=False, error="collector timeout: blog scan did not complete"),
            LaneStatus(lane="exec_speech", ran=True, error=None),
        ]
    )


async def criterion_a_and_d(model, evidence) -> list[dict[str, Any]]:
    """(a) known-active-day promotion + (d) every published claim carries a
    source URL from the actual evidence set."""
    synthesizer = Synthesizer(model=model)
    all_promoted: list[dict[str, Any]] = []
    all_ok = True
    detail_lines = []

    # Use the two richest real competitors so this is a genuine "known active
    # day" (multiple sources, real deltas above the materiality floor).
    for name in ("Elastic", "Constructor"):
        if name not in evidence:
            detail_lines.append(f"{name}: SKIPPED (fetch unavailable)")
            continue
        source, facts, deltas = evidence[name]
        inp = SynthesisInput(
            tenant_id=1,
            competitor_id=source.competitor_id,
            competitor_name=name,
            deltas=deltas,
            facts=facts,
            exec_signals=[],
            prior_theses=[],
            coverage=make_coverage(all_ran=True),
        )
        result = await synthesizer.synthesize(inp)
        allowed_urls = inp.evidence_urls()
        detail_lines.append(
            f"{name}: verdict={result.verdict.value} signals={len(result.signals)} events={[e.event_type.value for e in result.events]}"
        )
        for s in result.signals:
            urls_ok = bool(s.evidence_urls) and all(u in allowed_urls for u in s.evidence_urls)
            all_ok = all_ok and urls_ok
            detail_lines.append(
                f"    SIGNAL: {s.headline!r} materiality={s.materiality_score} owner={s.owner} "
                f"evidence_urls={s.evidence_urls} urls_in_input={urls_ok}"
            )
            all_promoted.append({**s.model_dump(), "competitor_name": name})

    promoted_any = len(all_promoted) > 0
    record(
        "(a) known-active-day promotes real signals",
        promoted_any,
        "\n".join(detail_lines) + f"\n\nTotal promoted: {len(all_promoted)}",
    )
    record(
        "(d) every published claim carries a source URL present in input evidence",
        promoted_any and all_ok,
        f"all {len(all_promoted)} promoted signals carry >=1 evidence URL drawn from supplied input: {all_ok}",
    )
    return all_promoted


async def criterion_b(model) -> None:
    """(b) quiet verdict only if coverage ran clean — feed no evidence AND an
    incomplete coverage report, assert COVERAGE_FAILURE not QUIET."""
    synthesizer = Synthesizer(model=model)
    inp = SynthesisInput(
        tenant_id=1,
        competitor_id=99,
        competitor_name="NoEvidenceCo",
        deltas=[],
        facts=[],
        exec_signals=[],
        prior_theses=[],
        coverage=make_coverage(all_ran=False),
    )
    result = await synthesizer.synthesize(inp)
    passed = result.verdict == Verdict.COVERAGE_FAILURE
    record(
        "(b) COVERAGE_FAILURE (not QUIET) when coverage incomplete + no material deltas",
        passed,
        f"verdict={result.verdict.value} signals={len(result.signals)} events={[e.event_type.value for e in result.events]}",
    )


async def criterion_c(promoted_signals: list[dict[str, Any]]) -> None:
    """(c) FN auditor catches a planted miss. A fixture-marked observation is
    present in raw data but absent from the promoted set; the deterministic
    guard in SemanticFNAuditor must FAIL the run regardless of LLM opinion."""

    class StaticRaw(RawObservationsProvider):
        def get_observations(self, tenant_id: int, run_id: str) -> list[dict]:
            return [
                {
                    "headline": "Elastic quietly raised enterprise pricing 12% for AI search tier",
                    "fixture_marker": "PLANTED-PRICING-001",
                    "evidence_url": "https://www.elastic.co/blog",
                },
            ]

    class StaticPromoted(PromotedSignalsProvider):
        def get_promoted_signals(self, tenant_id: int, run_id: str) -> list[dict]:
            # The real promoted signals from criterion (a) — none carry the
            # planted fixture_marker, so the marker guard must trip.
            return promoted_signals

    class NeverCalledLLM(FNSemanticLLMClient):
        def find_missed_signal(self, tenant_id, run_id, raw_observations, promoted_signals) -> dict:
            raise AssertionError(
                "LLM auditor was called — the deterministic planted-marker guard "
                "should short-circuit before any LLM judgment is consulted"
            )

    auditor = SemanticFNAuditor(StaticRaw(), StaticPromoted(), NeverCalledLLM())
    audit = auditor.audit(tenant_id=1, run_id="live-gate4-run")
    passed = audit is not None and audit.audit_status.value == "failed" and "PLANTED-PRICING-001" in (audit.recommended_recheck or [])
    record(
        "(c) FN auditor catches a planted miss",
        passed,
        f"audit_status={audit.audit_status.value if audit else None} "
        f"risk_reason={audit.risk_reason if audit else None} "
        f"recommended_recheck={audit.recommended_recheck if audit else None}\n"
        "(LLM client was never invoked — deterministic guard fired first, confirming "
        "'a caught planted miss is never overridden by LLM judgment')",
    )


async def criterion_e(model, evidence) -> None:
    """(e) a competitor thesis updates with evidence + confidence, using a
    live model call to draft the thesis text grounded in real fetched facts."""
    if "Coveo" not in evidence:
        record("(e) thesis updates with evidence + confidence", False, "Coveo fetch unavailable, cannot run")
        return
    source, facts, deltas = evidence["Coveo"]
    if not facts:
        record("(e) thesis updates with evidence + confidence", False, "no real facts extracted for Coveo")
        return

    engine = ThesisEngine()
    first_fact = facts[0]
    opening_text = "Coveo is investing in AI-driven search content; initial monitoring thesis, low confidence pending more evidence."
    opening_confidence = 0.3
    opening = engine.open_thesis(
        tenant_id=1,
        competitor_id=source.competitor_id,
        thesis=opening_text,
        confidence=opening_confidence,
        evidence_ids=[first_fact.evidence_url],
    )
    # NOTE: `opening` is the SAME mutable object the engine stores and later
    # mutates in place via update() -- snapshot the pre-update values as
    # plain strings/floats now, not the object, or comparisons below would
    # silently compare the post-update state to itself.

    # Ground the updated thesis text in a second, distinct real fact via a
    # live judgment-tier call — this is the "evidence-backed claim" driving
    # the update, not scripted text.
    second_fact = facts[1] if len(facts) > 1 else first_fact
    prompt = (
        "You are Argus. Given this newly observed fact about competitor Coveo, "
        "write ONE sharp sentence (no em dashes) updating the strategic thesis "
        "about their competitive direction. Return ONLY the sentence, no JSON, no quotes.\n\n"
        f"FACT: {second_fact.statement}\nCONTEXT: {second_fact.evidence_text[:400]}\n"
    )
    request = ModelRequest(task_profile="brain.thesis_update", messages=[{"role": "user", "content": prompt}])
    response = await model.generate(request)
    new_thesis_text = (response.text or "").strip() or "Coveo continues to invest in AI search content narratives."

    updated = engine.update(
        competitor_id=source.competitor_id,
        thesis=new_thesis_text,
        confidence=0.55,
        new_evidence_ids=[second_fact.evidence_url],
    )

    passed = (
        len(updated.history) == 1
        and updated.history[0].thesis == opening_text
        and updated.history[0].confidence == opening_confidence
        and updated.confidence == 0.55
        and first_fact.evidence_url in updated.evidence_ids
        and second_fact.evidence_url in updated.evidence_ids
        and updated.thesis == new_thesis_text
        and updated.thesis != opening_text
    )
    record(
        "(e) competitor thesis updates with evidence + confidence, non-destructive history",
        passed,
        f"opening_thesis={opening_text!r} confidence={opening_confidence}\n"
        f"updated_thesis={updated.thesis!r} confidence={updated.confidence}\n"
        f"evidence_ids={updated.evidence_ids}\n"
        f"history_len={len(updated.history)} history[0]={updated.history[0].thesis!r}",
    )


async def bonus_refute_panel(model, promoted_signals: list[dict[str, Any]], evidence) -> None:
    """Bonus: run the live adversarial refute panel over the signals promoted
    in criterion (a). Not a numbered acceptance criterion but requested by
    the team lead as an extra live check."""
    if not promoted_signals:
        print("\n=== REFUTE PANEL: skipped (no promoted signals from step a) ===")
        return
    from cios.brain.types import Signal

    signals = [Signal(**{k: v for k, v in s.items() if k != "competitor_name"}) for s in promoted_signals]
    allowed_urls: set[str] = set()
    for name, (source, facts, deltas) in evidence.items():
        allowed_urls.update(d.evidence_urls[0] for d in deltas if d.evidence_urls)
        allowed_urls.update(f.evidence_url for f in facts if f.evidence_url)

    panel = VerifyPanel(model=model)
    report = await panel.run(signals, allowed_urls)
    print("\n=== REFUTE PANEL (live, bonus) ===")
    for v in report.verdicts:
        print(f"  {'SURVIVED' if v.passed else 'KNOCKED DOWN'}: {v.signal_headline!r} evidence_ok={v.evidence_ok} refute_held={v.refute_held} rebuttal={v.rebuttal!r}")
    print(f"Survivors: {report.survivors}")
    print(f"Knocked down: {report.knocked_down}")


async def main() -> int:
    provider = ClaudeCliShimProvider(model_alias="opus", timeout_s=90.0)
    model = CountingModel(provider)

    health = await provider.health_check()
    print(f"claude-shim health: healthy={health.healthy} detail={health.detail}")
    if not health.healthy:
        print("ABORT: claude-shim is not healthy; refusing to run a 'live' certification against a dead model.")
        return 2

    print("\n--- Fetching real evidence (live network) ---")
    evidence = await fetch_evidence()
    if not evidence:
        print("ABORT: no evidence fetched successfully; cannot run a live acceptance test with zero real data.")
        return 2

    promoted = await criterion_a_and_d(model, evidence)
    await criterion_b(model)
    await criterion_c(promoted)
    await criterion_e(model, evidence)
    await bonus_refute_panel(model, promoted, evidence)

    print(f"\nTotal live LLM calls used: {LLM_CALLS['count']} / 15 budget")

    print("\n\n================= VERDICT TABLE =================")
    all_pass = True
    for name, passed, _ in RESULTS:
        all_pass = all_pass and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print("===================================================")
    print(f"\nOVERALL: {'ALL CRITERIA PASSED' if all_pass else 'ONE OR MORE CRITERIA FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
