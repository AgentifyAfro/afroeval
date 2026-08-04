"""Radar / spider chart for the scorecard dimensions (five scored since v1.8 + the
code-switching diagnostic; the renderer is data-driven off the card's own dimensions).

One geometry core (`radar_geometry`) feeds two dependency-free renderers so the
PDF (ReportLab vector shapes) and the console (inline SVG) draw an identical
chart. No matplotlib/plotly.

Geometry uses a math convention: center at the origin, +y is up, the first axis
points straight up, and axes proceed clockwise. Each renderer maps that into its
own canvas (SVG is y-down; ReportLab is y-up).
"""

import math
from dataclasses import dataclass

# Short axis labels for the canonical dimension ids (fallback = the id itself).
DIMENSION_LABELS: dict[str, str] = {
    "language_performance":     "Language",
    "cultural_appropriateness": "Cultural",
    "hallucination_risk":       "Hallucination",
    "bias_fairness":            "Bias",
    "code_switching_quality":   "Code-Switch",
    "safety_robustness":        "Safety",
}

# Theme palettes. "light" is tuned for the off-white PDF page; "dark" for the
# console canvas (#0A0A0F) where the light labels/grid would otherwise be
# invisible (see tests/test_console_contrast.py). fill = (r, g, b, alpha).
RADAR_THEMES: dict[str, dict] = {
    "light": {"grid": "#C7CCDD", "axis": "#A6ABC4", "label": "#33384A",
              "stroke": "#4169E1", "fill": (0, 207, 255, 0.22)},
    "dark":  {"grid": "#3A3A4C", "axis": "#4A4A5E", "label": "#C7CCDD",
              "stroke": "#00CFFF", "fill": (0, 207, 255, 0.20)},
}


def _rgba(fill: tuple) -> str:
    r, g, b, a = fill
    return f"rgba({r},{g},{b},{a})"


@dataclass
class RadarAxis:
    key: str                        # raw dimension id (renderers map to a display label)
    score: float
    angle_deg: float
    endpoint: tuple[float, float]   # axis end at full radius (label anchor)
    vertex: tuple[float, float]     # score-scaled point on the axis


@dataclass
class RadarGeometry:
    center: tuple[float, float]
    radius: float
    axes: list[RadarAxis]
    rings: list[float]              # absolute ring radii, inner -> outer

    @property
    def polygon(self) -> list[tuple[float, float]]:
        return [a.vertex for a in self.axes]


def radar_geometry(
    scores: dict[str, float],
    *,
    radius: float = 100.0,
    max_score: float = 100.0,
    ring_fractions: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0),
) -> RadarGeometry:
    """Compute axis endpoints, score vertices and ring radii for a radar chart.

    Center is the origin; the first axis points up (+y) and axes go clockwise.
    """
    n = len(scores)
    axes: list[RadarAxis] = []
    for i, (key, raw) in enumerate(scores.items()):
        angle_deg = 90.0 - i * (360.0 / n)      # top, then clockwise
        rad = math.radians(angle_deg)
        ux, uy = math.cos(rad), math.sin(rad)
        frac = 0.0 if max_score <= 0 else max(0.0, min(1.0, raw / max_score))
        axes.append(RadarAxis(
            key=key,
            score=raw,
            angle_deg=angle_deg,
            endpoint=(radius * ux, radius * uy),
            vertex=(radius * frac * ux, radius * frac * uy),
        ))
    rings = [radius * f for f in ring_fractions]
    return RadarGeometry(center=(0.0, 0.0), radius=radius, axes=axes, rings=rings)


def _fmt(x: float) -> str:
    return f"{x:.2f}"


