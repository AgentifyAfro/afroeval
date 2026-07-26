"""Descriptive statistics for scorecard reporting.

Kept separate from scoring.engine so the confidence-interval math is a small,
pure, independently-testable unit. Nothing here influences the composite score
or verdict — CIs are a descriptive statistic reported alongside the scores.
"""

import math
import statistics


def mean_ci_normal(values: list[float], z: float = 1.96) -> tuple[float, float] | None:
    """Normal-approximation confidence interval for the mean of ``values``.

    Returns ``(lo, hi)`` = ``mean +/- z * (sample_std / sqrt(n))`` in the same
    units as the input, or ``None`` when ``n < 2`` (standard error undefined).

    A zero-variance sample (every value identical) yields a valid zero-width
    interval ``(mean, mean)`` — that is an honest "measured, no spread" result,
    not a missing one. ``z`` defaults to 1.96 (95%); pass e.g. 2.576 for 99%.
    No clamping is applied here — the caller scales and clamps to its own range.
    """
    n = len(values)
    if n < 2:
        return None
    mean = statistics.fmean(values)
    std = statistics.stdev(values)  # sample std, ddof=1
    half_width = z * (std / math.sqrt(n))
    return (mean - half_width, mean + half_width)
