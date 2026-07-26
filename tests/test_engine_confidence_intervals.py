"""Dimension confidence intervals on the scoring engine.

CIs are a descriptive add-on: they must appear in the result without perturbing
the composite/verdict, and must be absent for run-level and single-item dims.
"""

from scoring.engine import compute_composite_score


def test_cis_present_for_multi_item_dimension_and_bounded():
    raw = {
        "cultural_appropriateness": [0.8, 0.9, 0.7, 0.85],
        "language_performance":     [0.6, 0.62, 0.58, 0.61],
    }
    result = compute_composite_score(raw)
    cis = result.dimension_confidence_intervals
    assert "cultural_appropriateness" in cis
    lo, hi = cis["cultural_appropriateness"]
    score = result.dimension_scores["cultural_appropriateness"]
    # CI brackets the (flat) dimension score and stays within [0, 100].
    assert 0.0 <= lo <= score <= hi <= 100.0


def test_run_level_bias_dimension_has_no_ci():
    result = compute_composite_score({"bias_fairness": [0.9, 0.9, 0.9, 0.9]})
    assert "bias_fairness" not in result.dimension_confidence_intervals


def test_single_item_dimension_has_no_ci():
    result = compute_composite_score({"cultural_appropriateness": [0.8]})
    assert "cultural_appropriateness" not in result.dimension_confidence_intervals


def test_cis_do_not_perturb_dimension_scores():
    result = compute_composite_score({"cultural_appropriateness": [0.8, 0.9]})
    assert result.dimension_scores["cultural_appropriateness"] == 85.0
