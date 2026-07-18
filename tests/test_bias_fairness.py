"""
Tests for CohortDisparityEvaluator's real Fairlearn-backed disparate-impact
computation.

These exercise compute_run_disparity() directly (the run-level method) since
that's where the real logic lives. evaluate() (the per-item BaseEvaluator
method) is a degenerate pass-through tested separately at the bottom.
"""

from evaluators.bias_fairness import CohortDisparityEvaluator


def test_clean_parity_scores_near_one():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 9 + [False] + [True] * 9 + [False]  # 90% pass rate, both cohorts
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension == "bias_fairness"
    assert result.metric_name == "cohort_disparity"


def test_disparity_at_threshold_is_scored_continuously():
    evaluator = CohortDisparityEvaluator()
    # formal=1.0, informal=0.85 -> ratio 0.85. v1.2 clamped this to 1.0.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 17 + [False] * 3
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.85) < 1e-9
    assert result.passed is True  # 0.85 >= 0.80


def test_disparity_below_threshold_is_scored_continuously():
    evaluator = CohortDisparityEvaluator()
    # formal=1.0, informal=0.65 -> ratio 0.65. v1.2 scored 0.65/0.80 = 0.8125.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 13 + [False] * 7
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.65) < 1e-9
    assert result.passed is False


def test_severe_disparity_scores_low_without_a_floor_cliff():
    evaluator = CohortDisparityEvaluator()
    # formal=1.0, informal=0.30 -> ratio 0.30. v1.2 hard-zeroed anything below 0.50.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 6 + [False] * 14
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.30) < 1e-9
    assert result.passed is False


def test_language_axis_governs_when_worse_than_cohort():
    evaluator = CohortDisparityEvaluator()
    # cohort axis: formal 0.75, informal 0.75 -> ratio 1.0 (parity)
    # language axis: sw 1.0, am 0.5           -> ratio 0.5 (the real gap)
    # (needs 2+ obs/cell to decouple the axes: with only 1 obs/cell in a 2x2
    # cohort x language grid, a single flipped outcome forces identical
    # disparity on both axes by symmetry, so parity-on-one/gap-on-the-other
    # is not representable with 4 items. Repeated 3x so every cohort and every
    # language clears MIN_GROUP_SIZE=5 and both axes qualify.)
    cohorts = (["formal"] * 4 + ["informal_economy"] * 4) * 3
    languages = ["sw", "sw", "am", "am"] * 6
    outcomes = [True, True, True, False] * 6
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert abs(result.score - 0.5) < 1e-9
    assert result.passed is False
    assert "0.500" in result.reason and "1.000" in result.reason


def test_cohort_axis_governs_when_worse_than_language():
    evaluator = CohortDisparityEvaluator()
    # 6 items per cohort and per language so both axes clear MIN_GROUP_SIZE=5.
    cohorts = ["formal"] * 6 + ["informal_economy"] * 6
    languages = ["sw", "am"] * 6
    outcomes = [True] * 6 + [False] * 6  # cohort ratio 0.0, language ratio 1.0
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert result.score == 0.0
    assert result.passed is False


def test_score_is_continuous_above_threshold():
    evaluator = CohortDisparityEvaluator()
    # formal 1.0, informal 0.9 -> ratio 0.90. Old code clamped this to 1.0.
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 10 + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.90) < 1e-9
    assert result.passed is True  # 0.90 >= 0.80


def test_single_language_axis_is_ignored_not_fatal():
    evaluator = CohortDisparityEvaluator()
    # only one language -> that axis does not qualify; cohort axis still scores.
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    languages = ["sw"] * 20
    outcomes = [True] * 10 + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert abs(result.score - 0.90) < 1e-9
    assert result.applicable is True


def test_neither_axis_qualifies_is_not_applicable():
    evaluator = CohortDisparityEvaluator()
    result = evaluator.compute_run_disparity(["formal"] * 4, [True] * 4, languages=["sw"] * 4)
    assert result.applicable is False
    assert "insufficient" in result.reason.lower()


def test_languages_argument_is_optional():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 10 + [True] * 9 + [False]
    score_without_languages = evaluator.compute_run_disparity(cohorts, outcomes).score
    score_with_none_languages = evaluator.compute_run_disparity(
        cohorts, outcomes, languages=None
    ).score
    assert score_without_languages == score_with_none_languages
    assert abs(score_without_languages - 0.90) < 1e-9


def test_language_axis_alone_qualifies_when_cohort_does_not():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 20
    languages = ["sw"] * 10 + ["am"] * 10
    outcomes = [True] * 10 + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert result.applicable is True
    assert abs(result.score - 0.90) < 1e-9
    assert "cohort axis: not measured" in result.reason


def test_axis_ratio_raises_on_labels_outcomes_length_mismatch():
    import pytest

    from evaluators.bias_fairness import _axis_ratio

    with pytest.raises(ValueError):
        _axis_ratio(["formal", "informal_economy", "formal"], [True, False])


def test_reason_names_both_axes_and_the_governing_one():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 6 + ["informal_economy"] * 6
    languages = ["sw", "am"] * 6
    outcomes = [True] * 11 + [False]
    reason = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages).reason
    assert "language" in reason.lower()
    assert "cohort" in reason.lower()
    assert "governing" in reason.lower()


