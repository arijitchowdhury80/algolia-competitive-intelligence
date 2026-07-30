"""argus-action-router + argus-delivery-commander (Gate 6).

See docs/planning/CI-OS-Fable-build-goal-spec.md Gate 6 and
docs/planning/Argus-project-manifesto.md Phase 8.
"""

from .packet_telegram_format import render_daily_packet_brief_html, render_weekly_packet_brief_html

__all__ = ["render_daily_packet_brief_html", "render_weekly_packet_brief_html"]
