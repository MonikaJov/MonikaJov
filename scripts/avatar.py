"""
ASCII avatar — the decorative art panel rendered beside the stats card.

To use your own art:
  1. Replace assets/fox-dark.txt and assets/fox-light.txt with your own
     ASCII art (one file per theme, same characters, same dimensions).
  2. Update PALETTE below so each frozenset covers the characters that
     should share a colour.  Characters not matched fall back to FALLBACK.

PALETTE structure:
  { "dark": { frozenset("chars"): "#hexcolor", ... },
    "light": { frozenset("chars"): "#hexcolor", ... } }

The art files use heavier characters (e.g. @, #, %) for dark areas and
lighter ones (e.g. ., :, -) for bright areas.  On a dark background the
heavy chars should be the lightest/brightest colours (they represent lit
fur); on a light background they should be the darkest (they represent
shadow/markings).
"""

import os

# ── Colour palette ────────────────────────────────────────────────────────────

PALETTE = {
    "dark": {
        # on dark bg → fox glows; heaviest chars are brightest highlights
        frozenset('@%#' ): "#FFF4D0",   # near-white gold — highlights
        frozenset('+'   ): "#FFCC60",   # golden yellow
        frozenset('='   ): "#FFA040",   # vivid orange — main fur
        frozenset('.:- *'): "#E06828",  # warm orange-brown — shadow
    },
    "light": {
        # on light bg → fox has depth; heaviest chars are darkest markings
        frozenset('@%'  ): "#2C1500",   # deep brown — darkest markings
        frozenset('#'   ): "#6E2A0A",   # dark reddish-brown
        frozenset('-=*' ): "#B04015",   # burnt orange — main fur
        frozenset('.:+' ): "#C8955A",   # warm tan — highlights
    },
}

FALLBACK = "#FFA040"   # colour for any character not matched by PALETTE

# ── Helpers ───────────────────────────────────────────────────────────────────

def _xe(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def get_color(ch: str, theme: str, bg: str) -> str:
    """Return the SVG fill colour for a single ASCII character."""
    if ch == " ":
        return bg
    for chars, color in PALETTE[theme].items():
        if ch in chars:
            return color
    return FALLBACK


def load(path: str) -> list:
    """Load ASCII art from *path*, stripping trailing whitespace and blank lines."""
    if not os.path.exists(path):
        return []
    lines = [line.rstrip() for line in open(path, encoding="utf-8")]
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def render(
    lines: list,
    theme: str,
    bg: str,
    *,
    pad: int   = 6,
    ix: int    = 10,
    line_h: int = 15,
    font_size: float = 14,
    font: str  = "'Courier New', Courier, monospace",
) -> str:
    """
    Render ASCII art lines as SVG <text> elements with per-character colouring.

    Consecutive characters that share a colour are grouped into a single
    <tspan> to keep the output compact.  Returns an SVG fragment (no wrapper)
    ready to embed directly inside an <svg> element.

    Parameters
    ----------
    lines     : list of strings from load()
    theme     : "dark" or "light"
    bg        : background hex colour (used for space characters)
    pad       : x offset of the art panel in pixels
    ix        : top padding — y of the first row = ix + line_h
    line_h    : vertical distance between rows in pixels
    font_size : monospace font size in px (must match the font's char width)
    font      : CSS font-family string
    """
    parts = []
    for i, line in enumerate(lines):
        y      = ix + (i + 1) * line_h
        groups: list = []
        for ch in line:
            col = get_color(ch, theme, bg)
            if groups and groups[-1][0] == col:
                groups[-1][1] += ch
            else:
                groups.append([col, ch])
        inner = "".join(
            f'<tspan fill="{col}">{_xe(text)}</tspan>'
            for col, text in groups
        )
        parts.append(
            f'<text x="{pad}" y="{y}" font-family="{font}" '
            f'font-size="{font_size}" xml:space="preserve">{inner}</text>'
        )
    return "".join(parts)
