"""argus-gated-delivery-commander: the only path that may turn a
QualityReview into an actual channel send.

Gate 7 rehearsal finding (docs/planning/gate7-rehearsal-runs/2026-07-08-run.md,
Critical finding #1): DeliveryCommander and QualityReviewer ran independently,
so every tenant delivered despite a FAILED quality verdict. The manifesto
(Phase 6) is explicit: a failed quality verdict must never ship.

Fix at the root: DeliveryCommander itself never learns about quality
verdicts -- it only knows how to fan a report out to channels. Bolting an
`if verdict.status == PASSED` check onto call sites is exactly how this bug
happened the first time (nothing stopped a caller from skipping the check).
Instead, GatedDeliveryCommander is the only object that exposes a `deliver`
taking a `QualityReview`, and it is the only production entry point wired
into the delivery layer -- DeliveryCommander.deliver() itself has no
verdict parameter and is not meant to be called directly from a report-ready
handler; it is an implementation detail this class delegates to once the
verdict is confirmed PASSED. `quality_verdict` is a required positional
argument typed as `QualityReview` (not `Optional`), so a caller that has no
verdict yet cannot compile a call that skips the gate -- there is no default
to fall back on and no legal way to pass "no verdict."

On a non-PASSED verdict: zero adapter calls are made; one BLOCKED
bot_deliveries row is recorded per planned target (so the ledger states, per
channel, that a send was withheld rather than attempted); and a learning
event carrying required_fixes is emitted via the injected recorder Protocol.
"""

from __future__ import annotations

from typing import Protocol

from cios.delivery.commander import AdapterRegistry, BotDeliveryRepository, DeliveryAttemptRepository, DeliveryCommander
from cios.delivery.types import (
    BotDeliveryRecord,
    BotDeliveryStatus,
    DeliveryOutcome,
    DeliveryRequest,
    redact_recipient,
)
from cios.learn.types import QualityReview, QualityReviewStatus


class LearningEventRecorder(Protocol):
    """Narrow extension point matching cios.learn.recorder.LearningRecorder's
    record_quality_verdict signature -- injected so this module never talks
    to a repository directly."""

    def record_quality_verdict(self, tenant_id: int, review: QualityReview) -> object: ...


def _blocked_reason(quality_verdict: QualityReview) -> str:
    fixes = [str(fix) for fix in quality_verdict.required_fixes]
    if fixes:
        return "quality review failed: " + "; ".join(fixes)
    return f"quality review status was '{quality_verdict.status.value}', not 'passed'"


class GatedDeliveryCommander:
    """Wraps DeliveryCommander behind a mandatory quality-verdict check.

    A caller with a reviewable brief and no verdict simply cannot construct
    a valid call: `deliver()` requires a `QualityReview` argument, and only
    a `PASSED` verdict is forwarded to the underlying commander.
    """

    def __init__(
        self,
        adapters: AdapterRegistry,
        bot_deliveries: BotDeliveryRepository,
        delivery_attempts: DeliveryAttemptRepository,
        recorder: LearningEventRecorder,
    ) -> None:
        self._bot_deliveries = bot_deliveries
        self._recorder = recorder
        self._inner = DeliveryCommander(
            adapters=adapters,
            bot_deliveries=bot_deliveries,
            delivery_attempts=delivery_attempts,
        )

    async def deliver(self, request: DeliveryRequest, quality_verdict: QualityReview) -> DeliveryOutcome:
        if quality_verdict.status != QualityReviewStatus.PASSED:
            return self._deliver_blocked(request, quality_verdict)
        return await self._inner.deliver(request)

    def _deliver_blocked(self, request: DeliveryRequest, quality_verdict: QualityReview) -> DeliveryOutcome:
        report = request.report
        reason = _blocked_reason(quality_verdict)

        outcome = DeliveryOutcome(
            tenant_id=request.tenant_id,
            report_id=report.report_id,
            delivered=False,
        )

        for target in request.plan.targets:
            blocked = BotDeliveryRecord(
                tenant_id=request.tenant_id,
                cadence=report.cadence,
                channel=target.channel,
                recipient_redacted=redact_recipient(target.recipient_user_id),
                status=BotDeliveryStatus.BLOCKED,
                markdown_path=report.markdown_path,
                html_path=report.html_path,
                dashboard_url=report.dashboard_url,
                report_id=report.report_id,
                error=reason,
            )
            outcome.bot_deliveries.append(self._bot_deliveries.save(blocked))

        self._recorder.record_quality_verdict(request.tenant_id, quality_verdict)

        return outcome
