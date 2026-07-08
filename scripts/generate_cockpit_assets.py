"""Regenerates src/cios/dashboard/_cockpit_assets.py from the source PNGs in
docs/mockups/assets/.

The cockpit HTML is a self-contained document (see cockpit_renderer.py
module docstring): it can be written to any path on any host and must still
render its brand imagery, so image references cannot be relative file paths
into docs/mockups/assets/ (that directory does not travel with the rendered
HTML). This script resizes + recompresses the mockup's source images to fit
comfortably under the renderer's 300KB-per-asset inline budget, base64
encodes them, and writes them as Python constants that cockpit_renderer.py
imports directly -- no image processing happens at render time.

Run this only when the source PNGs in docs/mockups/assets/ change:
    python3 scripts/generate_cockpit_assets.py
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "docs" / "mockups" / "assets"
OUT_PATH = REPO_ROOT / "src" / "cios" / "dashboard" / "_cockpit_assets.py"

INLINE_BUDGET_BYTES = 300 * 1024


def _logo_data_uri() -> str:
    """Logo mark: resized to 200x200, kept as PNG to preserve the alpha
    channel (JPEG would flatten transparency onto an opaque background)."""
    img = Image.open(ASSETS_DIR / "argus-logo-mark.png").convert("RGBA")
    img = img.resize((200, 200), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    assert len(data) <= INLINE_BUDGET_BYTES, f"logo asset still {len(data)} bytes after resize"
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _hero_data_uri() -> str:
    """Hero editorial image: no transparency needed, so JPEG at a
    resolution/quality that keeps it under budget while staying sharp at the
    visual-story panel's rendered size (max ~430px tall)."""
    img = Image.open(ASSETS_DIR / "argus-search-intelligence-weekly.png").convert("RGB")
    max_dim = 900
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    data = b""
    for quality in (85, 78, 70, 62, 54, 46, 38, 30):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= INLINE_BUDGET_BYTES:
            break
    assert len(data) <= INLINE_BUDGET_BYTES, f"hero asset still {len(data)} bytes after compression"
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode('ascii')}"


def main() -> None:
    logo_uri = _logo_data_uri()
    hero_uri = _hero_data_uri()
    OUT_PATH.write_text(
        '"""Auto-generated inline asset data URIs for cockpit_renderer.py.\n'
        "Regenerate with scripts/generate_cockpit_assets.py if the source PNGs in\n"
        "docs/mockups/assets/ change. Each constant is a complete data: URI, resized\n"
        "and recompressed to stay under the 300KB inline budget -- see\n"
        'cockpit_renderer\'s module docstring for why these are inlined instead of\n'
        'referenced by path.\n"""\n\n'
        f'LOGO_DATA_URI = "{logo_uri}"\n\n'
        f'HERO_IMAGE_DATA_URI = "{hero_uri}"\n',
        encoding="utf-8",
    )
    print(f"wrote {OUT_PATH} (logo {len(logo_uri)} chars, hero {len(hero_uri)} chars)")


if __name__ == "__main__":
    main()
