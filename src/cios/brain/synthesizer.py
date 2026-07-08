"""Semantic synthesizer (argus-semantic-synthesizer) -- the delta -> materiality
-> signal pipeline that is the product's differentiator.

Flow:
  1. Build a DATA block from the cycle's deltas / facts / exec signals / prior
     theses and the coverage report.
  2. Ask the injected BrainModel for structured JSON (task_profile routes to
     the judgment tier -> Claude Opus via the router; skills never name a
     model). Parse and validate. On malformed output, retry ONCE with a
     stricter reminder. If still malformed, HARD FAIL -- never fabricate a
     result to look done (no silent fabrication).
  3. Enforce evidence-or-silence: a candidate signal with no evidence URL, or
     citing a URL not present in the supplied evidence set, is rejected and
     logged as a BrainEvent -- never promoted.
  4. Enforce materiality-before-urgency: candidates below the materiality floor
     are suppressed (logged), not promoted.
  5. Enforce coverage-before-quiet: if no material signal survives AND not every
     required lane ran clean, the verdict is COVERAGE_FAILURE (with an event),
     not QUIET. QUIET is only returned when coverage is provably complete.

No DB, no network. The BrainModel and the materiality floor are injected.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from cios.platform.models.types import ModelRequest

from .prompts import SYNTHESIS_SYSTEM, build_synthesis_prompt
from .types import (
    BrainEvent,
    BrainEventType,
    BrainModel,
    Signal,
    SynthesisInput,
    SynthesisResult,
    Verdict,
)

logger = logging.getLogger("cios.brain.synthesizer")

VALID_OWNERS = {"PMM", "Sales Enablement", "Product", "Executive Review"}
DEFAULT_MATERIALITY_FLOOR = 0.35
SYNTHESIS_TASK_PROFILE = "brain.synthesis"


class MalformedSynthesisOutput(RuntimeError):
    """Raised when the model returns unparseable/invalid JSON twice. We fail
    loud rather than emit a fabricated brief (evidence-or-silence extends to
    not inventing structure)."""


class Synthesizer:
    def __init__(
        self,
        model: BrainModel,
        materiality_floor: float = DEFAULT_MATERIALITY_FLOOR,
    ) -> None:
        self._model = model
        self._floor = materiality_floor

    async def synthesize(self, inp: SynthesisInput) -> SynthesisResult:
        events: list[BrainEvent] = []
        allowed_urls = inp.evidence_urls()

        raw = await self._call_model_with_retry(inp, events)
        candidates = raw.get("signals", [])
        if not isinstance(candidates, list):
            raise MalformedSynthesisOutput("'signals' is not a list")

        promoted: list[Signal] = []
        for cand in candidates:
            signal = self._vet_candidate(cand, inp, allowed_urls, events)
            if signal is not None:
                promoted.append(signal)

        verdict = self._decide_verdict(promoted, inp, events)
        return SynthesisResult(
            tenant_id=inp.tenant_id,
            competitor_id=inp.competitor_id,
            verdict=verdict,
            signals=promoted,
            events=events,
        )

    # -- internals ---------------------------------------------------------

    async def _call_model_with_retry(
        self, inp: SynthesisInput, events: list[BrainEvent]
    ) -> dict[str, Any]:
        data_block = self._build_data_block(inp)
        prompt = build_synthesis_prompt(data_block)

        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=SYNTHESIS_TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(inp.tenant_id),
                messages=[
                    {"role": "system", "content": SYNTHESIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = self._parse(response)
            if parsed is not None:
                return parsed

            events.append(
                BrainEvent(
                    event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                    detail=f"attempt {attempt} returned unparseable JSON",
                    payload={"text": (response.text or "")[:500]},
                )
            )
            # tighten the ask before the single retry.
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + build_synthesis_prompt(data_block)
            )

        raise MalformedSynthesisOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )

    @staticmethod
    def _parse(response: Any) -> Optional[dict[str, Any]]:
        # Prefer a provider that already parsed JSON for us.
        if getattr(response, "parsed_json", None):
            obj = response.parsed_json
            return obj if isinstance(obj, dict) else None
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            return None
        # Tolerate a fenced ```json block but nothing more creative.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        return obj if isinstance(obj, dict) else None

    def _vet_candidate(
        self,
        cand: Any,
        inp: SynthesisInput,
        allowed_urls: set[str],
        events: list[BrainEvent],
    ) -> Optional[Signal]:
        if not isinstance(cand, dict):
            events.append(
                BrainEvent(
                    event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                    detail="signal candidate was not an object",
                    payload={"candidate": str(cand)[:200]},
                )
            )
            return None

        urls = [u for u in (cand.get("evidence_urls") or []) if isinstance(u, str) and u]

        # evidence-or-silence: must cite >=1 URL, and every URL must be one we
        # actually supplied. A cited URL outside the evidence set is fabricated.
        if not urls:
            events.append(
                BrainEvent(
                    event_type=BrainEventType.EVIDENCE_REJECTED,
                    detail="signal promoted without any evidence URL",
                    payload={"headline": cand.get("headline", "")[:200]},
                )
            )
            return None

        fabricated = [u for u in urls if u not in allowed_urls]
        if fabricated:
            events.append(
                BrainEvent(
                    event_type=BrainEventType.EVIDENCE_REJECTED,
                    detail="signal cited evidence URLs not present in the input",
                    payload={"fabricated_urls": fabricated, "headline": cand.get("headline", "")[:200]},
                )
            )
            return None

        try:
            score = float(cand.get("materiality_score"))
        except (TypeError, ValueError):
            score = 0.0

        owner = cand.get("owner") or ""
        recommended_action = (cand.get("recommended_action") or "").strip()
        # decision-layer-not-feed: no owner or no action => not decision-grade.
        if owner not in VALID_OWNERS or not recommended_action:
            events.append(
                BrainEvent(
                    event_type=BrainEventType.MATERIALITY_SUPPRESSED,
                    detail="signal lacked a valid owner or recommended action",
                    payload={"owner": owner, "headline": cand.get("headline", "")[:200]},
                )
            )
            return None

        # materiality-before-urgency: below the floor is suppressed, not shipped.
        if score < self._floor:
            events.append(
                BrainEvent(
                    event_type=BrainEventType.MATERIALITY_SUPPRESSED,
                    detail=f"materiality {score:.3f} below floor {self._floor:.3f}",
                    payload={"headline": cand.get("headline", "")[:200], "score": score},
                )
            )
            return None

        try:
            confidence = cand.get("confidence")
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        try:
            return Signal(
                competitor_id=inp.competitor_id,
                signal_type=(cand.get("signal_type") or "unclassified"),
                headline=(cand.get("headline") or "").strip() or "(no headline)",
                what_changed=(cand.get("what_changed") or "").strip(),
                why_it_matters=cand.get("why_it_matters"),
                implication=cand.get("implication"),
                recommended_action=recommended_action,
                owner=owner,
                materiality_score=score,
                confidence=confidence,
                evidence_urls=urls,
            )
        except ValidationError as exc:  # defensive: schema drift in model output
            events.append(
                BrainEvent(
                    event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                    detail="signal candidate failed schema validation",
                    payload={"error": str(exc)[:300]},
                )
            )
            return None

    def _decide_verdict(
        self, promoted: list[Signal], inp: SynthesisInput, events: list[BrainEvent]
    ) -> Verdict:
        if promoted:
            return Verdict.SIGNALS
        # Nothing material survived. Quiet is only honest if coverage was clean.
        if inp.coverage.all_ran:
            return Verdict.QUIET
        events.append(
            BrainEvent(
                event_type=BrainEventType.COVERAGE_FAILURE,
                detail="no material signal, but not all required lanes ran; refusing to call it quiet",
                payload={"failed_lanes": inp.coverage.failed_lanes},
            )
        )
        return Verdict.COVERAGE_FAILURE

    @staticmethod
    def _build_data_block(inp: SynthesisInput) -> str:
        lines: list[str] = []
        lines.append(f"CLIENT COMPETITOR: {inp.competitor_name} (id={inp.competitor_id})")

        urls = sorted(inp.evidence_urls())
        lines.append("\nEVIDENCE URLS (only cite from this list):")
        lines.extend(f"  - {u}" for u in urls) if urls else lines.append("  (none)")

        lines.append("\nOBSERVED DELTAS:")
        if inp.deltas:
            for d in inp.deltas:
                lines.append(
                    f"  - [{d.delta_type}] {d.what_changed}"
                    f" (materiality~{d.materiality_score}; evidence={d.evidence_urls})"
                )
        else:
            lines.append("  (none)")

        lines.append("\nSEMANTIC FACTS:")
        if inp.facts:
            for f in inp.facts:
                lines.append(f"  - [{f.fact_type}] {f.statement} (evidence={f.evidence_url})")
        else:
            lines.append("  (none)")

        lines.append("\nEXECUTIVE / GTM SIGNALS:")
        if inp.exec_signals:
            for s in inp.exec_signals:
                quote = s.get("quote") or s.get("claim") or s.get("statement") or ""
                url = s.get("source_url") or s.get("evidence_url") or ""
                lines.append(f"  - {quote} (evidence={url})")
        else:
            lines.append("  (none)")

        lines.append("\nPRIOR THESES:")
        lines.extend(f"  - {t}" for t in inp.prior_theses) if inp.prior_theses else lines.append("  (none)")

        lines.append("\nCOVERAGE THIS CYCLE:")
        for lane in inp.coverage.lanes:
            state = "ran" if (lane.ran and not lane.error) else f"FAILED ({lane.error or 'did not run'})"
            lines.append(f"  - {lane.lane}: {state}")

        return "\n".join(lines)
