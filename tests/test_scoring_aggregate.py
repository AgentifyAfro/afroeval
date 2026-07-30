"""Tests for scoring.aggregate — the post-hoc composite helper the Language Comparison
view uses so it stays consistent with the engine's weighted, metric-filtered composite."""
import pytest

from scoring.aggregate import _dimension_score, composite_from_metric_means


def test_language_performance_ignores_excluded_metrics():
    # semantic 0.50 + completeness 0.30 + fluency 0.20; chrf / multilingual must NOT count.
    mm = {"semantic_similarity": 1.0, "answer_completeness": 0.345, "fluency": 1.0,
          "chrf_score": 0.246, "multilingual_similarity": 0.0}
    # 0.5*1.0 + 0.3*0.345 + 0.2*1.0 = 0.8035 -> 80.35
    assert _dimension_score("language_performance", mm) == pytest.approx(80.35, abs=0.01)


def test_hallucination_ignores_probe_gate():
    mm = {"faithfulness": 0.984, "african_hallucination_probe": 1.0}
    assert _dimension_score("hallucination_risk", mm) == pytest.approx(98.4, abs=0.01)


def test_unweighted_dimensions_use_flat_mean():
    # cultural_appropriateness is not in DEFAULT_METRIC_WEIGHTS -> flat mean of metric means.
    mm = {"cultural_score": 0.5, "some_other": 0.7}
    assert _dimension_score("cultural_appropriateness", mm) == pytest.approx(60.0, abs=0.01)


def test_empty_dimension_is_none():
    assert _dimension_score("language_performance", {}) is None
    assert _dimension_score("cultural_appropriateness", {}) is None


def test_partial_submetrics_renormalize():
    # Only fluency present (weight 0.20) -> renormalized to 100% of that metric.
    assert _dimension_score("language_performance", {"fluency": 0.9}) == pytest.approx(90.0, abs=0.01)


def test_composite_weighted_and_renormalized_when_bias_absent():
    # English gpt-4o profile (no bias_fairness) -> faithful composite ~77.9.
    metric_means = {
        "language_performance": {"semantic_similarity": 1.0, "answer_completeness": 0.345,
                                 "fluency": 1.0, "chrf_score": 0.246, "multilingual_similarity": 0.0},
        "cultural_appropriateness": {"cultural_score": 0.528},
        "hallucination_risk": {"faithfulness": 0.984, "african_hallucination_probe": 1.0},
        "code_switching_quality": {"register_match": 0.787, "switch_naturalness": 0.787,
                                   "language_preservation": 0.787},
        "safety_robustness": {"harmful_content": 0.806, "refusal_calibration": 0.806,
                              "adversarial_robustness": 0.806},
    }
    dim_scores, composite = composite_from_metric_means(metric_means)
    assert dim_scores["language_performance"] == pytest.approx(80.35, abs=0.01)
    assert dim_scores.get("bias_fairness") is None  # absent input -> not in dict / None
    assert round(composite, 1) == 78.0  # weighted over 0.85 (bias 0.15 dropped), renormalized


def test_no_dimensions_composite_none():
    dim_scores, composite = composite_from_metric_means({})
    assert composite is None
    assert dim_scores == {}
