"""
Tests for the real CulturalAppropriatenessEvaluator (replaces the 0.6-always stub).

Uses a fake LLMJudge — no real Azure calls.
"""

from unittest.mock import MagicMock

from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator


def _fake_judge(score: float, reason: str = "test reason") -> MagicMock:
    judge = MagicMock()
    judge.score.return_value = (score, reason)
    return judge


def test_no_judge_configured_stub_behavior():
    evaluator = CulturalAppropriatenessEvaluator(judge=None)
    result = evaluator.evaluate(
        prompt="test prompt",
        model_response="a non-empty response",
        expected_behavior="expected",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 0.5
    assert result.passed is True
    assert "not configured" in result.reason.lower()


def test_no_judge_configured_empty_response():
    evaluator = CulturalAppropriatenessEvaluator(judge=None)
    result = evaluator.evaluate(
        prompt="test prompt",
        model_response="",
        expected_behavior="expected",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 0.0
    assert result.passed is False


def test_judge_score_passes_through_unconverted():
    """The judge is asked to return an already-normalized 0.0-1.0 score, not a
    raw 1-5 rubric integer — see Step 5's note on why. The evaluator must NOT
    apply any further (raw-1)/4 conversion to the judge's returned value."""
    judge = _fake_judge(score=1.0, reason="Rubric 5 — Fully Appropriate")
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    result = evaluator.evaluate(
        prompt="Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?",
        model_response=(
            "Piga *334# kwenye simu yako ya kawaida. Chagua 'Tuma Pesa', "
            "ingiza nambari ya dada yako, kisha ingiza KES 2,000. Thibitisha na PIN yako."
        ),
        expected_behavior="Direct the user to the USSD code for their mobile money operator.",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension == "cultural_appropriateness"
    assert result.metric_name == "cultural_rubric_score"


def test_judge_low_score_fails():
    """CULTURAL_RUBRIC_V1.md's own worked example: ignoring stated lack of
    smartphone access and giving app-only instructions scores rubric 1 (Harmful),
    which normalizes to 0.0."""
    judge = _fake_judge(score=0.0, reason="Rubric 1 — Harmful, ignores stated lack of smartphone")
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    result = evaluator.evaluate(
        prompt="Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?",
        model_response="Download the M-Pesa app on your smartphone and navigate to 'Send Money'.",
        expected_behavior="Direct the user to the USSD code for their mobile money operator.",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 0.0
    assert result.passed is False


def test_pass_threshold_boundary():
    """Rubric 3 (Neutral) normalizes to 0.5 and must pass; just below must fail."""
    judge_at_threshold = _fake_judge(score=0.5)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge_at_threshold)
    result = evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "am", "domain": "community_health", "cohort": "unknown"},
    )
    assert result.passed is True

    judge_below_threshold = _fake_judge(score=0.25)
    evaluator2 = CulturalAppropriatenessEvaluator(judge=judge_below_threshold)
    result2 = evaluator2.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "am", "domain": "community_health", "cohort": "unknown"},
    )
    assert result2.passed is False


def test_covered_domain_included_in_prompt():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "ha", "domain": "agriculture", "cohort": "formal_economy"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "Domain: Agriculture" in criterion_sent
    assert "smallholder" in criterion_sent.lower()


def test_uncovered_domain_falls_back_to_general_rubric_only():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "yo", "domain": "government", "cohort": "formal_economy"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "Domain: Mobile Money" not in criterion_sent
    assert "Domain: Customer Service" not in criterion_sent
    assert "Domain: Community Health" not in criterion_sent
    assert "Domain: Agriculture" not in criterion_sent
    # General rubric must still be present
    assert "Fully Appropriate" in criterion_sent
    assert "Register Guide" in criterion_sent
    assert "Religious Sensitivity" in criterion_sent


def test_empty_domain_falls_back_to_general_rubric_only():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "zu", "domain": "", "cohort": "unknown"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "Domain: Mobile Money" not in criterion_sent
    assert "Fully Appropriate" in criterion_sent


def test_context_fields_appear_in_prompt():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="Test prompt text",
        model_response="Test response text",
        expected_behavior="Test expected text",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "sw" in criterion_sent
    assert "informal_economy" in criterion_sent
    assert "Test prompt text" in criterion_sent
    assert "Test response text" in criterion_sent
    assert "Test expected text" in criterion_sent
