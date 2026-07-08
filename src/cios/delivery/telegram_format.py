"""Markdown-ish brief -> Telegram HTML (parse_mode=HTML safe subset).

V0 defect this fixes by design (Gate 6 mandate, manifesto §2): V0 stripped
formatting and sent a plain-text message plus an HTML file attachment
because the send layer never passed parse_mode="HTML". Here the MESSAGE
ITSELF is the rich brief -- render_brief_html() below is what
TelegramAdapter.send() puts in ResponseEnvelope.html_text.

Telegram's HTML parse mode supports a very small tag set:
https://core.telegram.org/bots/api#html-style -- b, i, u, s, a, code, pre
(+ a few others we do not use). Anything else must be escaped, including
raw '<', '>', '&' in body text, or Telegram rejects the whole message.

Splitting: the actual 4096-char hard split lives in
platform/channels/adapters/telegram.py (_split_html_text) since that is
where Telegram's limit is enforced at send time. This module exposes its
own section-aware splitter for callers (e.g. the commander) that want to
preview/validate chunk boundaries before handing off to the adapter, split
on section boundaries ("## " headings) in preference to mid-paragraph.
"""

from __future__ import annotations

import html
import re

TELEGRAM_HTML_LIMIT = 4096

# Safe tag allowlist per Telegram's HTML parse mode.
_ALLOWED_TAGS = {"b", "i", "u", "s", "a", "code", "pre"}

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def escape_html(text: str) -> str:
    """Escape everything so it is safe as HTML body text (not inside a tag)."""
    return html.escape(text, quote=False)


def markdown_to_telegram_html(markdown_text: str) -> str:
    """Convert a constrained markdown-ish subset to Telegram-safe HTML.

    Supported source markdown: **bold**, *italic*, `code`, [text](url).
    Everything else (including any literal HTML the source might contain,
    e.g. injected '<script>') is escaped first so it can never be
    interpreted as a tag -- injection-safe by construction.
    """
    escaped = escape_html(markdown_text)

    # Links first (so their escaped '(' / ')' don't confuse other patterns).
    def _link(match: "re.Match[str]") -> str:
        label, url = match.group(1), match.group(2)
        safe_url = html.escape(url, quote=True)
        return f'<a href="{safe_url}">{label}</a>'

    escaped = _LINK_RE.sub(_link, escaped)
    escaped = _INLINE_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _BOLD_RE.sub(lambda m: f"<b>{m.group(1)}</b>", escaped)
    escaped = _ITALIC_RE.sub(lambda m: f"<i>{m.group(1)}</i>", escaped)
    return escaped


def render_brief_html(title: str, body_markdown: str, dashboard_url: str | None = None) -> str:
    """Render a full Telegram-rich brief: bold title, formatted body, and an
    optional dashboard link -- the message itself is the brief."""
    parts = [f"<b>{escape_html(title)}</b>", "", markdown_to_telegram_html(body_markdown)]
    if dashboard_url:
        safe_url = html.escape(dashboard_url, quote=True)
        parts += ["", f'<a href="{safe_url}">View on the dashboard</a>']
    return "\n".join(parts)


def split_on_sections(html_text: str, limit: int = TELEGRAM_HTML_LIMIT) -> list[str]:
    """Split rendered HTML into <=limit chunks, preferring section
    boundaries (blank-line-separated blocks) over an arbitrary hard cut."""
    if len(html_text) <= limit:
        return [html_text]

    blocks = html_text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(block) <= limit:
            current = block
        else:
            for i in range(0, len(block), limit):
                chunks.append(block[i : i + limit])

    if current:
        chunks.append(current)

    return chunks
