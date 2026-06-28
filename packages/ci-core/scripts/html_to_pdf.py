#!/usr/bin/env python3
"""Small dependency-free HTML-to-PDF fallback for CI report delivery.

This is intentionally plain. It creates a valid text PDF when richer renderers
such as Playwright, WeasyPrint, or wkhtmltopdf are not available in the Hermes
container.
"""

import html
import re
import sys
import textwrap
from pathlib import Path


def html_to_text(source: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", source)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|section|article|h1|h2|h3|li|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf_bytes(title: str, text: str) -> bytes:
    lines = [title, ""]
    for paragraph in text.splitlines():
        wrapped = textwrap.wrap(paragraph, width=92) or [""]
        lines.extend(wrapped)
    lines = lines[:58]
    stream_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
    for line in lines:
        stream_lines.append("(%s) Tj" % pdf_escape(line[:120]))
        stream_lines.append("T*")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(("%d 0 obj\n" % idx).encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(("xref\n0 %d\n" % (len(objects) + 1)).encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(("%010d 00000 n \n" % offset).encode("ascii"))
    output.extend(
        (
            "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref_at)
        ).encode("ascii")
    )
    return bytes(output)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: html_to_pdf.py input.html output.pdf", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    text = html_to_text(source.read_text(errors="replace"))
    title_match = re.search(r"(?is)<title>(.*?)</title>", source.read_text(errors="replace"))
    title = html_to_text(title_match.group(1)) if title_match else source.stem
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(simple_pdf_bytes(title, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
