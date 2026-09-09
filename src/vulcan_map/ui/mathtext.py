"""LaTeX -> PNG data URI via matplotlib mathtext.

Node docs are LaTeX-heavy and Qt has no maths renderer. mathtext needs no TeX
installation, which keeps the tool portable — full TeX quality is unnecessary
for a side panel.
"""

from __future__ import annotations

import base64
import io
import re
import subprocess
import sys
from functools import lru_cache

_DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_RE = re.compile(r"(?<!\$)\$([^$\n]+?)\$(?!\$)")

# Rasterising one glyph exercises the whole Agg + FreeType path, which is where
# a broken matplotlib build fails.
_PROBE = (
    "import io, matplotlib; matplotlib.use('Agg');"
    "from matplotlib.figure import Figure;"
    "f = Figure(figsize=(0.1, 0.1)); f.text(0, 0, 'x');"
    "f.savefig(io.BytesIO(), format='png')"
)


@lru_cache(maxsize=1)
def available() -> bool:
    """Whether matplotlib can actually rasterise text in this environment.

    Some builds abort the *process* inside `savefig` — a FreeType or font-cache
    failure below the Python layer — which no try/except can catch. Probing once
    in a subprocess contains that: a crash costs a subprocess, not the UI. Without
    this, clicking a node whose doc contains maths would take down the window.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            capture_output=True,
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


@lru_cache(maxsize=256)
def render_latex(expr: str, fontsize: int = 13, colour: str = "#d8dee9") -> str | None:
    """Return an <img> data URI for `expr`, or None if it will not render."""
    if not available():
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib.figure import Figure
    except Exception:
        return None

    try:
        fig = Figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0.0)
        fig.text(0, 0, f"${expr}$", fontsize=fontsize, color=colour)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    pad_inches=0.02, transparent=True)
    except Exception:
        # Malformed maths must not take the panel down; the raw source is shown.
        return None

    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def substitute(markdown: str, *, colour: str = "#d8dee9") -> str:
    """Replace $$...$$ and $...$ with rendered images where possible."""

    def display(m: re.Match[str]) -> str:
        uri = render_latex(m.group(1).strip(), 15, colour)
        if uri is None:
            return f"<pre>{m.group(1).strip()}</pre>"
        return f'<div style="margin:12px 0;"><img src="{uri}" style="max-width:100%;"></div>'

    def inline(m: re.Match[str]) -> str:
        uri = render_latex(m.group(1).strip(), 11, colour)
        if uri is None:
            return f"<code>{m.group(1).strip()}</code>"
        return f'<img src="{uri}" style="vertical-align:middle;">'

    return _INLINE_RE.sub(inline, _DISPLAY_RE.sub(display, markdown))