def radar_svg(
    scores: dict[str, float], *, size: int = 320, max_score: float = 100.0, theme: str = "light"
) -> str:
    """Render the radar as a self-contained inline SVG string (console)."""
    t = RADAR_THEMES[theme]
    cx = cy = size / 2
    r = size / 2 * 0.64
    g = radar_geometry(scores, radius=r, max_score=max_score)

    def to_screen(pt: tuple[float, float]) -> tuple[float, float]:
        return cx + pt[0], cy - pt[1]            # SVG y is down -> flip

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}" role="img" aria-label="Dimension radar chart">'
    ]

    # concentric polygon rings
    for ring_r in g.rings:
        pts = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (to_screen((ring_r * math.cos(math.radians(a.angle_deg)),
                                    ring_r * math.sin(math.radians(a.angle_deg))))
                         for a in g.axes)
        )
        parts.append(f'<polygon points="{pts}" fill="none" stroke="{t["grid"]}" stroke-width="1"/>')

    # axes + labels
    for a in g.axes:
        ex, ey = to_screen(a.endpoint)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                     f'stroke="{t["axis"]}" stroke-width="1"/>')
        lx, ly = to_screen((a.endpoint[0] * 1.16, a.endpoint[1] * 1.16))
        anchor = "middle" if abs(a.endpoint[0]) < 1e-6 else ("start" if a.endpoint[0] > 0 else "end")
        label = DIMENSION_LABELS.get(a.key, a.key)
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="11" fill="{t["label"]}" '
                     f'text-anchor="{anchor}" dominant-baseline="middle" '
                     f'font-family="Inter, Segoe UI, system-ui, sans-serif">{label}</text>')

    # score polygon
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (to_screen(v) for v in g.polygon))
    parts.append(f'<polygon points="{poly}" fill="{_rgba(t["fill"])}" '
                 f'stroke="{t["stroke"]}" stroke-width="2"/>')
    for v in g.polygon:
        x, y = to_screen(v)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{t["stroke"]}"/>')

    parts.append("</svg>")
    return "".join(parts)


def radar_drawing(scores: dict[str, float], *, size: int = 220, max_score: float = 100.0, theme: str = "light"):
    """Render the radar as a ReportLab Drawing (PDF flowable). PDF is off-white → light theme."""
    from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, String
    from reportlab.lib import colors

    t = RADAR_THEMES[theme]
    cx = cy = size / 2
    r = size / 2 * 0.62
    g = radar_geometry(scores, radius=r, max_score=max_score)
    d = Drawing(size, size)

    def to_canvas(pt: tuple[float, float]) -> tuple[float, float]:
        return cx + pt[0], cy + pt[1]            # ReportLab y is up

    grid = colors.HexColor(t["grid"])
    axis = colors.HexColor(t["axis"])
    stroke = colors.HexColor(t["stroke"])
    _fr, _fg, _fb, _fa = t["fill"]
    fill = colors.Color(_fr / 255, _fg / 255, _fb / 255, alpha=_fa)
    label_color = colors.HexColor(t["label"])

    for ring_r in g.rings:
        pts: list[float] = []
        for a in g.axes:
            x, y = to_canvas((ring_r * math.cos(math.radians(a.angle_deg)),
                              ring_r * math.sin(math.radians(a.angle_deg))))
            pts += [x, y]
        d.add(Polygon(points=pts, strokeColor=grid, strokeWidth=0.75, fillColor=None))

    for a in g.axes:
        ex, ey = to_canvas(a.endpoint)
        d.add(Line(cx, cy, ex, ey, strokeColor=axis, strokeWidth=0.75))
        lx, ly = to_canvas((a.endpoint[0] * 1.14, a.endpoint[1] * 1.14))
        anchor = "middle" if abs(a.endpoint[0]) < 1e-6 else ("start" if a.endpoint[0] > 0 else "end")
        label = DIMENSION_LABELS.get(a.key, a.key)
        d.add(String(lx, ly - 3, label, fontSize=7.5, fillColor=label_color, textAnchor=anchor))

    poly: list[float] = []
    for v in g.polygon:
        x, y = to_canvas(v)
        poly += [x, y]
    d.add(Polygon(points=poly, strokeColor=stroke, strokeWidth=1.5, fillColor=fill))
    for v in g.polygon:
        x, y = to_canvas(v)
        d.add(Circle(x, y, 1.8, strokeColor=stroke, fillColor=stroke))

    return d
