"""Tests for reporting.radar — shared radar geometry + SVG/ReportLab renderers."""

import math

import pytest

from reporting.radar import radar_drawing, radar_geometry, radar_svg

DIMS = {
    "language_performance":     80.0,
    "cultural_appropriateness": 100.0,
    "hallucination_risk":       0.0,
    "bias_fairness":            60.0,
    "code_switching_quality":   40.0,
    "safety_robustness":        90.0,
}


def test_one_axis_per_dimension_in_input_order():
    g = radar_geometry(DIMS, radius=100.0)
    assert [a.key for a in g.axes] == list(DIMS)
    assert len(g.axes) == 6


def test_full_score_reaches_radius_and_zero_sits_at_center():
    g = radar_geometry(DIMS, radius=100.0, max_score=100.0)
    by = {a.key: a for a in g.axes}
    cx, cy = g.center
    d_full = math.hypot(*(v - c for v, c in zip(by["cultural_appropriateness"].vertex, (cx, cy))))
    d_zero = math.hypot(*(v - c for v, c in zip(by["hallucination_risk"].vertex, (cx, cy))))
    assert d_full == pytest.approx(100.0)
    assert d_zero == pytest.approx(0.0)


def test_first_axis_points_straight_up():
    # Math convention (y up): the first axis endpoint is at the top of the chart.
    g = radar_geometry(DIMS, radius=100.0)
    x, y = g.axes[0].endpoint
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(100.0)


def test_svg_is_well_formed_and_draws_the_score_polygon():
    svg = radar_svg(DIMS, size=320)
    assert svg.lstrip().startswith("<svg")
    assert "</svg>" in svg
    assert "<polygon" in svg  # the score polygon


def test_reportlab_drawing_is_non_empty():
    d = radar_drawing(DIMS, size=220)
    assert d.width > 0 and d.height > 0
    assert len(d.contents) > 0
