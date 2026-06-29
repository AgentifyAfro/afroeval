# Code-Switching Quality Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `CodeSwitchingEvaluator` stub (always returns `score=0.6`) with three real LLM-judge evaluators implementing the documented sub-metrics in `METHODOLOGY_V1.md` section 2.5.

**Architecture:** `ail/code_switching.py` gains three evaluator classes — `RegisterMatchEvaluator`, `SwitchNaturalnessEvaluator`, `LanguagePreservationEvaluator` — each wrapping its own `LLMJudge` call with a focused, self-authored scoring guide. Combined via a new `scoring/engine.py::DEFAULT_METRIC_WEIGHTS["code_switching_quality"]` entry, consumed automatically by the already-generic `_weighted_dimension_average()`. Wired into the dispatcher exactly like the existing `FluencyEvaluator`/`CulturalAppropriatenessEvaluator`.

**Tech Stack:** Python, the existing `evaluators.llm_judge.LLMJudge` (Azure OpenAI-backed), pytest.

## Global Constraints

- Per the approved spec (`docs/superpowers/specs/2026-06-28-code-switching-evaluator-design.md`): three separate evaluator classes, not one holistic metric — this dimension's documented design has no internal contradiction requiring collapse, unlike `cultural_appropriateness`.
- Sub-metric weights are exactly `register_match: 0.35, switch_naturalness: 0.35, language_preservation: 0.30` (must sum to 1.0).
- `passed` is `True` exactly when `score >= 0.6` for all three evaluators, matching the documented dimension-level "Pass threshold: ≥ 0.60."
- Each judge call asks for an already-normalized 0.0-1.0 score directly (no rubric-scale conversion needed — unlike cultural appropriateness, there's no 1-5 scale here to convert from).
- No new dependencies — reuses `evaluators.llm_judge.LLMJudge`, already a project dependency.
- `METHODOLOGY_V1.md` is NOT modified by this plan — its existing section 2.5 already accurately describes what's being built.

---

### Task 1: Three real evaluator classes with unit tests

**Files:**
- Modify: `ail/code_switching.py` (entire file rewritten)
- Test: `tests/test_code_switching.py` (new)

**Interfaces:**
- Produces: `ail.code_switching.RegisterMatchEvaluator.__init__(self, judge: LLMJudge | None = None)`, `ail.code_switching.SwitchNaturalnessEvaluator.__init__(self, judge: LLMJudge | None = None)`, `ail.code_switching.LanguagePreservationEvaluator.__init__(self, judge: LLMJudge | None = None)`. All three: `dimension` property returns `"code_switching_quality"`; `metric_name` returns `"register_match"`, `"switch_naturalness"`, `"language_preservation"` respectively.
- Consumes: `evaluators.llm_judge.LLMJudge` (existing) — `judge.score(criterion: str, fallback: float = 0.5) -> tuple[float, str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_code_switching.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_code_switching.py -v
```

Expected: `ImportError` or collection failure — `RegisterMatchEvaluator`, `SwitchNaturalnessEvaluator`, `LanguagePreservationEvaluator` don't exist yet.

- [ ] **Step 3: Write the full implementation**

Replace the entire contents of `ail/code_switching.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_code_switching.py -v
```

Expected: all tests PASS (3 evaluator classes × parametrized cases + 3 prompt-specific tests = 24 individual test results).

- [ ] **Step 5: Stage and stop for review**

```powershell
git add ail/code_switching.py tests/test_code_switching.py
git status
```

Do not commit — show Dan the staged diff and wait for explicit approval before any commit.

---

### Task 2: Wire into scoring + pipeline, unstub the export script

**Files:**
- Modify: `scoring/engine.py:47-57` (add `DEFAULT_METRIC_WEIGHTS["code_switching_quality"]`)
- Test: `tests/test_scoring.py` (add one test, mirroring the existing pattern at line 122)
- Modify: `orchestration/dispatcher.py:220` and `:248` (import + instantiation)
- Modify: `scripts/hitl_export_tasks.py:31-35` (`_STUB_METRIC_NAMES`)

**Interfaces:**
- Consumes: `ail.code_switching.RegisterMatchEvaluator`, `ail.code_switching.SwitchNaturalnessEvaluator`, `ail.code_switching.LanguagePreservationEvaluator` (Task 1).

- [ ] **Step 1: Add the sub-metric weights**

In `scoring/engine.py`, find (currently lines 47-57):

```python
DEFAULT_METRIC_WEIGHTS: dict[str, dict[str, float]] = {
    "language_performance": {
        "semantic_similarity": 0.50,
        "answer_completeness": 0.30,
        "fluency": 0.20,
    },
    "hallucination_risk": {
        "faithfulness": 0.40,
        "african_hallucination_probe": 0.60,
    },
}
```

Replace with:

```python
DEFAULT_METRIC_WEIGHTS: dict[str, dict[str, float]] = {
    "language_performance": {
        "semantic_similarity": 0.50,
        "answer_completeness": 0.30,
        "fluency": 0.20,
    },
    "hallucination_risk": {
        "faithfulness": 0.40,
        "african_hallucination_probe": 0.60,
    },
    "code_switching_quality": {
        "register_match": 0.35,
        "switch_naturalness": 0.35,
        "language_preservation": 0.30,
    },
}
```

- [ ] **Step 2: Write the failing test for the new weights**

In `tests/test_scoring.py`, after the existing `test_weighted_dimension_average_renormalizes_missing_metric` function (currently ending around line 140), add:

```python
def test_weighted_dimension_average_matches_code_switching_weights():
    # code_switching_quality: register_match 35%, switch_naturalness 35%, language_preservation 30%
    metric_scores = {
        "register_match": [1.0],
        "switch_naturalness": [1.0],
        "language_preservation": [0.0],
    }
    avg = _weighted_dimension_average(metric_scores, DEFAULT_METRIC_WEIGHTS["code_switching_quality"])
    assert avg == pytest.approx(0.70)  # 1.0*0.35 + 1.0*0.35 + 0.0*0.30
```

- [ ] **Step 3: Run the new test to verify it fails, then passes**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py::test_weighted_dimension_average_matches_code_switching_weights -v
```

Expected before Step 1: `KeyError: 'code_switching_quality'`. After Step 1 is in place: PASS.

- [ ] **Step 4: Wire the real evaluators into the dispatcher**

In `orchestration/dispatcher.py`, find this import line (currently line 220):

```python
                from ail.code_switching import CodeSwitchingEvaluator
```

Replace with:

```python
                from ail.code_switching import (
                    LanguagePreservationEvaluator,
                    RegisterMatchEvaluator,
                    SwitchNaturalnessEvaluator,
                )
```

Then find this line in the `evaluators` list (currently line 248):

```python
                    CodeSwitchingEvaluator(),
```

Replace with:

```python
                    RegisterMatchEvaluator(judge=judge),
                    SwitchNaturalnessEvaluator(judge=judge),
                    LanguagePreservationEvaluator(judge=judge),
```

(`judge` is already in scope at that point — built earlier in the function, already passed the same way to `FluencyEvaluator` and `CulturalAppropriatenessEvaluator`.)

- [ ] **Step 5: Remove the now-resolved stub entry from the export script**

In `scripts/hitl_export_tasks.py`, find the `_STUB_METRIC_NAMES` set (currently lines 31-35):

```python
_STUB_METRIC_NAMES = {
    "cohort_disparity",             # CohortDisparityEvaluator — always 0.75
    "code_switching_score",         # CodeSwitchingEvaluator — always 0.6
    "african_hallucination_probe",  # only 2 hardcoded fabrication topics, not a real probe set
}
```

Replace with:

```python
_STUB_METRIC_NAMES = {
    "cohort_disparity",             # CohortDisparityEvaluator — always 0.75
    "african_hallucination_probe",  # only 2 hardcoded fabrication topics, not a real probe set
}
```

(`"code_switching_score"` is removed entirely — that metric name doesn't exist anymore now that the stub class is gone, replaced by `register_match`/`switch_naturalness`/`language_preservation`, none of which were ever stubs.)

- [ ] **Step 6: Run the full test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all tests pass (117 prior + 24 from Task 1 + 1 from Step 2 = 142; if the exact count differs, read any failure before assuming it's wrong — confirm whether it's a genuinely new regression or an expected count adjustment).

- [ ] **Step 7: Manual verification**

This cannot be fully automated without a live Azure judge call. If you have Azure credentials configured (copy `.env` from the main checkout into this worktree if needed, then remove it afterward), run a sanity check using a clear Sheng example:

```powershell
.\.venv\Scripts\python.exe -c "
from evaluators.llm_judge import LLMJudge
from ail.code_switching import RegisterMatchEvaluator, SwitchNaturalnessEvaluator, LanguagePreservationEvaluator
from api.settings import get_settings

s = get_settings()
judge = LLMJudge.from_azure(s.azure_openai_api_key, s.azure_openai_endpoint, s.azure_openai_deployment_name, s.azure_openai_api_version)

prompt = 'Niaje, unaweza kunitumia hela kwa M-Pesa leo?'
good_response = 'Sawa bro, nitakutumia hela kwa M-Pesa sasa hivi. Tuma number yako.'
bad_response = 'Sure, I can send you the money via M-Pesa today. Please share your number.'

for label, response in [('GOOD (Sheng, natural)', good_response), ('BAD (English-only)', bad_response)]:
    print(f'--- {label} ---')
    for cls in [RegisterMatchEvaluator, SwitchNaturalnessEvaluator, LanguagePreservationEvaluator]:
        ev = cls(judge=judge)
        r = ev.evaluate(prompt=prompt, model_response=response, expected_behavior='Confirm the transfer in a casual, friendly register.', context={'language': 'sheng'})
        print(f'{r.metric_name}: score={r.score}, passed={r.passed}, reason={r.reason}')
"
```

Expected: the good (Sheng) response should score noticeably higher across all three metrics than the bad (English-only) response — especially `language_preservation`, which should score low for the English-only response since it's exactly the failure mode that metric is designed to catch. If the good and bad responses score similarly, investigate the prompts before treating Task 1 as done — this is the one check that exercises a real LLM call instead of a fake judge.

- [ ] **Step 8: Stage and stop for review**

```powershell
git add scoring/engine.py tests/test_scoring.py orchestration/dispatcher.py scripts/hitl_export_tasks.py
git status
```

Do not commit — present the full diff across both tasks to Dan and wait for his explicit approval before committing anything.

---

## Self-Review Notes

- **Spec coverage:** three separate evaluator classes (Task 1), the 35/35/30 weighting (Task 2 Step 1), dispatcher wiring (Task 2 Step 4), export-script unstub (Task 2 Step 5) — every section of the spec has a corresponding step. No `METHODOLOGY_V1.md` change needed, consistent with the spec's explicit statement that this dimension's doc has no contradiction to fix.
- **Type consistency:** all three evaluator constructors share the identical `__init__(self, judge: LLMJudge | None = None)` signature defined once in Task 1, consumed identically in Task 2's dispatcher wiring — no renamed parameters. `metric_name` strings (`register_match`, `switch_naturalness`, `language_preservation`) are used identically across Task 1's classes, Task 2's `DEFAULT_METRIC_WEIGHTS` keys, and Task 2's new test — no typos introduced between them (double-checked character-by-character against each other while writing this plan).
- **No placeholders:** every step has complete, literal code and exact commands. The one explicit human checkpoint (none requiring live production access this time, unlike the RLS fix plan) is the manual Azure verification in Task 2 Step 7, which is explicitly optional-but-recommended and clearly flagged as the one thing automated tests can't cover.
