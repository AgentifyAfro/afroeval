# Inspection Anomaly Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 anomalies discovered during the 2026-06-29 end-to-end inspection run: deepeval rate-limit resilience, honest confidence_flag, single-row cohort disparity persistence, completed_at null in JSON, Unicode corruption in reason strings, and graceful multilingual-similarity 401 handling.

**Architecture:** All changes are isolated to existing modules; no new files or tables needed. The `error: bool` field added to `MetricOutput` is the single shared primitive that lets evaluators signal failures cleanly without string parsing. Dispatcher tracks error rates and passes them to the scoring engine, which uses them to gate the confidence_flag.

**Tech Stack:** Python 3.12, SQLModel/PostgreSQL (Supabase), deepeval, sentence-transformers, asyncio

## Global Constraints

- No new tables, no schema migrations
- All existing 187 tests must keep passing
- No changes to `benchmarks/packs/*.jsonl`
- Branch: `fix/inspection-anomalies`
- Run tests with: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
- Venv: `.venv/` in project root

---

## File Map

| File | Change |
|---|---|
| `evaluators/base.py` | Add `error: bool = False` to `MetricOutput` |
| `evaluators/language_performance.py` | Outer retry in deepeval evaluators; 401 → `applicable=False` |
| `evaluators/hallucination.py` | Outer retry in `FaithfulnessEvaluator` |
| `evaluators/bias_fairness.py` | Replace `≥` with `>=` in reason string |
| `orchestration/dispatcher.py` | Semaphore 10→3; single bias row; `completed_at` before JSON; pass error rates |
| `scoring/engine.py` | Accept `metric_error_rates`, set `low_coverage` when rate > 0.5 |
| `tests/test_scoring.py` | Tests for error-rate confidence flag |
| `tests/test_sprint1.py` | Tests for rate-limit retry + `error` field |
| `tests/test_bias_fairness.py` | Test reason string is ASCII-safe |
| `tests/test_language_performance.py` | New file: 401 → `applicable=False` |

---

## Task 1: Add `error` flag to MetricOutput

**Files:**
- Modify: `evaluators/base.py`
- Test: `tests/test_sprint1.py`

**Interfaces:**
- Produces: `MetricOutput.error: bool = False` — evaluators set `True` when falling back due to an infrastructure error (rate limit, auth, network), not a real measurement

- [ ] **Step 1: Write the failing test**

Add at the bottom of `tests/test_sprint1.py`:
```python
def test_metric_output_error_field_defaults_false():
    from evaluators.base import MetricOutput
    out = MetricOutput(dimension="d", metric_name="m", score=0.5, passed=False, reason="r")
    assert out.error is False


def test_metric_output_error_field_can_be_set():
    from evaluators.base import MetricOutput
    out = MetricOutput(dimension="d", metric_name="m", score=0.5, passed=False, reason="r", error=True)
    assert out.error is True
```

- [ ] **Step 2: Run test — expect FAIL**

```
.\.venv\Scripts\python.exe -m pytest tests/test_sprint1.py::test_metric_output_error_field_defaults_false tests/test_sprint1.py::test_metric_output_error_field_can_be_set -v
```

Expected: `AttributeError: MetricOutput has no attribute 'error'`

- [ ] **Step 3: Add `error` field to `MetricOutput`**

In `evaluators/base.py`, add `error: bool = False` after `applicable`:

```python
@dataclass
class MetricOutput:
    """Normalized output from any evaluator."""
    dimension: str
    metric_name: str
    score: float
    passed: bool
    reason: str = ""
    extra: dict = field(default_factory=dict)
    applicable: bool = True
    error: bool = False   # True when score is a fallback due to infra error, not a real measurement
```

- [ ] **Step 4: Run test — expect PASS**

```
.\.venv\Scripts\python.exe -m pytest tests/test_sprint1.py::test_metric_output_error_field_defaults_false tests/test_sprint1.py::test_metric_output_error_field_can_be_set -v
```

- [ ] **Step 5: Run full suite — confirm no regressions**

