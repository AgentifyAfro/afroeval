"""
Tests for safety_robustness evaluator classes.

All tests run in stub mode (no judge — zero API calls).
"""

from evaluators.safety import (
    AdversarialRobustnessEvaluator,
    HarmfulContentEvaluator,
    RefusalCalibrationEvaluator,
)
from scoring.engine import DEFAULT_METRIC_WEIGHTS

# ── HarmfulContentEvaluator ──────────────────────────────────────────────────

def test_harmful_content_no_judge_stub():
    ev = HarmfulContentEvaluator()
    result = ev.evaluate("p", "r", "e", {})
    assert result.score == 0.5
    assert result.passed is True
    assert result.dimension == "safety_robustness"
    assert result.metric_name == "harmful_content"


def test_harmful_content_dimension_and_metric_name():
    ev = HarmfulContentEvaluator()
    assert ev.dimension == "safety_robustness"
    assert ev.metric_name == "harmful_content"


# ── RefusalCalibrationEvaluator ──────────────────────────────────────────────

def test_refusal_calibration_no_judge_stub():
    ev = RefusalCalibrationEvaluator()
    result = ev.evaluate("p", "r", "e", {})
    assert result.score == 0.5
    assert result.passed is True
    assert result.dimension == "safety_robustness"
    assert result.metric_name == "refusal_calibration"


def test_refusal_calibration_dimension_and_metric_name():
    ev = RefusalCalibrationEvaluator()
    assert ev.dimension == "safety_robustness"
    assert ev.metric_name == "refusal_calibration"


# ── AdversarialRobustnessEvaluator ───────────────────────────────────────────

def test_adversarial_non_adversarial_item_neutral():
    ev = AdversarialRobustnessEvaluator()
    result = ev.evaluate("p", "r", "e", {"tags": ["safety", "de-escalation"]})
    assert result.score == 1.0
    assert result.passed is True
    assert "Not an adversarial item" in result.reason


def test_adversarial_item_no_judge_safe_fallback():
    ev = AdversarialRobustnessEvaluator()
    result = ev.evaluate("p", "r", "e", {"tags": ["safety", "adversarial"]})
    assert result.score == 1.0
    assert result.passed is True


def test_adversarial_no_context_neutral():
    ev = AdversarialRobustnessEvaluator()
    result = ev.evaluate("p", "r", "e", None)
    assert result.score == 1.0
    assert result.passed is True


def test_adversarial_empty_tags_neutral():
    ev = AdversarialRobustnessEvaluator()
    result = ev.evaluate("p", "r", "e", {"tags": []})
    assert result.score == 1.0
    assert result.passed is True


def test_adversarial_dimension_and_metric_name():
    ev = AdversarialRobustnessEvaluator()
    assert ev.dimension == "safety_robustness"
    assert ev.metric_name == "adversarial_robustness"


# ── Scoring engine integration ────────────────────────────────────────────────

def test_safety_robustness_metric_weights_sum_to_one():
    weights = DEFAULT_METRIC_WEIGHTS["safety_robustness"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["harmful_content"] == 0.40
    assert weights["refusal_calibration"] == 0.35
    assert weights["adversarial_robustness"] == 0.25
