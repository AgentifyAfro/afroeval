"""
Tests for the real code-switching evaluators (replace the 0.6-always stub).

Uses a fake LLMJudge — no real Azure calls.
"""

from unittest.mock import MagicMock

import pytest

from ail.code_switching import (
    LanguagePreservationEvaluator,
    RegisterMatchEvaluator,
    SwitchNaturalnessEvaluator,
)

ALL_EVALUATOR_CLASSES = [RegisterMatchEvaluator, SwitchNaturalnessEvaluator, LanguagePreservationEvaluator]
EXPECTED_METRIC_NAMES = {
    RegisterMatchEvaluator: "register_match",
    SwitchNaturalnessEvaluator: "switch_naturalness",
    LanguagePreservationEvaluator: "language_preservation",
}


def _fake_judge(score: float, reason: str = "test reason") -> MagicMock:
    judge = MagicMock()
    judge.score.return_value = (score, reason)
    return judge


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_dimension_and_metric_name(evaluator_cls):
    evaluator = evaluator_cls(judge=None)
    assert evaluator.dimension == "code_switching_quality"
    assert evaluator.metric_name == EXPECTED_METRIC_NAMES[evaluator_cls]


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_no_judge_configured_stub_behavior(evaluator_cls):
    evaluator = evaluator_cls(judge=None)
    result = evaluator.evaluate(
        prompt="Niaje, unaweza kunitumia hela kwa M-Pesa leo?",
        model_response="a non-empty response",
        expected_behavior="expected",
        context={"language": "sheng"},
    )
    assert result.score == 0.5
    assert result.passed is True
    assert "not configured" in result.reason.lower()


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_no_judge_configured_empty_response(evaluator_cls):
    evaluator = evaluator_cls(judge=None)
    result = evaluator.evaluate(
        prompt="Niaje, unaweza kunitumia hela kwa M-Pesa leo?",
        model_response="",
        expected_behavior="expected",
        context={"language": "sheng"},
    )
    assert result.score == 0.0
    assert result.passed is False


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_judge_score_passes_through_unconverted(evaluator_cls):
    judge = _fake_judge(score=1.0, reason="Natural register-matched code-switch")
    evaluator = evaluator_cls(judge=judge)
    result = evaluator.evaluate(
        prompt="Niaje, unaweza kunitumia hela kwa M-Pesa leo?",
        model_response="Sawa bro, nitakutumia hela kwa M-Pesa sasa hivi.",
        expected_behavior="Confirm the transfer in a casual, friendly register.",
        context={"language": "sheng"},
    )
    assert result.score == 1.0
    assert result.passed is True


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_judge_low_score_fails(evaluator_cls):
    judge = _fake_judge(score=0.4, reason="Defaults to monolingual English, ignoring the Sheng prompt")
    evaluator = evaluator_cls(judge=judge)
    result = evaluator.evaluate(
        prompt="Niaje, unaweza kunitumia hela kwa M-Pesa leo?",
        model_response="Sure, I can send you the money via M-Pesa today.",
        expected_behavior="Confirm the transfer in a casual, friendly register.",
        context={"language": "sheng"},
    )
    assert result.score == 0.4
    assert result.passed is False


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_pass_threshold_boundary(evaluator_cls):
    judge_at_threshold = _fake_judge(score=0.6)
    evaluator = evaluator_cls(judge=judge_at_threshold)
    result = evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e", context={"language": "pidgin"},
    )
    assert result.passed is True

    judge_below_threshold = _fake_judge(score=0.59)
    evaluator2 = evaluator_cls(judge=judge_below_threshold)
    result2 = evaluator2.evaluate(
        prompt="p", model_response="r", expected_behavior="e", context={"language": "pidgin"},
    )
    assert result2.passed is False


def test_register_match_prompt_contains_scoring_guide():
    judge = _fake_judge(score=0.75)
    evaluator = RegisterMatchEvaluator(judge=judge)
    evaluator.evaluate(prompt="p", model_response="r", expected_behavior="e", context={"language": "sheng"})
    criterion_sent = judge.score.call_args[0][0]
    assert "register" in criterion_sent.lower()
    assert "Sheng" in criterion_sent


def test_switch_naturalness_prompt_contains_scoring_guide():
    judge = _fake_judge(score=0.75)
    evaluator = SwitchNaturalnessEvaluator(judge=judge)
    evaluator.evaluate(prompt="p", model_response="r", expected_behavior="e", context={"language": "pidgin"})
    criterion_sent = judge.score.call_args[0][0]
    assert "natural" in criterion_sent.lower()
    assert "Nigerian Pidgin" in criterion_sent


def test_language_preservation_prompt_contains_scoring_guide():
    judge = _fake_judge(score=0.75)
    evaluator = LanguagePreservationEvaluator(judge=judge)
    evaluator.evaluate(prompt="p", model_response="r", expected_behavior="e", context={"language": "darija"})
    criterion_sent = judge.score.call_args[0][0]
    assert "monolingual english" in criterion_sent.lower()
    assert "Darija" in criterion_sent


@pytest.mark.parametrize("evaluator_cls", ALL_EVALUATOR_CLASSES)
def test_context_fields_appear_in_prompt(evaluator_cls):
    judge = _fake_judge(score=0.75)
    evaluator = evaluator_cls(judge=judge)
    evaluator.evaluate(
        prompt="Test prompt text",
        model_response="Test response text",
        expected_behavior="Test expected text",
        context={"language": "kinyarwanda-french"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "kinyarwanda-french" in criterion_sent
    assert "Test prompt text" in criterion_sent
    assert "Test response text" in criterion_sent
    assert "Test expected text" in criterion_sent
