"""argus-delivery-commander: takes a certified report/brief and fans it out
to channels via the existing ChannelAdapter registry, recording delivery
state that reflects reality.

Gate 6 mandate (CI-OS-Fable-build-goal-spec.md, Argus-project-manifesto.md
Phase 8): fix bot_deliveries to record TRUE send state. V0 wrote a
bot_deliveries row regardless of whether the channel API actually accepted
the message and never advanced past 'queued_for_telegram'. Here a
BotDeliveryRecord only reaches SENT when the adapter's DeliveryResult says
success=True; every failure (including exhausting the retry budget) is
recorded FAILED with the adapter's error text, never silently dropped or
assumed successful.

Storage is via injected repository Protocols (in-memory fakes in tests, no
network) -- matches hunter/lifecycle.py conventions.
"""

from __future__ import annotations

from typing import Protocol

from cios.delivery.email_format import render_email_html
from cios.delivery.telegram_format import render_brief_html
from cios.delivery.types import (
    BotDeliveryRecord,
    BotDeliveryStatus,
    Cadence,
    DeliveryAttemptRecord,
    DeliveryAttemptStatus,
    DeliveryOutcome,
    DeliveryRequest,
    RecipientTarget,
    ReportReadyEvent,
    redact_recipient,
)
from cios.platform.channels.adapter import ChannelAdapter, NotSupported
from cios.platform.channels.types import Channel, DeliveryPolicy, DeliveryResult, ResponseEnvelope


class AdapterRegistry(Protocol):
    def get_adapter(self, channel: str) -> ChannelAdapter: ...


class BotDeliveryRepository(Protocol):
    def save(self, record: BotDeliveryRecord) -> BotDeliveryRecord: ...


class DeliveryAttemptRepository(Protocol):
    def save(self, record: DeliveryAttemptRecord) -> DeliveryAttemptRecord: ...


def _build_envelope(report: ReportReadyEvent, target: RecipientTarget) -> ResponseEnvelope:
    title = report.title or "CI-OS Brief"
    body_markdown = report.markdown_body or report.summary or ""

    if target.channel == Channel.TELEGRAM:
        html_text = render_brief_html(title, body_markdown, dashboard_url=report.dashboard_url)
        return ResponseEnvelope(
            recipient_user_id=target.recipient_user_id,
            channel=target.channel,
            thread_id=target.thread_id,
            text=body_markdown or title,
            html_text=html_text,
            classification=report.cadence.value,
        )

    if target.channel == Channel.EMAIL:
        html_text = render_email_html(title, body_markdown=body_markdown, dashboard_url=report.dashboard_url)
        return ResponseEnvelope(
            recipient_user_id=target.recipient_user_id,
            channel=target.channel,
            thread_id=target.thread_id,
            text=body_markdown or title,
            html_text=html_text,
            classification=title,
        )

    # Dashboard / other channels: plain envelope, adapter decides rendering.
    return ResponseEnvelope(
        recipient_user_id=target.recipient_user_id,
        channel=target.channel,
        thread_id=target.thread_id,
        text=body_markdown or title,
        classification=report.cadence.value,
        delivery_policy=DeliveryPolicy(),
    )


class DeliveryCommander:
    """Fans a report out to channels in fallback order, recording true state."""

    def __init__(
        self,
        adapters: AdapterRegistry,
        bot_deliveries: BotDeliveryRepository,
        delivery_attempts: DeliveryAttemptRepository,
    ) -> None:
        self._adapters = adapters
        self._bot_deliveries = bot_deliveries
        self._delivery_attempts = delivery_attempts

    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        """Attempt delivery to each target in plan.targets, in order, with
        bounded retries per channel. Stops at the first channel that
        confirms success. Every attempt -- success or failure -- is
        recorded before moving on."""
        outcome = DeliveryOutcome(
            tenant_id=request.tenant_id,
            report_id=request.report.report_id,
            delivered=False,
        )

        for target in request.plan.targets:
            bot_delivery, delivered = await self._attempt_channel(request, target, outcome)
            outcome.bot_deliveries.append(bot_delivery)
            if delivered:
                outcome.delivered = True
                outcome.delivered_channel = target.channel
                break

        return outcome

    async def _attempt_channel(
        self, request: DeliveryRequest, target: RecipientTarget, outcome: DeliveryOutcome
    ) -> tuple[BotDeliveryRecord, bool]:
        report = request.report
        bot_delivery = BotDeliveryRecord(
            tenant_id=request.tenant_id,
            cadence=report.cadence,
            channel=target.channel,
            recipient_redacted=redact_recipient(target.recipient_user_id),
            status=BotDeliveryStatus.SENDING,
            markdown_path=report.markdown_path,
            html_path=report.html_path,
            dashboard_url=report.dashboard_url,
            report_id=report.report_id,
            packet_id=report.packet_id,
            run_id=report.run_id,
        )
        bot_delivery = self._bot_deliveries.save(bot_delivery)

        last_error: str | None = None
        try:
            adapter = self._adapters.get_adapter(target.channel.value)
        except Exception as exc:  # noqa: BLE001 - unknown/unregistered channel is a real failure
            last_error = f"no adapter registered for channel {target.channel.value}: {exc}"
            failed = bot_delivery.model_copy(update={"status": BotDeliveryStatus.FAILED, "error": last_error})
            failed = self._bot_deliveries.save(failed)
            outcome.attempts.append(
                self._delivery_attempts.save(
                    DeliveryAttemptRecord(
                        tenant_id=request.tenant_id,
                        channel=target.channel,
                        status=DeliveryAttemptStatus.FAILED,
                        error=last_error,
                    )
                )
            )
            return failed, False

        envelope = _build_envelope(report, target)

        for _attempt_num in range(1, request.max_attempts_per_channel + 1):
            try:
                result: DeliveryResult = await adapter.send(envelope)
            except NotSupported as exc:
                last_error = f"adapter does not support send: {exc}"
                result = DeliveryResult(success=False, channel=target.channel, error=last_error)
            except Exception as exc:  # noqa: BLE001 - any adapter exception is a real send failure
                last_error = str(exc)
                result = DeliveryResult(success=False, channel=target.channel, error=last_error)

            attempt_status = DeliveryAttemptStatus.SENT if result.success else DeliveryAttemptStatus.FAILED
            outcome.attempts.append(
                self._delivery_attempts.save(
                    DeliveryAttemptRecord(
                        tenant_id=request.tenant_id,
                        channel=target.channel,
                        status=attempt_status,
                        delivery_ref=result.provider_message_id,
                        error=result.error,
                    )
                )
            )

            if result.success:
                sent = bot_delivery.model_copy(update={"status": BotDeliveryStatus.SENT, "error": None})
                sent = self._bot_deliveries.save(sent)
                return sent, True

            last_error = result.error or "adapter reported failure with no error detail"

        failed = bot_delivery.model_copy(update={"status": BotDeliveryStatus.FAILED, "error": last_error})
        failed = self._bot_deliveries.save(failed)
        return failed, False
