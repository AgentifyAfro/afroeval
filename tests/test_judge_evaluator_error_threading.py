"""Judge-backed evaluators thread error/error_cause from JudgeResult into MetricOutput."""
from ail.code_switching import RegisterMatchEvaluator
from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator
from evaluators.llm_judge import JudgeResult
from evaluators.safety import HarmfulContentEvaluator


class _FakeJudge:
    def __init__(self, result): self._r = result
    def score(self, criterion, fallback=0.5): return self._r


def test_safety_judge_failure_marks_error_not_a_real_score():
    j = _FakeJudge(JudgeResult(1.0, "Judge error (content_filter): ...", error=True, error_cause="content_filter"))
    out = HarmfulContentEvaluator(judge=j).evaluate("p", "r", "e", {"domain": "d", "language": "yo"})
    assert out.error is True and out.error_cause == "content_filter"


def test_code_switch_judge_failure_threads_error():
    j = _FakeJudge(JudgeResult(0.5, "Judge unavailable: ...", error=True, error_cause="unavailable"))
    out = RegisterMatchEvaluator(judge=j).evaluate("p", "r", "e", {"language": "sw"})
    assert out.error is True and out.error_cause == "unavailable"


def test_cultural_judge_success_has_no_error():
    j = _FakeJudge(JudgeResult(0.9, "great"))
    out = CulturalAppropriatenessEvaluator(judge=j).evaluate("p", "r", "e", {"language": "am", "domain": "health"})
    assert out.error is False and out.error_cause is None and out.score == 0.9
