"""
Code-Switching Quality evaluators — Dimension weight: 10%.

Three separate evaluator classes, one per documented sub-metric
(METHODOLOGY_V1.md section 2.5: register match 35%, switch naturalness 35%,
language preservation 30%), combined via scoring/engine.py's
DEFAULT_METRIC_WEIGHTS["code_switching_quality"].

Design: These evaluators run on EVERY item in a run, not just items explicitly
tagged as code-switching items. Rationale: African users naturally mix languages
even in formally monolingual contexts — a Swahili prompt that receives an English
response is a language preservation failure regardless of its tags. Register
match and language preservation are meaningful quality signals for any item.

The judge prompts are written to handle both cases correctly:
- For monolingual items (e.g. English prompt → English response): the model
  should score near 1.0 for correctly staying in the input language.
- For code-switched items: the model is scored on how naturally it handles
  the actual switching expected by the item.
"""

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.llm_judge import LLMJudge

_PRIMARY_VARIETIES = "Sheng (Nairobi), Nigerian Pidgin, Kinyarwanda-French, Darija (Moroccan Arabic-French)"


class RegisterMatchEvaluator(BaseEvaluator):
    """Does the response match the register (formal/informal/mixed) of the input?"""

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

    @property
    def dimension(self) -> str:
        return "code_switching_quality"

    @property
    def metric_name(self) -> str:
        return "register_match"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        ctx = context or {}

        if not self._judge:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=score,
                passed=score >= 0.6,
                reason="Stub — LLM judge not configured.",
            )

        criterion = (
            "Score how well this AI model response matches the register "
            "(formal, informal, or mixed) of the user's prompt, in an African "
            "language context. This applies to all African languages and varieties "
            f"including English, Swahili, Yoruba, Amharic, Hausa, Zulu, and mixed "
            f"varieties such as {_PRIMARY_VARIETIES}.\n\n"
            "Scoring guide:\n"
            "  1.0 — Perfectly matches the input register (formal→formal, informal→informal, mixed→appropriate mix)\n"
            "  0.7 — Close match with minor register slippage that does not change the overall tone\n"
            "  0.4 — Noticeable mismatch (e.g. formal response to an informal/mixed prompt, or vice versa)\n"
            "  0.0 — Completely ignores the input register\n\n"
            f"Language/variety: {ctx.get('language', 'unknown')}\n"
            f"User prompt: {prompt}\n"
            f"Model response: {model_response}\n"
            f"Reference (expected behavior, for context only): {expected_behavior}\n\n"
            'Respond with: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}'
        )
        score, reason = self._judge.score(criterion, fallback=0.5)

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=reason,
        )


class SwitchNaturalnessEvaluator(BaseEvaluator):
    """Are language switches (or lack thereof) appropriate and natural for this item?"""

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

    @property
    def dimension(self) -> str:
        return "code_switching_quality"

    @property
    def metric_name(self) -> str:
        return "switch_naturalness"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        ctx = context or {}

        if not self._judge:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=score,
                passed=score >= 0.6,
                reason="Stub — LLM judge not configured.",
            )

        criterion = (
            "Score how naturally this AI model handles language in an African context. "
            "This covers both code-switching items and monolingual items — staying "
            "correctly in one language is just as valid as switching naturally between two.\n\n"
            "Scoring guide:\n"
            "  1.0 — No switching expected and the model correctly stays in the input language; OR\n"
            "         switching is expected and switches are grammatically and pragmatically natural\n"
            "  0.7 — Mostly appropriate with minor awkwardness (slight forced switching or minor drift)\n"
            "  0.4 — Jarring or unexpected language switches that disrupt the response\n"
            "  0.0 — Model makes incoherent switches, or unexpectedly switches to a different language\n\n"
            f"Language/variety: {ctx.get('language', 'unknown')}\n"
            f"User prompt: {prompt}\n"
            f"Model response: {model_response}\n"
            f"Reference (expected behavior, for context only): {expected_behavior}\n\n"
            'Respond with: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}'
        )
        score, reason = self._judge.score(criterion, fallback=0.5)

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=reason,
        )


class LanguagePreservationEvaluator(BaseEvaluator):
    """Does the response use the appropriate language(s) for the input?"""

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

    @property
    def dimension(self) -> str:
        return "code_switching_quality"

    @property
    def metric_name(self) -> str:
        return "language_preservation"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        ctx = context or {}

        if not self._judge:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=score,
                passed=score >= 0.6,
                reason="Stub — LLM judge not configured.",
            )

        criterion = (
            "Score whether this AI model response uses the appropriate language(s) "
            "given the user's prompt, in an African language context. A correct "
            "response stays in the same language as a monolingual prompt, or maintains "
            "the expected language mix for a code-switched prompt.\n\n"
            "Scoring guide:\n"
            "  1.0 — Correctly uses the input language(s); does not switch to a different language without reason\n"
            "  0.7 — Mostly correct with minor unnecessary language drift\n"
            "  0.4 — Frequently uses a different language than expected by the prompt\n"
            "  0.0 — Responds entirely in the wrong language (e.g. English when Swahili was used, "
            "or monolingual English when a mixed-language response was clearly expected)\n\n"
            f"Language/variety: {ctx.get('language', 'unknown')}\n"
            f"User prompt: {prompt}\n"
            f"Model response: {model_response}\n"
            f"Reference (expected behavior, for context only): {expected_behavior}\n\n"
            'Respond with: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}'
        )
        score, reason = self._judge.score(criterion, fallback=0.5)

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=reason,
        )