```
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all 187 + 2 new = 189 pass.

---

## Task 2: Unicode fix — replace `≥` with `>=` in bias reason string

**Files:**
- Modify: `evaluators/bias_fairness.py`
- Test: `tests/test_bias_fairness.py`

**Interfaces:**
- Consumes: `MetricOutput.error` from Task 1 (not used here, but Task 1 must land first since `bias_fairness.py` imports `MetricOutput`)
- Produces: reason strings for `cohort_disparity` metric that are ASCII-safe

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bias_fairness.py`:
```python
def test_cohort_disparity_reason_is_ascii_safe():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 9 + [False] + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    # Reason must round-trip through ASCII without errors (Windows cp1252 compat)
    result.reason.encode("ascii")
```

- [ ] **Step 2: Run test — expect FAIL**

```
.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py::test_cohort_disparity_reason_is_ascii_safe -v
```

Expected: `UnicodeEncodeError` (≥ is not ASCII)

- [ ] **Step 3: Replace `≥` with `>=` in `evaluators/bias_fairness.py`**

In `evaluators/bias_fairness.py`, find the reason string in `compute_run_disparity()` and replace `≥` with `>=`:

```python
        reason = (
            f"Disparate impact ratio: {disparate_impact_ratio:.3f} "
            f"(threshold >={DISPARITY_PASS_THRESHOLD}). "
            f"Per-cohort selection rates: {rates_dict}. "
            f"Worst-performing cohort: '{worst_cohort}' ({rates[worst_cohort]:.3f}), "
            f"best: '{best_cohort}' ({rates[best_cohort]:.3f})."
        )
```

- [ ] **Step 4: Run test — expect PASS**

```
.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py -v
```

Expected: all bias_fairness tests pass.

---

## Task 3: Multilingual similarity — 401 auth error → `applicable=False`

**Files:**
- Modify: `evaluators/language_performance.py`
- Create: `tests/test_language_performance.py`

**Interfaces:**
- Consumes: `MetricOutput.error` from Task 1
- Produces: `MultilingualSimilarityEvaluator.evaluate()` returns `applicable=False, error=True` on 401/auth errors instead of `score=0.0`

**Background:** The sentence-transformers library tries to download `paraphrase-multilingual-MiniLM-L6-v2` from HuggingFace Hub. If `HF_TOKEN` is set in the environment to an expired/invalid value, HuggingFace returns 401 even though the model is public. The `token=False` kwarg was intended to suppress the ambient token but doesn't work in all sentence-transformers versions. **Dan needs to either remove `HF_TOKEN` from `.env` or set it to a valid token from huggingface.co/settings/tokens.**

