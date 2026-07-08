"""The dot-connector: ties this week's signals to standing horizon trends.

Doctrine (Addendum 2 point 1): "Argus connects the dots... brings in what
is interesting and helpful" across the industry, not just a feed. This is
the module that produces the actual connection: "this week's X connects to
the 30-day trend Y", citing BOTH the current signal's evidence and the
horizon observation's evidence.

No DB, no network. BrainModel is injected (cios.brain.types.BrainModel). The
evidence guard is deterministic and runs regardless of what the model
claims: a candidate connection citing any URL not present in the caller-
supplied allowed sets is rejected outright, not trimmed or repaired.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import ValidationError

from cios.brain.quality import extract_json_object
from cios.brain.types import BrainModel, Signal
from cios.horizon.types import DotConnection, Horizon, HorizonRead
from cios.platform.models.types import ModelRequest

logger = logging.getLogger("cios.horizon.connector")

TASK_PROFILE = "horizon.dot_connector"

CONNECTOR_SYSTEM = """\
You are Argus, the dot-connector. You are given this week's signals for a
company's own CMO and marketing leadership, plus standing multi-horizon
industry reads (10/30/60 day lookbacks). Your job is to say, plainly,
whether any of this week's signals connect to a wider trend the company has
already been tracking -- "this week's X connects to the 30-day trend Y" --
and why that connection matters. You are skeptical and evidence-led. You
never invent a connection that is not supported by both sides of the
evidence you were given.

Hard rules:
1. Evidence or silence. Every connection MUST cite at least one evidence URL
   from the current signal AND at least one evidence URL from the horizon
   read it connects to. Both must come only from the URLS supplied below.
2. No forced connections. If nothing this week meaningfully connects to a
   standing horizon read, return an empty list. A thin or generic connection
   is worse than no connection.
3. No em dashes. Plain sentences.
4. Name the horizon explicitly (d10, d30, or d60) for every connection you
   propose, matching one of the horizons supplied below.

Return ONLY a JSON object of this shape:
{
  "connections": [
    {
      "horizon": "d10" | "d30" | "d60",
      "connection": "string",
      "signal_evidence_urls": ["url", ...],
      "horizon_evidence_urls": ["url", ...]
    }, ...
  ]
}
"""


class MalformedConnectorOutput(RuntimeError):
    """Raised when the model returns unparseable/invalid JSON twice."""


def _parse(response: Any) -> Optional[dict[str, Any]]:
    if getattr(response, "parsed_json", None):
        obj = response.parsed_json
        return obj if isinstance(obj, dict) else None
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        return None
    return extract_json_object(text)


def _horizon_evidence_urls(read: HorizonRead) -> set[str]:
    return {u for theme in read.themes for u in theme.evidence_urls if u}


def _vet_connection(
    cand: Any,
    tenant_id: int,
    signal_urls: set[str],
    horizon_urls_by_horizon: dict[Horizon, set[str]],
) -> Optional[DotConnection]:
    if not isinstance(cand, dict):
        return None
    try:
        horizon = Horizon(cand.get("horizon"))
    except ValueError:
        return None
    connection_text = (cand.get("connection") or "").strip()
    if not connection_text:
        return None

    proposed_signal_urls = [
        u for u in (cand.get("signal_evidence_urls") or []) if isinstance(u, str) and u
    ]
    proposed_horizon_urls = [
        u for u in (cand.get("horizon_evidence_urls") or []) if isinstance(u, str) and u
    ]

    # Deterministic guard: reject any connection citing evidence outside the
    # caller-supplied allowed sets -- run unconditionally, never trusting the
    # model's own claim about what it grounded the connection in.
    valid_signal_urls = [u for u in proposed_signal_urls if u in signal_urls]
    if len(valid_signal_urls) != len(proposed_signal_urls) or not valid_signal_urls:
        return None

    allowed_horizon_urls = horizon_urls_by_horizon.get(horizon, set())
    valid_horizon_urls = [u for u in proposed_horizon_urls if u in allowed_horizon_urls]
    if len(valid_horizon_urls) != len(proposed_horizon_urls) or not valid_horizon_urls:
        return None

    try:
        return DotConnection(
            tenant_id=tenant_id,
            horizon=horizon,
            connection=connection_text,
            signal_evidence_urls=valid_signal_urls,
            horizon_evidence_urls=valid_horizon_urls,
        )
    except ValidationError:
        return None


class DotConnector:
    """Given standing HorizonReads plus this week's signals, produces
    DotConnection items linking the two -- each citing both sides' evidence.
    """

    def __init__(self, model: BrainModel) -> None:
        self._model = model

    async def connect(
        self,
        tenant_id: int,
        signals: list[Signal],
        horizon_reads: list[HorizonRead],
    ) -> list[DotConnection]:
        if not signals or not horizon_reads:
            return []

        signal_urls = {u for s in signals for u in s.evidence_urls if u}
        horizon_urls_by_horizon = {read.horizon: _horizon_evidence_urls(read) for read in horizon_reads}
        if not signal_urls or not any(horizon_urls_by_horizon.values()):
            return []

        data_block = self._build_data_block(signals, horizon_reads)
        raw = await self._call_model_with_retry(tenant_id, data_block)

        connections = [
            c
            for cand in raw.get("connections", [])
            if (
                c := _vet_connection(cand, tenant_id, signal_urls, horizon_urls_by_horizon)
            )
            is not None
        ]
        return connections

    async def _call_model_with_retry(self, tenant_id: int, data_block: str) -> dict[str, Any]:
        prompt = (
            "Read this week's signals and the standing horizon reads below, "
            "then produce the JSON object described in the system "
            "instructions.\n\n" + data_block
        )
        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(tenant_id),
                messages=[
                    {"role": "system", "content": CONNECTOR_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = _parse(response)
            if parsed is not None:
                return parsed
            logger.warning("dot-connector attempt %d returned unparseable JSON", attempt)
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + prompt
            )
        raise MalformedConnectorOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )

    @staticmethod
    def _build_data_block(signals: list[Signal], horizon_reads: list[HorizonRead]) -> str:
        lines = ["THIS WEEK'S SIGNALS:"]
        for s in signals:
            lines.append(
                f"  - [{s.signal_type}] {s.headline}: {s.what_changed}"
                f" (evidence={s.evidence_urls})"
            )
        for read in horizon_reads:
            lines.append(f"\nHORIZON {read.horizon.value} (as of {read.as_of.isoformat()}):")
            if read.notable_movements:
                lines.append("  Notable movements:")
                lines.extend(f"    - {m}" for m in read.notable_movements)
            if read.themes:
                lines.append("  Themes:")
                for theme in read.themes:
                    lines.append(
                        f"    - {theme.theme} [{theme.confidence.value}]"
                        f" (evidence={theme.evidence_urls})"
                    )
            if not read.notable_movements and not read.themes:
                lines.append("  (nothing notable)")
        return "\n".join(lines)