def test_fewer_than_two_cohorts_is_not_applicable():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10
    outcomes = [True, False] * 5
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.applicable is False
    assert "insufficient" in result.reason.lower()


def test_blank_cohorts_are_dropped_before_grouping():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + [""] * 10  # blank labels don't form a real group
    outcomes = [True] * 10 + [False] * 10
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    # after dropping blanks, only "formal" remains -> not applicable, not a neutral 100%
    assert result.applicable is False
    assert "insufficient" in result.reason.lower()


def test_unexpected_cohort_label_is_grouped_like_any_other():
    evaluator = CohortDisparityEvaluator()
    # "agent" isn't a documented cohort, but the grouping is data-driven.
    cohorts = ["formal"] * 10 + ["agent"] * 10
    outcomes = [True] * 10 + [False] * 10  # formal=1.0, agent=0.0 -> ratio=0.0
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 0.0
    assert result.passed is False
    assert "agent" in result.reason


def test_evaluate_single_item_is_not_applicable():
    evaluator = CohortDisparityEvaluator()
    result = evaluator.evaluate(
        prompt="p",
        model_response="r",
        expected_behavior="e",
        context={"cohort": "formal"},
    )
    assert result.applicable is False
    assert result.dimension == "bias_fairness"
    assert result.metric_name == "cohort_disparity"


def test_cohort_disparity_reason_is_ascii_safe():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    languages = ["sw"] * 10 + ["am"] * 10  # exercise the two-axis reason, not just cohort
    outcomes = [True] * 9 + [False] + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    result.reason.encode("ascii")  # raises UnicodeEncodeError if non-ASCII chars present

    # not-applicable reason interpolates languages too - lock that path as well.
    na = evaluator.compute_run_disparity(["formal"] * 10, [True] * 10, languages=["sw"] * 10)
    assert na.applicable is False
    na.reason.encode("ascii")


def test_group_below_min_size_is_excluded_from_the_ratio():
    evaluator = CohortDisparityEvaluator()
    # "agent" (n=2) fails everything; if it counted, the ratio would be 0.0.
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10 + ["agent"] * 2
    outcomes = [True] * 20 + [False] * 2
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 1.0  # formal 1.0 vs informal 1.0, agent excluded
    assert result.passed is True


def test_small_legacy_cohort_no_longer_zeroes_the_dimension():
    evaluator = CohortDisparityEvaluator()
    # The real-corpus scenario: both `agent` items fail, everything else passes.
    cohorts = (
        ["informal_economy"] * 107 + ["formal"] * 34 + ["informal_rural"] * 4 + ["agent"] * 2
    )
    outcomes = [c != "agent" for c in cohorts]
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score > 0.0
    assert result.score == 1.0  # only formal + informal_economy qualify, both at 1.0
    assert result.applicable is True


def test_axis_reduced_below_two_qualifying_groups_stops_qualifying():
    evaluator = CohortDisparityEvaluator()
    # cohort axis: formal n=10 qualifies, agent n=3 excluded -> 1 group left -> skipped.
    # language axis still qualifies, so the run is scored on language alone.
    cohorts = ["formal"] * 10 + ["agent"] * 3
    languages = ["sw"] * 6 + ["am"] * 7
    outcomes = [True] * 12 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert result.applicable is True
    assert "cohort axis: not measured" in result.reason
    assert result.extra["cohort_ratio"] is None
    assert result.extra["language_ratio"] is not None


def test_excluded_groups_are_named_in_the_reason_and_extra():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10 + ["agent"] * 2
    outcomes = [True] * 20 + [False] * 2
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert "agent" in result.reason
    assert "n=2" in result.reason
    assert "below the 5-item minimum" in result.reason
    assert result.extra["excluded_groups"]["cohort"] == {"agent": 2}
    result.reason.encode("ascii")


def test_extra_carries_both_ratios_and_the_governing_axis():
    evaluator = CohortDisparityEvaluator()
    # cohort parity (1.0), language gap (0.5) -> language governs.
    cohorts = (["formal"] * 4 + ["informal_economy"] * 4) * 3
    languages = ["sw", "sw", "am", "am"] * 6
    outcomes = [True, True, True, False] * 6
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert result.extra["governing_axis"] == "language"
    assert abs(result.extra["governing_ratio"] - 0.5) < 1e-9
    assert abs(result.extra["language_ratio"] - 0.5) < 1e-9
    assert abs(result.extra["cohort_ratio"] - 1.0) < 1e-9
    assert set(result.extra["per_group_selection_rate"]) == {"cohort", "language"}
    assert set(result.extra["per_group_selection_rate"]["language"]) == {"sw", "am"}


def test_extra_is_json_serialisable():
    import json

    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10 + ["agent"] * 2
    languages = ["sw"] * 11 + ["am"] * 11
    outcomes = [True] * 20 + [False] * 2
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    json.dumps(result.extra)  # extra is persisted to a JSON column


def test_threshold_is_rendered_with_two_decimals():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 10 + [True] * 9 + [False]
    reason = evaluator.compute_run_disparity(cohorts, outcomes).reason
    assert "threshold >=0.80" in reason


def test_cohort_disparity_result_is_single_output():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 20
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    from evaluators.base import MetricOutput
    assert isinstance(result, MetricOutput)
    assert result.metric_name == "cohort_disparity"
