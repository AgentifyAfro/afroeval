"""Console colour palette + a WCAG contrast helper.

Single source of truth for the console's accent / semantic colours so contrast
is measurable and can't silently regress (see tests/test_console_contrast.py).
Pure module — no Streamlit import — so it is safe to import from tests.

Backgrounds mirror .streamlit/config.toml. Accent/semantic colours are chosen to
clear WCAG AA on BG_SURFACE (the harder, card background) and AAA on BG_CANVAS.
"""

# ── Backgrounds ───────────────────────────────────────────────────────────────
BG_CANVAS = "#0A0A0F"
BG_SURFACE = "#1A1A24"
BORDER = "#2D2D3D"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT = "#FFFFFF"
TEXT_MUTED = "#C7CCDD"
TEXT_FAINT = "#A6ABC4"

# ── Accent / semantic ─────────────────────────────────────────────────────────
# Old values failed or only just cleared AA on the card background; these lift
# them clear. Ratios (fg on BG_SURFACE): LINK 6.34, SUCCESS 8.97, ERROR 6.24.
LINK = "#A78BFA"      # was #7C3AED (3.47:1 as small text — fail)
SUCCESS = "#34D399"   # was #10B981 (6.80:1 — AA)
ERROR = "#F87171"     # was #EF4444 (~4.3:1 on card)
WARNING = "#F59E0B"   # unchanged — already AAA on canvas (9.2:1)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 relative contrast ratio between two ``#RRGGBB`` colours (1.0–21.0)."""
    def _lin(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def _lum(h: str) -> float:
        h = h.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)
