"""Adversarial verify panel (Gate 4) -- the last gate before a signal is
trusted. Two independent verifiers per signal:

  1. Evidence-URL audit (deterministic): every cited URL must be present in the
     supplied evidence set and the signal must cite at least one. This repeats
     the synthesizer's guarantee at the gate so a signal that somehow arrived
     with a fabricated or missing URL is caught here too (defense in depth).
  2. Refute pass (LLM, injected): a hostile reviewer tries to knock the signal
     down. A signal only holds if it survives.

A signal passes the panel only when BOTH verifiers pass. The panel returns a
report; it never mutates or silently drops signals -- the caller decides what
to do with a failed verdict (suppress, downgrade, escalate to human).

The planted-miss / false-negative half of the panel lives in fn_auditor.py
(SemanticFNAuditor). This module is the refute + evidence-audit half. No DB or
network; the model is injected (fake in tests).
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field

from cios.platform.models.types import ModelRequest

from .prompts import REFUTE_SYSTEM
from .types import BrainModel, Signal


class SignalVerdict(BaseModel):
    signal_headline: str
    evidence_ok: bool
    refute_held: bool
    rebuttal: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.evidence_ok and self.refute_held


class PanelReport(BaseModel):
    verdicts: list[SignalVerdict] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(v.passed for v in self.verdicts)

    @property
    def survivors(self) -> list[str]:
        return [v.signal_headline for v in self.verdicts if v.passed]

    @property
    def knocked_down(self) -> list[str]:
        return [v.signal_headline for v in self.verdicts if not v.passed]


REFUTE_TASK_PROFILE = "brain.refute"


class VerifyPanel:
    def __init__(self, model: BrainModel) -> None:
        self._model = model

    async def run(self, signals: list[Signal], allowed_urls: set[str]) -> PanelReport:
        verdicts = [await self._verify_one(s, allowed_urls) for s in signals]
        return PanelReport(verdicts=verdicts)

    async def _verify_one(self, signal: Signal, allowed_urls: set[str]) -> SignalVerdict:
        reasons: list[str] = []

        # 1. deterministic evidence-URL audit.
        urls = [u for u in signal.evidence_urls if u]
        evidence_ok = True
        if not urls:
            evidence_ok = False
            reasons.append("no evidence URL")
        else:
            fabricated = [u for u in urls if u not in allowed_urls]
            if fabricated:
                evidence_ok = False
                reasons.append(f"evidence URLs not in input: {fabricated}")

        # 2. refute pass. Only worth spending a model call if evidence holds;
        # a signal with bad evidence is already dead.
        refute_held = False
        rebuttal: Optional[str] = None
        if evidence_ok:
            refute_held, rebuttal = await self._refute(signal)
            if not refute_held:
                reasons.append("did not survive refute pass")
        else:
            reasons.append("refute skipped: evidence audit already failed")

        return SignalVerdict(
            signal_headline=signal.headline,
            evidence_ok=evidence_ok,
            refute_held=refute_held,
            rebuttal=rebuttal,
            reasons=reasons,
        )

    async def _refute(self, signal: Signal) -> tuple[bool, Optional[str]]:
        payload = (
            f"SIGNAL: {signal.headline}\n"
            f"WHAT CHANGED: {signal.what_changed}\n"
            f"WHY IT MATTERS: {signal.why_it_matters or ''}\n"
            f"RECOMMENDED ACTION: {signal.recommended_action}\n"
            f"MATERIALITY: {signal.materiality_score}\n"
            f"EVIDENCE: {signal.evidence_urls}\n"
        )
        request = ModelRequest(
            task_profile=REFUTE_TASK_PROFILE,
            capability_needs=["needs_json_mode"],
            messages=[
                {"role": "system", "content": REFUTE_SYSTEM},
                {"role": "user", "content": payload},
            ],
        )
        response = await self._model.generate(request)
        parsed = None
        if getattr(response, "parsed_json", None):
            parsed = response.parsed_json
        else:
            try:
                parsed = json.loads((response.text or "").strip())
            except (json.JSONDecodeError, ValueError):
                parsed = None
        # Fail closed: an unparseable refute verdict is treated as "did not
        # survive" rather than waved through (never trust silence).
        if not isinstance(parsed, dict):
            return False, "refute verdict unparseable; failing closed"
        return bool(parsed.get("holds")), parsed.get("rebuttal")
