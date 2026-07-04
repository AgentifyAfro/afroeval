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


def test_disparity_at_threshold_clamps_to_full_score():
    evaluator = CohortDisparityEvaluator()
    # formal: 10/10 pass (rate=1.0). informal_economy: 8.5/10 -> use 17/20 for exactness.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 17 + [False] * 3  # formal=1.0, informal=0.85 -> ratio=0.85
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 1.0  # min(0.85/0.80, 1.0) clamps to 1.0
    assert result.passed is True  # 0.85 >= 0.80


def test_disparity_between_floor_and_threshold_is_partial_score():
    evaluator = CohortDisparityEvaluator()
    # formal: 20/20 pass (rate=1.0). informal_economy: 13/20 pass (rate=0.65) -> ratio=0.65
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 13 + [False] * 7
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.8125) < 0.001  # 0.65 / 0.80
    assert result.passed is False


def test_disparity_below_floor_scores_zero():
    evaluator = CohortDisparityEvaluator()
    # formal: 20/20 pass (rate=1.0). informal_economy: 6/20 pass (rate=0.30) -> ratio=0.30
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 6 + [False] * 14
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 0.0
    assert result.passed is False


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
    outcomes = [True] * 9 + [False] + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    result.reason.encode("ascii")  # raises UnicodeEncodeError if non-ASCII chars present


def test_cohort_disparity_result_is_single_output():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 20
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    from evaluators.base import MetricOutput
    assert isinstance(result, MetricOutput)
    assert result.metric_name == "cohort_disparity"
