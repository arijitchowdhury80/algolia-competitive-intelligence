"""Cadence ladder: weekly pattern identification and monthly roll-up.

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md): daily digest
-> weekly (pattern identification + action plan over the week's daily
signals) -> monthly (roll-up of weeklies). Both weekly and monthly are
first-class pipeline outputs, not an afterthought bolted onto daily.

Same doctrine invariants as the daily Synthesizer (synthesizer.py):
  - evidence-or-silence: every pattern/action cites >=1 URL drawn only from
    the evidence already attached to the inputs reasoned over.
  - decision-layer-not-feed: every action plan item names a team_to_involve
    and a concrete action.
  - materiality-before-urgency, meaning-before-volume, no-fabrication: the
    same as daily. Weekly/monthly do not get a weaker bar than daily.

No DB, no network. The BrainModel and the ledger Protocols are injected
(house style: see thesis.py / claim_ledger.py for injected-repo Protocol
convention in this package).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional, Protocol

from pydantic import ValidationError

from cios.platform.models.types import ModelRequest

from .prompts import (
    MONTHLY_SYNTHESIS_SYSTEM,
    WEEKLY_SYNTHESIS_SYSTEM,
    build_monthly_synthesis_prompt,
    build_weekly_synthesis_prompt,
)
from .quality import extract_json_object
from .types import (
    BrainEvent,
    BrainEventType,
    BrainModel,
    CadenceActionItem,
    MonthlySynthesisResult,
    Pattern,
    Signal,
    Verdict,
    WeeklySynthesisResult,
)

logger = logging.getLogger("cios.brain.cadence")

VALID_TEAMS_TO_INVOLVE = {"Marketing", "Content", "Product", "Sales Enablement", "Executive"}
DEFAULT_MATERIALITY_FLOOR = 0.35
WEEKLY_TASK_PROFILE = "brain.weekly_synthesis"
MONTHLY_TASK_PROFILE = "brain.monthly_synthesis"


class MalformedCadenceOutput(RuntimeError):
    """Raised when the model returns unparseable/invalid JSON twice for a
    weekly or monthly pass. Fail loud rather than fabricate a rollup."""


class DailySignalLedger(Protocol):
    """Injected repo: the week's already-promoted daily signals for a
    competitor. No network/DB in this module -- the caller's repo maps this
    onto tenant-scoped DB rows."""

    def signals_for_week(self, tenant_id: int, competitor_id: int, week_start: date) -> list[Signal]: ...


class WeeklyResultLedger(Protocol):
    """Injected repo: prior weekly synthesis results for a competitor within
    a month, read by the monthly roll-up (never raw daily signals)."""

    def weeklies_for_month(
        self, tenant_id: int, competitor_id: int, month_start: date
    ) -> list[WeeklySynthesisResult]: ...


def _parse(response: Any) -> Optional[dict[str, Any]]:
    if getattr(response, "parsed_json", None):
        obj = response.parsed_json
        return obj if isinstance(obj, dict) else None
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        return None
    return extract_json_object(text)


def _vet_pattern(
    cand: Any, allowed_urls: set[str], events: list[BrainEvent], floor: float
) -> Optional[Pattern]:
    if not isinstance(cand, dict):
        events.append(
            BrainEvent(
                event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                detail="pattern candidate was not an object",
                payload={"candidate": str(cand)[:200]},
            )
        )
        return None

    urls = [u for u in (cand.get("evidence_urls") or []) if isinstance(u, str) and u]
    if not urls:
        events.append(
            BrainEvent(
                event_type=BrainEventType.EVIDENCE_REJECTED,
                detail="pattern promoted without any evidence URL",
                payload={"pattern": str(cand.get("pattern", ""))[:200]},
            )
        )
        return None

    fabricated = [u for u in urls if u not in allowed_urls]
    if fabricated:
        events.append(
            BrainEvent(
                event_type=BrainEventType.EVIDENCE_REJECTED,
                detail="pattern cited evidence URLs not present in the input",
                payload={"fabricated_urls": fabricated},
            )
        )
        return None

    try:
        score = float(cand.get("materiality_score"))
    except (TypeError, ValueError):
        score = 0.0

    if score < floor:
        events.append(
            BrainEvent(
                event_type=BrainEventType.MATERIALITY_SUPPRESSED,
                detail=f"pattern materiality {score:.3f} below floor {floor:.3f}",
                payload={"pattern": str(cand.get("pattern", ""))[:200], "score": score},
            )
        )
        return None

    try:
        return Pattern(
            pattern=(cand.get("pattern") or "").strip(),
            materiality_score=score,
            evidence_urls=urls,
        )
    except ValidationError as exc:
        events.append(
            BrainEvent(
                event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                detail="pattern candidate failed schema validation",
                payload={"error": str(exc)[:300]},
            )
        )
        return None


def _vet_action(
    cand: Any, allowed_urls: set[str], events: list[BrainEvent]
) -> Optional[CadenceActionItem]:
    if not isinstance(cand, dict):
        events.append(
            BrainEvent(
                event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                detail="action plan candidate was not an object",
                payload={"candidate": str(cand)[:200]},
            )
        )
        return None

    urls = [u for u in (cand.get("evidence_urls") or []) if isinstance(u, str) and u]
    if not urls:
        events.append(
            BrainEvent(
                event_type=BrainEventType.EVIDENCE_REJECTED,
                detail="action plan item promoted without any evidence URL",
                payload={"action": str(cand.get("action", ""))[:200]},
            )
        )
        return None

    fabricated = [u for u in urls if u not in allowed_urls]
    if fabricated:
        events.append(
            BrainEvent(
                event_type=BrainEventType.EVIDENCE_REJECTED,
                detail="action plan item cited evidence URLs not present in the input",
                payload={"fabricated_urls": fabricated},
            )
        )
        return None

    team = cand.get("team_to_involve") or ""
    action = (cand.get("action") or "").strip()
    if team not in VALID_TEAMS_TO_INVOLVE or not action:
        events.append(
            BrainEvent(
                event_type=BrainEventType.MATERIALITY_SUPPRESSED,
                detail="action plan item lacked a valid team_to_involve or action",
                payload={"team_to_involve": team},
            )
        )
        return None

    try:
        return CadenceActionItem(action=action, team_to_involve=team, evidence_urls=urls)
    except ValidationError as exc:
        events.append(
            BrainEvent(
                event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                detail="action plan candidate failed schema validation",
                payload={"error": str(exc)[:300]},
            )
        )
        return None


def _decide_verdict(patterns: list[Pattern], events: list[BrainEvent]) -> Verdict:
    # The weekly/monthly ladder has no lane-coverage concept of its own (it
    # reasons over already-certified daily/weekly outputs, whose own coverage
    # was already gated at that layer) -- so "nothing material" is always an
    # honest QUIET here, never a coverage failure.
    return Verdict.SIGNALS if patterns else Verdict.QUIET


class WeeklySynthesizer:
    """Pattern identification + action plan over one week's daily signal
    ledger for one competitor."""

    def __init__(
        self,
        model: BrainModel,
        ledger: DailySignalLedger,
        materiality_floor: float = DEFAULT_MATERIALITY_FLOOR,
    ) -> None:
        self._model = model
        self._ledger = ledger
        self._floor = materiality_floor

    async def synthesize(
        self, tenant_id: int, competitor_id: int, week_start: date
    ) -> WeeklySynthesisResult:
        signals = self._ledger.signals_for_week(tenant_id, competitor_id, week_start)
        allowed_urls = {u for s in signals for u in s.evidence_urls if u}
        events: list[BrainEvent] = []

        data_block = self._build_data_block(competitor_id, week_start, signals)
        raw = await self._call_model_with_retry(tenant_id, data_block, events)

        patterns = [
            p
            for cand in raw.get("patterns", [])
            if (p := _vet_pattern(cand, allowed_urls, events, self._floor)) is not None
        ]
        actions = [
            a
            for cand in raw.get("action_plan", [])
            if (a := _vet_action(cand, allowed_urls, events)) is not None
        ]

        return WeeklySynthesisResult(
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            week_start=week_start,
            verdict=_decide_verdict(patterns, events),
            patterns=patterns,
            action_plan=actions,
            events=events,
        )

    async def _call_model_with_retry(
        self, tenant_id: int, data_block: str, events: list[BrainEvent]
    ) -> dict[str, Any]:
        prompt = build_weekly_synthesis_prompt(data_block)
        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=WEEKLY_TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(tenant_id),
                messages=[
                    {"role": "system", "content": WEEKLY_SYNTHESIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = _parse(response)
            if parsed is not None:
                return parsed
            events.append(
                BrainEvent(
                    event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                    detail=f"attempt {attempt} returned unparseable JSON",
                    payload={"text": (response.text or "")[:500]},
                )
            )
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + build_weekly_synthesis_prompt(data_block)
            )
        raise MalformedCadenceOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )

    @staticmethod
    def _build_data_block(competitor_id: int, week_start: date, signals: list[Signal]) -> str:
        lines = [f"COMPETITOR id={competitor_id}", f"WEEK STARTING: {week_start.isoformat()}"]
        lines.append("\nDAILY SIGNALS THIS WEEK (already delivered; do not repeat, find the pattern):")
        if signals:
            for s in signals:
                lines.append(
                    f"  - [{s.signal_type}] {s.headline}: {s.what_changed}"
                    f" (owner={s.owner}; team={s.team_to_involve}; evidence={s.evidence_urls})"
                )
        else:
            lines.append("  (none)")
        urls = sorted({u for s in signals for u in s.evidence_urls if u})
        lines.append("\nEVIDENCE URLS (only cite from this list):")
        lines.extend(f"  - {u}" for u in urls) if urls else lines.append("  (none)")
        return "\n".join(lines)


class MonthlySynthesizer:
    """Rolls up a month's prior weekly synthesis results for one competitor
    (never raw daily signals)."""

    def __init__(
        self,
        model: BrainModel,
        ledger: WeeklyResultLedger,
        materiality_floor: float = DEFAULT_MATERIALITY_FLOOR,
    ) -> None:
        self._model = model
        self._ledger = ledger
        self._floor = materiality_floor

    async def synthesize(
        self, tenant_id: int, competitor_id: int, month_start: date
    ) -> MonthlySynthesisResult:
        weeklies = self._ledger.weeklies_for_month(tenant_id, competitor_id, month_start)
        allowed_urls = {
            u
            for w in weeklies
            for p in w.patterns
            for u in p.evidence_urls
            if u
        } | {
            u
            for w in weeklies
            for a in w.action_plan
            for u in a.evidence_urls
            if u
        }
        events: list[BrainEvent] = []

        data_block = self._build_data_block(competitor_id, month_start, weeklies)
        raw = await self._call_model_with_retry(tenant_id, data_block, events)

        patterns = [
            p
            for cand in raw.get("patterns", [])
            if (p := _vet_pattern(cand, allowed_urls, events, self._floor)) is not None
        ]
        actions = [
            a
            for cand in raw.get("action_plan", [])
            if (a := _vet_action(cand, allowed_urls, events)) is not None
        ]

        return MonthlySynthesisResult(
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            month_start=month_start,
            verdict=_decide_verdict(patterns, events),
            patterns=patterns,
            action_plan=actions,
            events=events,
        )

    async def _call_model_with_retry(
        self, tenant_id: int, data_block: str, events: list[BrainEvent]
    ) -> dict[str, Any]:
        prompt = build_monthly_synthesis_prompt(data_block)
        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=MONTHLY_TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(tenant_id),
                messages=[
                    {"role": "system", "content": MONTHLY_SYNTHESIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = _parse(response)
            if parsed is not None:
                return parsed
            events.append(
                BrainEvent(
                    event_type=BrainEventType.MALFORMED_LLM_OUTPUT,
                    detail=f"attempt {attempt} returned unparseable JSON",
                    payload={"text": (response.text or "")[:500]},
                )
            )
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + build_monthly_synthesis_prompt(data_block)
            )
        raise MalformedCadenceOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )

    @staticmethod
    def _build_data_block(
        competitor_id: int, month_start: date, weeklies: list[WeeklySynthesisResult]
    ) -> str:
        lines = [f"COMPETITOR id={competitor_id}", f"MONTH STARTING: {month_start.isoformat()}"]
        lines.append("\nWEEKLY REPORTS THIS MONTH (roll up, do not repeat a single week):")
        if weeklies:
            for w in weeklies:
                lines.append(f"  WEEK {w.week_start.isoformat()}:")
                for p in w.patterns:
                    lines.append(f"    - pattern: {p.pattern} (evidence={p.evidence_urls})")
                for a in w.action_plan:
                    lines.append(f"    - action: {a.action} (team={a.team_to_involve}; evidence={a.evidence_urls})")
        else:
            lines.append("  (none)")
        urls = sorted(
            {u for w in weeklies for p in w.patterns for u in p.evidence_urls if u}
            | {u for w in weeklies for a in w.action_plan for u in a.evidence_urls if u}
        )
        lines.append("\nEVIDENCE URLS (only cite from this list):")
        lines.extend(f"  - {u}" for u in urls) if urls else lines.append("  (none)")
        return "\n".join(lines)
