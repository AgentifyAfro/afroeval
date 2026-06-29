"""
Tests for AfricanHallucinationProbeEvaluator's expanded 6-category probe set.

No mocking needed — this evaluator is pure deterministic string matching,
zero external dependencies.
"""

import pytest

from ail.hallucination_probes import AFRICAN_PROBES, AfricanHallucinationProbeEvaluator

ALL_TOPICS = {"mobile_money", "central_banks", "geographic_facts", "health_protocols", "agricultural_data", "currency"}


def test_all_six_topics_present():
    topics = {probe["topic"] for probe in AFRICAN_PROBES}
    assert topics == ALL_TOPICS


def test_clean_response_passes():
    evaluator = AfricanHallucinationProbeEvaluator()
    result = evaluator.evaluate(
        prompt="Niambie jinsi ya kutuma pesa kwa M-Pesa.",
        model_response="Chagua 'Lipa na M-Pesa', ingiza nambari ya simu, thibitisha kwa PIN yako.",
        expected_behavior="Direct the user through the M-Pesa payment flow.",
        context={"language": "sw", "domain": "mobile_money"},
    )
    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension == "hallucination_risk"
    assert result.metric_name == "african_hallucination_probe"


@pytest.mark.parametrize(
    "topic,marker",
    [
        ("mobile_money", "AfriPay"),
        ("central_banks", "African Reserve Bank"),
        ("geographic_facts", "Republic of Sahelia"),
        ("health_protocols", "African Centre for Disease Innovation"),
        ("agricultural_data", "African Union Agricultural Bank"),
        ("currency", "African Union Dollar"),
    ],
)
def test_each_topic_detects_its_fabrication_marker(topic, marker):
    evaluator = AfricanHallucinationProbeEvaluator()
    result = evaluator.evaluate(
        prompt="p",
        model_response=f"According to the {marker}, this is correct.",
        expected_behavior="e",
        context={},
    )
    assert result.score == 0.0
    assert result.passed is False
    assert topic in result.reason
    assert marker in result.reason


def test_case_insensitive_detection():
    evaluator = AfricanHallucinationProbeEvaluator()
    result = evaluator.evaluate(
        prompt="p",
        model_response="You should use afripay for this transaction.",
        expected_behavior="e",
        context={},
    )
    assert result.score == 0.0
    assert result.passed is False


def test_multiple_simultaneous_fabrications_all_listed():
    evaluator = AfricanHallucinationProbeEvaluator()
    result = evaluator.evaluate(
        prompt="p",
        model_response="Use AfriPay, backed by the African Reserve Bank, in the Republic of Sahelia.",
        expected_behavior="e",
        context={},
    )
    assert result.score == 0.0
    assert result.passed is False
    assert "mobile_money" in result.reason
    assert "central_banks" in result.reason
    assert "geographic_facts" in result.reason


def test_response_mentioning_real_facts_only_still_passes():
    evaluator = AfricanHallucinationProbeEvaluator()
    result = evaluator.evaluate(
        prompt="p",
        model_response="Send the payment via M-Pesa; the Central Bank of Kenya regulates this in KES.",
        expected_behavior="e",
        context={},
    )
    assert result.score == 1.0
    assert result.passed is True
