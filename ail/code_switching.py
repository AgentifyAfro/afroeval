"""
Code-Switching Quality evaluators — Dimension weight: 10%.

Three separate evaluator classes, one per documented sub-metric
(METHODOLOGY_V1.md section 2.5: register match 35%, switch naturalness 35%,
language preservation 30%), combined via scoring/engine.py's
DEFAULT_METRIC_WEIGHTS["code_switching_quality"]. This mirrors how
language_performance and hallucination_risk implement their own multi-metric
dimensions as separate classes rather than one holistic score — see
docs/superpowers/specs/2026-06-28-code-switching-evaluator-design.md for why
this dimension uses that shape instead of the single-holistic-metric shape
used for cultural_appropriateness.

There is no dedicated rubric doc for this dimension (unlike
docs/CULTURAL_RUBRIC_V1.md for cultural appropriateness) — the scoring guide
for each sub-metric is authored directly in this file's prompts, following the
same precedent as the existing FluencyEvaluator
(evaluators/language_performance.py), which also has no separate rubric doc.

Each judge call asks for an already-normalized 0.0-1.0 score directly. Unlike
cultural_appropriateness, there's no 1-5 rubric scale to convert from here, so
there's no clamping-corruption risk to design around (METHODOLOGY_V1.md
already specifies "each scored 0.0-1.0 by an LLM-judge" for this dimension).
"""

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.llm_judge import LLMJudge

_PRIMARY_VARIETIES = "Sheng (Nairobi), Nigerian Pidgin, Kinyarwanda-French, Darija (Moroccan Arabic-French)"


class RegisterMatchEvaluator(BaseEvaluator):
    """Does the response match the input's register (formal/informal/mixed)?"""

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
            "code-switching context. Primary varieties this evaluation covers: "
            f"{_PRIMARY_VARIETIES}.\n\n"
            "Scoring guide:\n"
            "  1.0 — Matches the input's register exactly\n"
            "  0.7 — Close match with minor register slippage that doesn't change the tone\n"
            "  0.4 — Noticeable register mismatch (e.g. responds formally to an informal/mixed prompt)\n"
            "  0.0 — Ignores the input's code-switched/informal style entirely\n\n"
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
    """Are language switches in the response grammatically and pragmatically natural?"""

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
            "Score how natural the language switching is in this AI model response, "
            "in an African code-switching context. Primary varieties this evaluation "
            f"covers: {_PRIMARY_VARIETIES}.\n\n"
            "Scoring guide:\n"
            "  1.0 — Switches are grammatically and pragmatically natural, as a fluent bilingual speaker would switch\n"
            "  0.7 — Understandable but slightly forced switching\n"
            "  0.4 — Jarring switches, or switches that break mid-phrase unnaturally\n"
            "  0.0 — No attempt at code-switching when clearly required, or switches are incoherent\n\n"
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
    """Does the response avoid defaulting to monolingual English when a mix is expected?"""

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
            "Score whether this AI model response avoids defaulting to monolingual "
            "English when a code-switched response was expected, in an African "
            f"code-switching context. Primary varieties this evaluation covers: {_PRIMARY_VARIETIES}.\n\n"
            "Scoring guide:\n"
            "  1.0 — Fully preserves the expected mixed-language style; never defaults to monolingual English\n"
            "  0.7 — Mostly preserves the mix, with one or two unnecessary drops into English\n"
            "  0.4 — Frequently defaults to English, undermining the code-switched style\n"
            "  0.0 — Responds entirely in monolingual English when a code-switched response was clearly expected\n\n"
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
