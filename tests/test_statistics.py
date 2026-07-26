"""Unit tests for scoring.statistics.mean_ci_normal (dimension confidence intervals)."""

import pytest

from scoring.statistics import mean_ci_normal


def test_returns_none_for_fewer_than_two_values():
    assert mean_ci_normal([]) is None
    assert mean_ci_normal([0.5]) is None


def test_known_two_point_ci():
    # values [0.4, 0.6]: mean 0.5, sample std sqrt(0.02), SE 0.1, 95% CI 0.5 +/- 0.196
    lo, hi = mean_ci_normal([0.4, 0.6])
    assert lo == pytest.approx(0.304, abs=1e-3)
    assert hi == pytest.approx(0.696, abs=1e-3)


def test_zero_variance_gives_zero_width_ci():
    # A genuinely unanimous sample has a valid, zero-width CI — not None.
    lo, hi = mean_ci_normal([0.7, 0.7, 0.7])
    assert lo == hi                      # zero width
    assert lo == pytest.approx(0.7)


def test_z_is_configurable_and_widens_symmetrically():
    lo95, hi95 = mean_ci_normal([0.2, 0.8])
    lo99, hi99 = mean_ci_normal([0.2, 0.8], z=2.576)
    assert lo99 < lo95 and hi99 > hi95
    assert (lo95 + hi95) / 2 == pytest.approx(0.5)
    assert (lo99 + hi99) / 2 == pytest.approx(0.5)