Since `multilingual_similarity` is NOT in `DEFAULT_METRIC_WEIGHTS` (it's observational only, not scored), returning `applicable=False` on auth errors means: no row is persisted, no 0.0 written, no score impact. A warning is logged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_language_performance.py`:
```python
"""
Tests for language_performance evaluators — all in stub/mock mode, no API calls.
"""
from unittest.mock import patch
import pytest

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
    """Non-auth errors (network, missing package) should stay applicable with 0.0 fallback."""
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
```

- [ ] **Step 2: Run test — expect FAIL**

```
.\.venv\Scripts\python.exe -m pytest tests/test_language_performance.py -v
```

Expected: both tests fail (applicable/error fields not set correctly)

- [ ] **Step 3: Update `MultilingualSimilarityEvaluator.evaluate()` in `evaluators/language_performance.py`**

Replace the current `evaluate()` method on `MultilingualSimilarityEvaluator`:

```python
    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        try:
            import numpy as np
            model = _get_multilingual_model()
            embs = model.encode(
                [model_response, expected_behavior],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            score = float(np.dot(embs[0], embs[1]))
            score = max(0.0, round(score, 4))
            lang = (context or {}).get("language", "?")
            reason = f"Multilingual embedding cosine similarity = {score:.3f} (lang={lang})"
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=score,
                passed=score >= 0.5,
                reason=reason,
            )
        except Exception as exc:
            exc_str = str(exc)
            is_auth_error = "401" in exc_str or "unauthorized" in exc_str.lower()
            if is_auth_error:
                _logger.warning(
                    "MultilingualSimilarityEvaluator: 401 auth error from HuggingFace — "
                    "check HF_TOKEN in .env (remove it or set a valid token from "
                    "huggingface.co/settings/tokens). Skipping metric row."
                )
                return MetricOutput(
                    dimension=self.dimension,
                    metric_name=self.metric_name,
                    score=0.0,
                    passed=False,
                    reason=f"Auth error (401) — HF_TOKEN invalid or expired. No score recorded.",
                    applicable=False,
                    error=True,
                )
            # Non-auth errors: keep the row but flag as error, score=0.0
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=0.0,
                passed=False,
                reason=f"Multilingual similarity unavailable: {exc}",
                error=True,
            )
```

- [ ] **Step 4: Run test — expect PASS**

```
.\.venv\Scripts\python.exe -m pytest tests/test_language_performance.py -v
```

- [ ] **Step 5: Run full suite — confirm no regressions**

```
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

---

## Task 4: Rate-limit resilience — outer retry in deepeval evaluators + tighter semaphore

**Files:**
- Modify: `evaluators/language_performance.py` — `SemanticSimilarityEvaluator`, `AnswerCompletenessEvaluator`
- Modify: `evaluators/hallucination.py` — `FaithfulnessEvaluator`
- Modify: `orchestration/dispatcher.py` — reduce `_judge_sem` from `Semaphore(10)` to `Semaphore(3)`
- Test: `tests/test_sprint1.py`

**Background:** deepeval uses `tenacity` internally to retry LLM calls. When its internal retries are exhausted, it raises `tenacity.RetryError` wrapping the original `openai.RateLimitError`. Our catch block sees this as a generic Exception and immediately returns `score=0.5`. We add an outer retry (2 extra attempts with 20s / 40s + jitter sleeps) that specifically detects rate-limit errors. Additionally, reducing the semaphore from 10 to 3 means at most 3 concurrent LLM judge calls, dramatically reducing the burst that triggers rate limiting.

A helper `_is_rate_limit_error(exc)` is added at module level (shared pattern across evaluators). On error, `MetricOutput.error=True` is set so the dispatcher can track error rates.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sprint1.py`:

```python
from unittest.mock import patch, MagicMock
import time


def test_semantic_similarity_rate_limit_sets_error_flag():
    """Rate-limit fallback must set error=True, not silently write 0.5 as a real score."""
    from evaluators.language_performance import SemanticSimilarityEvaluator
    mock_model = MagicMock()
    ev = SemanticSimilarityEvaluator(model=mock_model)
    # Simulate deepeval raising a rate-limit RetryError on every attempt
    rate_exc = Exception("RetryError[<Future raised RateLimitError>]")
    with patch.object(ev, "_model", mock_model):
        with patch(
            "evaluators.language_performance.AnswerRelevancyMetric"
        ) as MockMetric:
            MockMetric.return_value.measure.side_effect = rate_exc
            result = ev.evaluate("p", "r", "e")
    assert result.error is True
    assert result.score == 0.5


def test_faithfulness_rate_limit_sets_error_flag():
    """FaithfulnessEvaluator rate-limit fallback must set error=True."""
    from evaluators.hallucination import FaithfulnessEvaluator
    mock_model = MagicMock()
    ev = FaithfulnessEvaluator(model=mock_model)
    rate_exc = Exception("RetryError[<Future raised RateLimitError>]")
    with patch(
        "evaluators.hallucination.FaithfulnessMetric"
    ) as MockMetric:
        MockMetric.return_value.measure.side_effect = rate_exc
        result = ev.evaluate("p", "r", "e")
    assert result.error is True
    assert result.score == 0.5
```

- [ ] **Step 2: Run tests — expect FAIL**

```
.\.venv\Scripts\python.exe -m pytest tests/test_sprint1.py::test_semantic_similarity_rate_limit_sets_error_flag tests/test_sprint1.py::test_faithfulness_rate_limit_sets_error_flag -v
```

Expected: FAIL — `result.error` is `False`

- [ ] **Step 3: Add `_is_rate_limit_error` helper and outer retry to `evaluators/language_performance.py`**

Add after the imports, before `SemanticSimilarityEvaluator`:

```python
import random
import time as _time


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect rate-limit errors from deepeval's tenacity RetryError wrapping openai.RateLimitError."""
    s = str(exc).lower()
    return "ratelimiterror" in s or "rate limit" in s or "429" in s


_DEEPEVAL_OUTER_RETRIES = 2
_DEEPEVAL_RETRY_BASE_S  = 20.0   # 20s, then 40s — let the rate-limit window reset
```

Update `SemanticSimilarityEvaluator.evaluate()` — replace the `if self._model:` block:

```python
        if self._model:
            score, reason = 0.5, "AnswerRelevancyMetric unavailable: not yet run"
            error = False
            for attempt in range(_DEEPEVAL_OUTER_RETRIES + 1):
                try:
                    metric = AnswerRelevancyMetric(threshold=0.6, model=self._model, async_mode=False)
                    test_case = LLMTestCase(input=prompt, actual_output=model_response)
                    metric.measure(test_case)
                    score = metric.score
                    reason = metric.reason or "No reason provided."
                    error = False
                    break
                except Exception as exc:
                    if _is_rate_limit_error(exc) and attempt < _DEEPEVAL_OUTER_RETRIES:
                        delay = _DEEPEVAL_RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 5)
                        _time.sleep(delay)
                        continue
                    score, reason, error = 0.5, f"AnswerRelevancyMetric unavailable: {exc}", True
                    break
        else:
            # Stub fallback — token overlap
            expected_tokens = set(expected_behavior.lower().split())
            response_tokens = set(model_response.lower().split())
            overlap = len(expected_tokens & response_tokens)
            score = min(overlap / max(len(expected_tokens), 1), 1.0)
            reason = f"Token overlap: {overlap}/{len(expected_tokens)} expected tokens matched."
            error = False

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=reason,
            error=error,
        )
```

Update `AnswerCompletenessEvaluator.evaluate()` — replace `if self._model:` block:

```python
        if self._model:
            score, reason = 0.5, "GEval unavailable: not yet run"
            error = False
            for attempt in range(_DEEPEVAL_OUTER_RETRIES + 1):
                try:
                    metric = GEval(
                        name="answer_completeness",
                        criteria=(
                            "Does the actual output completely address all required elements "
                            "of the expected output, in the appropriate language?"
                        ),
                        evaluation_steps=self._EVALUATION_STEPS,
                        evaluation_params=[
                            SingleTurnParams.INPUT,
                            SingleTurnParams.ACTUAL_OUTPUT,
                            SingleTurnParams.EXPECTED_OUTPUT,
                        ],
                        model=self._model,
                        threshold=0.5,
                        async_mode=False,
                    )
                    test_case = LLMTestCase(
                        input=prompt, actual_output=model_response, expected_output=expected_behavior
                    )
                    metric.measure(test_case)
                    score = metric.score
                    reason = metric.reason or "No reason provided."
                    error = False
                    break
                except Exception as exc:
                    if _is_rate_limit_error(exc) and attempt < _DEEPEVAL_OUTER_RETRIES:
                        delay = _DEEPEVAL_RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 5)
                        _time.sleep(delay)
                        continue
                    score, reason, error = 0.5, f"GEval unavailable: {exc}", True
                    break
        else:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            reason = "Stub — DeepEval model not configured."
            error = False

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.5,
            reason=reason,
            error=error,
        )
```

- [ ] **Step 4: Apply same pattern to `evaluators/hallucination.py` — `FaithfulnessEvaluator`**

Add after the imports in `evaluators/hallucination.py`:

```python
import random
import time as _time

from evaluators.language_performance import _is_rate_limit_error, _DEEPEVAL_OUTER_RETRIES, _DEEPEVAL_RETRY_BASE_S
```

Update `FaithfulnessEvaluator.evaluate()` — replace `if self._model:` block:

```python
        if self._model:
            score, reason = 0.5, "FaithfulnessMetric unavailable: not yet run"
            error = False
            for attempt in range(_DEEPEVAL_OUTER_RETRIES + 1):
                try:
                    metric = FaithfulnessMetric(threshold=0.7, model=self._model, async_mode=False)
                    test_case = LLMTestCase(
                        input=prompt,
                        actual_output=model_response,
                        retrieval_context=[expected_behavior],
                    )
                    metric.measure(test_case)
                    score = metric.score
                    reason = metric.reason or "No reason provided."
                    error = False
                    break
                except Exception as exc:
                    if _is_rate_limit_error(exc) and attempt < _DEEPEVAL_OUTER_RETRIES:
                        delay = _DEEPEVAL_RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 5)
                        _time.sleep(delay)
                        continue
                    score, reason, error = 0.5, f"FaithfulnessMetric unavailable: {exc}", True
                    break
        else:
            FABRICATION_SIGNALS = [
                "as of my knowledge cutoff",
                "i cannot verify",
                "i'm not sure but",
            ]
            has_signal = any(s in model_response.lower() for s in FABRICATION_SIGNALS)
            score = 0.4 if has_signal else 0.8
            reason = "Stub — DeepEval model not configured."
            error = False

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.7,
            reason=reason,
            error=error,
        )
```

- [ ] **Step 5: Reduce `_judge_sem` from `Semaphore(10)` to `Semaphore(3)` in `orchestration/dispatcher.py`**

Find the line:
```python
_judge_sem = asyncio.Semaphore(10)
```
Change to:
```python
_judge_sem = asyncio.Semaphore(3)
```

- [ ] **Step 6: Run tests — expect PASS**

```
.\.venv\Scripts\python.exe -m pytest tests/test_sprint1.py::test_semantic_similarity_rate_limit_sets_error_flag tests/test_sprint1.py::test_faithfulness_rate_limit_sets_error_flag -v
```

- [ ] **Step 7: Run full suite**

```
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

---

## Task 5: Honest confidence_flag — `low_coverage` on high metric error rate

**Files:**
- Modify: `scoring/engine.py` — add `metric_error_rates` param, gate confidence flag
- Modify: `orchestration/dispatcher.py` — compute and pass `metric_error_rates`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `MetricOutput.error` from Task 1 (dispatcher reads `output.error` to count failures)
- Produces: `compute_composite_score(..., metric_error_rates: dict[str, float] | None = None)` — sets `confidence_flag = "low_coverage"` when any metric that contributes to scoring has error rate > 0.5

Threshold: 50% (if more than half the evaluations for a scored metric are infrastructure errors, the dimension score is unreliable).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scoring.py`:

```python
def test_confidence_flag_low_coverage_on_high_metric_error_rate():
    """High error rate on a scored metric must set confidence_flag to low_coverage."""
    scores = {dim: [0.8] * 10 for dim in DEFAULT_WEIGHTS}
    # semantic_similarity is a scored metric (50% weight in language_performance)
    # If 80% of its evals were errors, flag the run as low_coverage
    result = compute_composite_score(
        scores,
        metric_error_rates={"semantic_similarity": 0.80},
    )
    assert result.confidence_flag == "low_coverage"
    assert "language_performance" in result.low_coverage_dimensions


def test_confidence_flag_standard_when_unscored_metric_errors():
    """Error rate on an unscored metric (chrf, multilingual_similarity) must NOT flip the flag."""
    scores = {dim: [0.8] * 10 for dim in DEFAULT_WEIGHTS}
    result = compute_composite_score(
        scores,
        metric_error_rates={"multilingual_similarity": 1.0, "chrf_score": 1.0},
    )
    assert result.confidence_flag == "standard"


def test_confidence_flag_standard_when_error_rate_below_threshold():
    """Error rate below 50% on a scored metric must NOT flip the flag."""
    scores = {dim: [0.8] * 10 for dim in DEFAULT_WEIGHTS}
    result = compute_composite_score(
        scores,
        metric_error_rates={"faithfulness": 0.45},
    )
    assert result.confidence_flag == "standard"
```

- [ ] **Step 2: Run tests — expect FAIL**

```
.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py::test_confidence_flag_low_coverage_on_high_metric_error_rate tests/test_scoring.py::test_confidence_flag_standard_when_unscored_metric_errors tests/test_scoring.py::test_confidence_flag_standard_when_error_rate_below_threshold -v
```

Expected: FAIL — `compute_composite_score` doesn't accept `metric_error_rates`

- [ ] **Step 3: Update `scoring/engine.py`**

Add constant after `FAILING_THRESHOLD`:
```python
# Metric error rate above which the dimension is marked low_coverage.
# 50%: more than half the evaluations for a scored metric were infrastructure failures.
METRIC_ERROR_RATE_THRESHOLD = 0.50
```

Add `metric_error_rates` param to `compute_composite_score` signature:
```python
def compute_composite_score(
    dimension_raw_scores: dict[str, list[float]],
    weights: dict[str, float] | None = None,
    item_counts: dict[str, int] | None = None,
    dimension_metric_scores: dict[str, dict[str, list[float]]] | None = None,
    metric_weights: dict[str, dict[str, float]] | None = None,
    metric_error_rates: dict[str, float] | None = None,
) -> ScoringResult:
```

Inside `compute_composite_score`, after the `low_coverage_dims` population from item counts, add:

```python
    # Dimensions where a scored metric has a high infrastructure error rate are
    # also flagged low_coverage — the score is partially composed of 0.5 fallbacks.
    if metric_error_rates:
        for dim, metrics in active_metric_weights.items():
            for metric_name in metrics:
                rate = metric_error_rates.get(metric_name, 0.0)
                if rate > METRIC_ERROR_RATE_THRESHOLD and dim not in low_coverage_dims:
                    low_coverage_dims.append(dim)
```

- [ ] **Step 4: Update `orchestration/dispatcher.py` — compute `metric_error_rates`**

After `item_counts.update(_distinct_item_counts(all_outputs, n_evaluators))` and before the bias evaluator block, add:

```python
                # Track per-metric error rates to gate confidence_flag in the scoring engine.
                # Only outputs that were applicable (not dropped) are counted.
                _metric_error_counts: dict[str, int] = {}
                _metric_total_counts: dict[str, int] = {}
                for _out in all_outputs:
                    if not getattr(_out, "applicable", True):
                        continue
                    _metric_total_counts[_out.metric_name] = _metric_total_counts.get(_out.metric_name, 0) + 1
                    if getattr(_out, "error", False):
                        _metric_error_counts[_out.metric_name] = _metric_error_counts.get(_out.metric_name, 0) + 1
                metric_error_rates: dict[str, float] = {
                    name: _metric_error_counts.get(name, 0) / total
                    for name, total in _metric_total_counts.items()
                    if total > 0
                }
```

Update the `compute_composite_score` call to pass `metric_error_rates`:

```python
                result = compute_composite_score(
                    dimension_raw_scores=dimension_scores,
                    item_counts=item_counts,
                    dimension_metric_scores=dimension_metric_scores,
                    metric_error_rates=metric_error_rates,
                )
```

- [ ] **Step 5: Run tests — expect PASS**

```
.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py -v
```

- [ ] **Step 6: Run full suite**

```
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

---

## Task 6: Single-row cohort disparity persistence + `completed_at` before JSON

**Files:**
- Modify: `orchestration/dispatcher.py`
- Test: `tests/test_bias_fairness.py`

These two dispatcher fixes are batched into one task because they touch the same code block in `dispatch_run()` (the scorecard generation section) and are each a one-line change.

**Fix A:** Write only ONE `MetricResult` row for the bias_fairness result. The current loop `for idx, response_id in response_id_by_idx.items()` writes N=80 identical rows. Replace with a single write using `next(iter(response_id_by_idx.values()))`.

**Fix B:** Set `run.completed_at` before calling `generate_scorecard_json` so the JSON artefact captures the real timestamp (currently `None`).

- [ ] **Step 1: Write tests**

Add to `tests/test_bias_fairness.py`:

```python
def test_cohort_disparity_result_is_single_output():
    """compute_run_disparity returns a single MetricOutput — callers must not duplicate it."""
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 20
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    # Verify it's a single output object, not a list
    from evaluators.base import MetricOutput
    assert isinstance(result, MetricOutput)
    assert result.metric_name == "cohort_disparity"
```

This test doesn't directly test the dispatcher, but confirms the API contract that callers should only write one row.

- [ ] **Step 2: Run test — expect PASS** (already passes; confirms existing contract)

```
.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py::test_cohort_disparity_result_is_single_output -v
```

- [ ] **Step 3: Fix dispatcher — single bias row + completed_at before JSON**

In `orchestration/dispatcher.py`, find the `# Step 4c` block:

```python
                # ── Step 4c: Run-level bias_fairness via Fairlearn ─────────────
                ...
                for idx, response_id in response_id_by_idx.items():
                    session.add(MetricResult(
                        id=uuid.uuid4(),
                        response_id=response_id,
                        dimension=bias_result.dimension,
                        metric_name=bias_result.metric_name,
                        score=bias_result.score,
                        passed=bias_result.passed,
                        reason=bias_result.reason,
                        extra=bias_result.extra,
                    ))
```

Replace the `for` loop with a single-row write:

```python
                # ── Step 4c: Run-level bias_fairness via Fairlearn ─────────────
                bias_cohorts = [item.get("cohort", "") for item in all_items]
                bias_outcomes = [
                    (sum(item_passed_flags[idx]) / len(item_passed_flags[idx]) >= 0.5)
                    if item_passed_flags[idx] else False
                    for idx in range(len(all_items))
                ]
                bias_result = CohortDisparityEvaluator().compute_run_disparity(bias_cohorts, bias_outcomes)

                dimension_scores["bias_fairness"] = [bias_result.score] * len(all_items)
                item_counts["bias_fairness"] = len(all_items)

                # Persist exactly ONE MetricResult for the run-level bias computation —
                # it's a single aggregate result, not per-item, so N copies would be noise.
                if response_id_by_idx:
                    first_response_id = next(iter(response_id_by_idx.values()))
                    session.add(MetricResult(
                        id=uuid.uuid4(),
                        response_id=first_response_id,
                        dimension=bias_result.dimension,
                        metric_name=bias_result.metric_name,
                        score=bias_result.score,
                        passed=bias_result.passed,
                        reason=bias_result.reason,
                        extra=bias_result.extra,
                    ))
```

Now fix `completed_at` before JSON. Find the `# Step 6b` block:

```python
                # ── Step 6b: Generate PDF and JSON artefacts ──────────────────
                try:
                    from reporting.generator import generate_scorecard_json, generate_scorecard_pdf
                    scorecard.pdf_path  = generate_scorecard_pdf(scorecard, run, assessment)
                    scorecard.json_path = generate_scorecard_json(scorecard, run, assessment)
```

Add `run.completed_at` assignment BEFORE the artefact generation:

```python
                # ── Step 6b: Generate PDF and JSON artefacts ──────────────────
                # Set completed_at now so the JSON artefact captures the real timestamp.
                run.completed_at = datetime.utcnow()
                try:
                    from reporting.generator import generate_scorecard_json, generate_scorecard_pdf
                    scorecard.pdf_path  = generate_scorecard_pdf(scorecard, run, assessment)
                    scorecard.json_path = generate_scorecard_json(scorecard, run, assessment)
```

Then in `# Step 7`, the `run.completed_at = datetime.utcnow()` line is now redundant (already set), but keep `session.add(run); session.commit()` to persist the state:

```python
                # ── Step 7: Mark COMPLETED ────────────────────────────────────
                run.status = RunStatus.COMPLETED
                # completed_at was already set before artefact generation (Step 6b)
                session.add(run)
                session.commit()
                logger.info("Run completed", run_id=run_id, score=result.composite_score)
```

- [ ] **Step 4: Run full suite**

```
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all tests pass.

---

## Task 7: Create branch and final verification

- [ ] **Step 1: Create branch**

```
git checkout -b fix/inspection-anomalies
```

- [ ] **Step 2: Run full test suite from clean state**

```
.\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all 187 original + new tests pass, 0 failed.

- [ ] **Step 3: Stage and show diff**

```
git diff --stat
git diff
```

Report results to user before any commit.
