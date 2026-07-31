"""
Tests for language_performance evaluators — stub/mock mode, no API calls.
"""
from unittest.mock import patch

from evaluators.language_performance import MultilingualSimilarityEvaluator


def test_multilingual_similarity_401_returns_not_applicable():
    """A 401 auth error from HuggingFace Hub must NOT be stored as a real 0.0 score."""
    ev = MultilingualSimilarityEvaluator()
    with patch(
        "evaluators.language_performance._get_multilingual_model",
        side_effect=Exception("401 Client Error: Unauthorized for url: https://huggingface.co/..."),
    ):
        result = ev.evaluate(
            prompt="p",
            model_response="r",
            expected_behavior="e",
        )
    assert result.applicable is False
    assert result.error is True
    assert "401" in result.reason or "auth" in result.reason.lower()


def test_multilingual_similarity_non_auth_error_stays_applicable():
    """Transient errors (e.g. a network timeout) keep the row visible but flag it as an error,
    so the failure is noticed. (Permanent infra failures — auth, missing dep — are skipped;
    see the tests around this one.)"""
    ev = MultilingualSimilarityEvaluator()
    with patch(
        "evaluators.language_performance._get_multilingual_model",
        side_effect=Exception("Connection timeout"),
    ):
        result = ev.evaluate(
            prompt="p",
            model_response="r",
            expected_behavior="e",
        )
    assert result.applicable is True
    assert result.error is True
    assert result.score == 0.0


def test_multilingual_similarity_missing_dependency_not_applicable():
    """sentence-transformers not installed -> the metric cannot run, so it must be skipped
    (applicable=False), not persisted as a dead 0.0 FAIL row in the Metric Results."""
    ev = MultilingualSimilarityEvaluator()
    with patch(
        "evaluators.language_performance._get_multilingual_model",
        side_effect=ModuleNotFoundError("No module named 'sentence_transformers'"),
    ):
        result = ev.evaluate(prompt="p", model_response="r", expected_behavior="e")
    assert result.applicable is False
    assert result.error is True
    assert result.score == 0.0


def test_multilingual_similarity_dimension_and_metric_name():
    ev = MultilingualSimilarityEvaluator()
    assert ev.dimension == "language_performance"
    assert ev.metric_name == "multilingual_similarity"
