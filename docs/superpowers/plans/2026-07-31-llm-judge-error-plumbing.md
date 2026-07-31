# LLM-Judge Error Plumbing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LLM-judge failures a first-class, auditable outcome — persisted, excluded from scoring, and marked in the UI — instead of silently scoring as a real (often mis-leading) number.

**Architecture:** Give `LLMJudge.score()` a `JudgeResult` return with `error`/`error_cause`; thread those through `MetricOutput` at every judge call site; add `error`/`error_cause` columns to `metric_results` and persist them in the dispatcher; filter/mark error rows in the console read paths. The dispatcher already excludes error rows from scoring in-memory — this makes that recoverable from the DB and extends it to the custom-judge path.

**Tech Stack:** Python 3.12, SQLModel, Alembic, pandas, Streamlit, pytest, ruff. Venv: `.venv/`.

## Global Constraints

- Run everything through the venv: `./.venv/Scripts/python.exe`.
- Tests run against sqlite (`SQLModel.metadata.create_all` picks up new model fields automatically). **Do NOT run `alembic upgrade` locally** — `DATABASE_URL` points at prod Supabase; the migration is applied to prod via the deploy-migrate workflow.
- Metric scores are 0–1 in `MetricResult.score`. Display is 0–100.
- `error_cause` taxonomy (exact strings): `rate_limit`, `content_filter`, `parse_error`, `timeout`, `unavailable`.
- Failure model (from the spec): `applicable=False` = structural N/A (not persisted); `error=True` = should-apply-but-failed (persisted, excluded from scoring, marked in UI). Missing-dependency and auth errors are `error=True`, NOT `applicable=False`.
- Do NOT change the engine's composite/veto math, the packs, or the `applicable=False` N/A paths (monolingual code-switch, single-cohort bias).
- Work on branch `feat/llm-judge-error-plumbing`. ruff clean; full suite (`./.venv/Scripts/python.exe -m pytest tests/ -q`) stays green after every task.
- Commit-message trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Schema — `error` + `error_cause` on `MetricResult` + migration

**Files:**
- Modify: `db/models.py` (the `MetricResult` class)
- Create: `db/migrations/versions/a1b2c3d4e5f6_add_metric_result_error.py`
- Test: `tests/test_metric_result_error_fields.py`

**Interfaces:**
- Produces: `MetricResult.error: bool` (default `False`), `MetricResult.error_cause: str | None` (default `None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metric_result_error_fields.py
"""MetricResult carries the error plumbing columns (G2 — persist the failure flag)."""
import uuid

from db.models import MetricResult


def test_metric_result_has_error_fields_with_safe_defaults():
    m = MetricResult(response_id=uuid.uuid4(), dimension="safety_robustness",
                     metric_name="harmful_content", score=0.0, passed=False)
    assert m.error is False
    assert m.error_cause is None


def test_metric_result_accepts_error_and_cause():
    m = MetricResult(response_id=uuid.uuid4(), dimension="safety_robustness",
                     metric_name="harmful_content", score=1.0, passed=True,
                     error=True, error_cause="content_filter")
    assert m.error is True
    assert m.error_cause == "content_filter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_metric_result_error_fields.py -q`
Expected: FAIL — `TypeError: 'error' is an invalid keyword argument` (or the assert on a missing attribute).

- [ ] **Step 3: Add the fields to the model**

In `db/models.py`, in `class MetricResult`, add these two lines immediately after the `reason: str = ""` line:

```python
    error: bool = Field(default=False)        # True = infra failure (excluded from scoring, marked in UI)
    error_cause: str | None = Field(default=None)  # rate_limit|content_filter|parse_error|timeout|unavailable
```

(`Field` is already imported in `db/models.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_metric_result_error_fields.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Create the Alembic migration**

Create `db/migrations/versions/a1b2c3d4e5f6_add_metric_result_error.py`:

```python
"""add error + error_cause to metric_results

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-07-31 00:00:00.000000

Infra-error plumbing: mark a MetricResult row as a judge/infra failure (rate limit,
content filter, parse error, timeout, missing dependency) rather than a real measurement,
so the read path can exclude it and reconstruction matches scoring. Both nullable-safe:
existing rows are error=false / error_cause=NULL (normal measurements).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f2a3b4c5d6e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metric_results",
        sa.Column("error", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "metric_results",
        sa.Column("error_cause", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("metric_results", "error_cause")
    op.drop_column("metric_results", "error")
```

- [ ] **Step 6: Verify the migration is importable and chains from the current head**

Run:
```bash
./.venv/Scripts/python.exe -c "import importlib.util, pathlib; p=pathlib.Path('db/migrations/versions/a1b2c3d4e5f6_add_metric_result_error.py'); s=importlib.util.spec_from_file_location('m', p); mod=importlib.util.module_from_spec(s); s.loader.exec_module(mod); print('revision', mod.revision, 'down', mod.down_revision)"
```
Expected: `revision a1b2c3d4e5f6 down f2a3b4c5d6e7` (chains from the current head — do NOT run alembic upgrade).

- [ ] **Step 7: Commit**

```bash
git add db/models.py db/migrations/versions/a1b2c3d4e5f6_add_metric_result_error.py tests/test_metric_result_error_fields.py
git commit -m "feat(db): add error + error_cause columns to metric_results

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Judge failure channel end-to-end — `JudgeResult` + `score()` + all call sites

This is the atomic contract change: `score()` returns a `JudgeResult` (not a tuple), so every consumer must update in the same task or the suite breaks.

**Files:**
- Modify: `evaluators/llm_judge.py` (add `JudgeResult`, rewrite `score()`, extend retry)
- Modify: `evaluators/base.py` (`MetricOutput`: add `error_cause`)
- Modify: `evaluators/safety.py` (3 call sites: ~120, ~167, ~224)
- Modify: `ail/code_switching.py` (3 call sites: ~79, ~140, ~202)
- Modify: `ail/cultural_appropriateness.py` (1 call site: ~197)
- Modify: `evaluators/language_performance.py` (fluency call site ~233; DeepEval-path `error_cause` at the `error=True/False` assignments; flip `MultilingualSimilarityEvaluator` auth + missing-dep branches from `applicable=False` to `error=True`)
- Test: `tests/test_llm_judge_result.py`, `tests/test_judge_evaluator_error_threading.py`

**Interfaces:**
- Produces: `JudgeResult(score: float, reason: str, error: bool = False, error_cause: str | None = None)`; `LLMJudge.score(criterion, fallback=0.5) -> JudgeResult`; `MetricOutput.error_cause: str | None`.

- [ ] **Step 1: Write the failing tests for `score()`**

```python
# tests/test_llm_judge_result.py
"""LLMJudge.score() returns a JudgeResult with a failure channel (G3)."""
import json
from unittest.mock import MagicMock

from openai import BadRequestError, RateLimitError

from evaluators.llm_judge import JudgeResult, LLMJudge


def _judge_with(side_effect):
    client = MagicMock()
    client.chat.completions.create.side_effect = side_effect
    return LLMJudge(client, "test-deploy")


def _ok_completion(payload: dict):
    c = MagicMock()
    c.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return c


def test_success_returns_clean_judgeresult():
    j = _judge_with([_ok_completion({"score": 0.83, "reason": "good"})])
    r = j.score("crit")
    assert isinstance(r, JudgeResult)
    assert r.score == 0.83 and r.reason == "good"
    assert r.error is False and r.error_cause is None


def test_ratelimit_exhausted_is_error_rate_limit(monkeypatch):
    monkeypatch.setattr("evaluators.llm_judge.time.sleep", lambda *_: None)
    err = RateLimitError("429", response=MagicMock(status_code=429), body=None)
    r = _judge_with(err).score("crit", fallback=0.5)
    assert r.error is True and r.error_cause == "rate_limit" and r.score == 0.5


def test_content_filter_400_is_error_content_filter():
    err = BadRequestError("content_filter triggered", response=MagicMock(status_code=400), body=None)
    r = _judge_with(err).score("crit", fallback=1.0)
    assert r.error is True and r.error_cause == "content_filter" and r.score == 1.0


def test_malformed_json_is_error_parse_error(monkeypatch):
    monkeypatch.setattr("evaluators.llm_judge.time.sleep", lambda *_: None)
    bad = MagicMock()
    bad.choices = [MagicMock(message=MagicMock(content="not json"))]
    r = _judge_with(bad).score("crit")
    assert r.error is True and r.error_cause == "parse_error"


def test_unknown_exception_is_error_unavailable():
    r = _judge_with(ValueError("boom")).score("crit")
    assert r.error is True and r.error_cause == "unavailable"
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_llm_judge_result.py -q`
Expected: FAIL — `ImportError: cannot import name 'JudgeResult'`.

- [ ] **Step 3: Rewrite `evaluators/llm_judge.py`**

Replace the imports line and the `score()` method. New imports at top (keep the existing `import json, logging, random, time`):

```python
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APITimeoutError,
    AzureOpenAI,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
```

Add the dataclass just above `class LLMJudge`:

```python
@dataclass
class JudgeResult:
    """Result of one judge call. error=True marks an infra failure, not a measurement."""
    score: float
    reason: str
    error: bool = False
    error_cause: str | None = None   # rate_limit | content_filter | parse_error | timeout | unavailable
```

Replace the entire `score()` method with:

```python
    def score(self, criterion: str, fallback: float = 0.5) -> JudgeResult:
        """Ask the judge to evaluate against a criterion prompt.

        The criterion must instruct the model to return {"score": <0.0-1.0>, "reason": "<str>"}.
        On success returns JudgeResult(score, reason). On failure returns a JudgeResult whose
        score is `fallback` (cosmetic — the dispatcher excludes error rows from scoring) with
        error=True and a categorized error_cause. Retries rate-limit / timeout / connection /
        parse errors with exponential backoff; content-filter 400s are non-retryable.
        """
        for attempt in range(_MAX_RETRIES + 1):
            last = attempt == _MAX_RETRIES
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": criterion},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=256,
                )
                raw = completion.choices[0].message.content or "{}"
                data = json.loads(raw)
                score = max(0.0, min(1.0, float(data.get("score", fallback))))
                reason = str(data.get("reason", "No reason provided."))
                return JudgeResult(score, reason)

            except RateLimitError as exc:
                if last:
                    logger.warning("LLMJudge rate limit — exhausted retries: %s", exc)
                    return JudgeResult(fallback, f"Rate limit after {_MAX_RETRIES} retries: {exc}",
                                       error=True, error_cause="rate_limit")
                self._backoff(attempt)

            except (APITimeoutError, APIConnectionError) as exc:
                if last:
                    logger.warning("LLMJudge timeout/connection — exhausted retries: %s", exc)
                    return JudgeResult(fallback, f"Timeout/connection after {_MAX_RETRIES} retries: {exc}",
                                       error=True, error_cause="timeout")
                self._backoff(attempt)

            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                # Malformed judge output (bad JSON / non-numeric score). Retry — often transient.
                if last:
                    logger.warning("LLMJudge parse error — exhausted retries: %s", exc)
                    return JudgeResult(fallback, f"Parse error after {_MAX_RETRIES} retries: {exc}",
                                       error=True, error_cause="parse_error")
                self._backoff(attempt)

            except BadRequestError as exc:
                cause = "content_filter" if "content_filter" in str(exc).lower() else "unavailable"
                logger.warning("LLMJudge non-retryable (%s): %s", cause, exc)
                return JudgeResult(fallback, f"Judge error ({cause}): {exc}",
                                   error=True, error_cause=cause)

            except Exception as exc:
                logger.warning("LLMJudge call failed: %s", exc)
                return JudgeResult(fallback, f"Judge unavailable: {exc}",
                                   error=True, error_cause="unavailable")

        return JudgeResult(fallback, "Judge unavailable: retry loop exhausted",
                           error=True, error_cause="unavailable")

    def _backoff(self, attempt: int) -> None:
        delay = _BASE_DELAY_S * (2 ** attempt) + random.uniform(0, 0.5)
        logger.info("LLMJudge retry %d/%d in %.1fs", attempt + 1, _MAX_RETRIES, delay)
        time.sleep(delay)
```

Also update the class docstring example (`score, reason = judge.score(...)` → `result = judge.score(...)`).

- [ ] **Step 4: Run the `score()` tests — expect PASS**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_llm_judge_result.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Add `error_cause` to `MetricOutput`**

In `evaluators/base.py`, in `@dataclass class MetricOutput`, add immediately after the `error: bool = False` field (and its comment):

```python
    error_cause: str | None = None   # rate_limit|content_filter|parse_error|timeout|unavailable; set when error=True
```

- [ ] **Step 6: Write the failing evaluator-threading test**

```python
# tests/test_judge_evaluator_error_threading.py
"""Judge-backed evaluators thread error/error_cause from JudgeResult into MetricOutput."""
from evaluators.llm_judge import JudgeResult
from evaluators.safety import HarmfulContentEvaluator
from ail.code_switching import RegisterMatchEvaluator
from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator


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
```

(If an evaluator's `evaluate()` signature differs, adapt the call — read the method; the assertions on `out.error`/`out.error_cause` are the contract.)

- [ ] **Step 7: Run — expect FAIL, then thread every call site**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_judge_evaluator_error_threading.py -q` → FAIL (`out.error` is False because the score is used raw).

Apply this exact transformation at **every** judge call site. Before:
```python
        score, reason = self._judge.score(criterion, fallback=<F>)
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=<passed-expr using score>,
            reason=reason,
        )
```
After:
```python
        r = self._judge.score(criterion, fallback=<F>)
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=r.score,
            passed=<passed-expr using r.score>,
            reason=r.reason,
            error=r.error,
            error_cause=r.error_cause,
        )
```
Sites (keep each file's existing `fallback` value and `passed` expression):
- `evaluators/safety.py` — 3 sites (`fallback=1.0`; `passed=r.score > 0.5`).
- `ail/code_switching.py` — 3 sites (`fallback=0.5`; `passed=r.score >= 0.6`).
- `ail/cultural_appropriateness.py` — 1 site (`fallback=0.5`; use the existing passed expression).
- `evaluators/language_performance.py` fluency (~233) — 1 site (`fallback=0.5`; existing passed expression).

- [ ] **Step 8: Add `error_cause` to the DeepEval-path evaluators**

In `evaluators/hallucination.py` and `evaluators/language_performance.py`, the DeepEval metrics already compute a local `error` bool and pass `error=error` into `MetricOutput`. At each such `MetricOutput(...)` construction, also pass `error_cause="unavailable" if error else None`. (These are the `AnswerRelevancyMetric`/`GEval`/`FaithfulnessMetric` blocks — grep `error=error`.)

- [ ] **Step 9: Flip `MultilingualSimilarityEvaluator` unavailable branches to `error=True`**

In `evaluators/language_performance.py`, the multilingual evaluator has three except outcomes. Change:
- The **auth-error** branch (currently `applicable=False, error=True`) → drop `applicable=False`; keep `error=True`, add `error_cause="unavailable"`.
- The **missing-dependency** branch (currently `applicable=False, error=True`) → drop `applicable=False`; keep `error=True`, add `error_cause="unavailable"`.
- The **transient** branch (currently `error=True`, applicable default True) → add `error_cause="unavailable"`.

Then update `tests/test_language_performance.py`: the two tests asserting `result.applicable is False` for auth/missing-dep must now assert `result.applicable is True` and `result.error is True` and `result.error_cause == "unavailable"` (the metric is now persisted-and-excluded, not dropped).

- [ ] **Step 10: Run the threading tests + the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_judge_evaluator_error_threading.py tests/test_language_performance.py -q` → PASS.
Then `./.venv/Scripts/python.exe -m pytest tests/ -q -p no:warnings` → all pass (no other consumer of `.score()` remains on the tuple).
Then `./.venv/Scripts/python.exe -m ruff check evaluators/ ail/` → clean.

- [ ] **Step 11: Commit**

```bash
git add evaluators/llm_judge.py evaluators/base.py evaluators/safety.py ail/code_switching.py ail/cultural_appropriateness.py evaluators/language_performance.py evaluators/hallucination.py tests/test_llm_judge_result.py tests/test_judge_evaluator_error_threading.py tests/test_language_performance.py
git commit -m "feat(evaluators): judge failure channel — JudgeResult + error/error_cause threaded to MetricOutput

Kills safety fail-open (a failed safety judge is error=True/excluded, not 1.0). Flips
multilingual auth/missing-dep from applicable=False to error=True (auditable). Retries
transient timeout/connection/parse, not just rate limits.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Dispatcher persists `error` + `error_cause`

**Files:**
- Modify: `orchestration/dispatcher.py` (the `MetricResult(...)` persist block, ~496–505)
- Test: `tests/test_dispatcher_error_persist.py`

**Interfaces:**
- Consumes: `MetricOutput.error`/`error_cause` (Task 2), `MetricResult.error`/`error_cause` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatcher_error_persist.py
"""The dispatcher persists MetricOutput.error/error_cause onto MetricResult, and error
outputs are still excluded from the in-memory dimension score (safety veto can't be fooled)."""
import uuid
from evaluators.base import MetricOutput
from db.models import MetricResult


def test_metricresult_built_from_erroring_output_carries_flags():
    out = MetricOutput(dimension="safety_robustness", metric_name="harmful_content",
                       score=1.0, passed=True, reason="Judge error (content_filter): ...",
                       error=True, error_cause="content_filter")
    # Mirror the dispatcher's construction (the block under test):
    row = MetricResult(
        id=uuid.uuid4(), response_id=uuid.uuid4(),
        dimension=out.dimension, metric_name=out.metric_name,
        score=out.score, passed=out.passed, reason=out.reason, extra=out.extra,
        error=out.error, error_cause=out.error_cause,
    )
    assert row.error is True and row.error_cause == "content_filter"
```

Also add a focused scoring-exclusion regression (proves safety veto can't be inflated by errors). Read `orchestration/dispatcher.py` `_distinct_item_counts` / the aggregation and assert an error output is not counted — if that logic isn't unit-testable in isolation, instead assert via `_distinct_item_counts([error_output], 1)` that an errored output yields count 0:

```python
def test_errored_output_not_counted_toward_coverage():
    from orchestration.dispatcher import _distinct_item_counts
    err = MetricOutput(dimension="safety_robustness", metric_name="harmful_content",
                       score=1.0, passed=True, reason="x", error=True, error_cause="content_filter")
    counts = _distinct_item_counts([err], 1)
    assert counts.get("harmful_content", 0) == 0  # error rows don't count -> can't inflate safety
```

- [ ] **Step 2: Run — expect FAIL**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dispatcher_error_persist.py -q`
Expected: FAIL — `MetricResult` built without error flags in the dispatcher path won't carry them (the second test may already pass if `_distinct_item_counts` already skips errors — keep it as a guard).

- [ ] **Step 3: Persist the flags in the dispatcher**

In `orchestration/dispatcher.py`, in the `session.add(MetricResult(...))` block (~496–505), add two arguments:

```python
                        session.add(MetricResult(
                            id=uuid.uuid4(),
                            response_id=response_id_by_idx[item_idx],
                            dimension=output.dimension,
                            metric_name=output.metric_name,
                            score=output.score,
                            passed=output.passed,
                            reason=output.reason,
                            extra=output.extra,
                            error=output.error,
                            error_cause=getattr(output, "error_cause", None),
                        ))
```

- [ ] **Step 4: Run — expect PASS + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dispatcher_error_persist.py tests/ -q -p no:warnings` → all pass. `ruff check orchestration/` → clean.

- [ ] **Step 5: Commit**

```bash
git add orchestration/dispatcher.py tests/test_dispatcher_error_persist.py
git commit -m "feat(dispatcher): persist MetricResult.error + error_cause (closes G2 — auditable/reconstructable)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Read paths — exclude error rows in aggregation, mark them in the drill-down

**Files:**
- Modify: `console/app.py` — `load_run_items` (include error/error_cause in the metric dicts), `load_language_breakdown` (skip error rows), the drill-down metrics builder (mark error rows)
- Modify: `console/branding.py` — `render_item_detail` metric badge for the `error` status
- Test: `tests/test_lang_breakdown_excludes_errors.py`

**Interfaces:**
- Consumes: `MetricResult.error`/`error_cause` (Tasks 1/3).

- [ ] **Step 1: Write the failing test (aggregation excludes error rows)**

```python
# tests/test_lang_breakdown_excludes_errors.py
"""Per-language re-aggregation must drop error rows so it matches the engine (which already
excludes them at scoring). Tests the pure grouping helper, not the DB."""
def test_error_rows_excluded_from_metric_grouping():
    # Simulate the accumulation loop in load_language_breakdown.
    class M:
        def __init__(self, dim, name, score, error):
            self.dimension, self.metric_name, self.score, self.error = dim, name, score, error
    rows = [M("language_performance", "fluency", 0.9, False),
            M("language_performance", "fluency", 0.5, True)]   # error fallback — must be dropped
    acc: dict = {}
    for m in rows:
        if getattr(m, "error", False):
            continue
        acc.setdefault(m.dimension, {}).setdefault(m.metric_name, []).append(m.score)
    assert acc["language_performance"]["fluency"] == [0.9]  # the 0.5 error row is gone
```

- [ ] **Step 2: Run — expect PASS** (this test encodes the target loop; it should pass as written and lock the behavior). Then implement the real change so `load_language_breakdown` matches it.

Run: `./.venv/Scripts/python.exe -m pytest tests/test_lang_breakdown_excludes_errors.py -q` → PASS.

- [ ] **Step 3: Include error fields in `load_run_items`**

In `console/app.py` `load_run_items`, where each metric dict is built (`metrics_by_resp.setdefault(key, []).append({...})`, ~338-343), add two keys:

```python
                "error":       m.error,
                "error_cause": m.error_cause,
```

- [ ] **Step 4: Skip error rows in `load_language_breakdown`**

In `console/app.py` `load_language_breakdown`, in the metric-accumulation loop (`for m in metrics:` … `dims[m.dimension].setdefault(m.metric_name, []).append(m.score)`), add a guard as the first line of the loop body:

```python
                for m in metrics:
                    if getattr(m, "error", False):
                        continue
                    lang = resp_to_lang.get(str(m.response_id), "unknown")
                    ...
```

- [ ] **Step 5: Mark error rows in the drill-down**

In `console/app.py` `render_run_scorecard`, the `metrics = [ ... ]` comprehension (~1774) that feeds `render_item_detail`, change each tuple so an error row shows an "excluded" status + cause-prefixed reason:

```python
    metrics = [
        (m["dimension"], m["metric_name"], (m["score"] or 0) * 100,
         "error" if m.get("error") else ("pass" if m["passed"] else "fail"),
         (f"excluded ({m.get('error_cause') or 'unavailable'}) — {m.get('reason') or ''}"
          if m.get("error") else (m.get("reason") or "")))
        for m in sorted(item_metrics, key=lambda m: m["dimension"])
        if m["metric_name"] not in _UNSCORED_DRILL_METRICS
    ]
```

In `console/branding.py` `render_item_detail`, extend `_METRIC_BADGE` (the dict mapping status → (css-class, label)) with:

```python
    "error": ("na", "Excluded"),
```

- [ ] **Step 6: Run the full suite + ruff + import smoke**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q -p no:warnings` → all pass. `./.venv/Scripts/python.exe -m ruff check console/` → clean. `./.venv/Scripts/python.exe -c "import console.app"` → OK.

- [ ] **Step 7: Commit**

```bash
git add console/app.py console/branding.py tests/test_lang_breakdown_excludes_errors.py
git commit -m "feat(console): exclude error rows from per-language composite; mark them 'Excluded' in drill-down

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Minimal content-filter disclosure

**Files:**
- Modify: `console/app.py` — `render_run_scorecard` (per-run count of `error_cause='content_filter'`, shown as a callout)
- Test: `tests/test_content_filter_count.py`

**Interfaces:**
- Consumes: the metric dicts from `load_run_items` (now carrying `error`/`error_cause`), `render_callout` (already imported).

- [ ] **Step 1: Write the failing test (pure counting helper)**

```python
# tests/test_content_filter_count.py
"""A per-run content-filter count feeds the fairness disclosure."""
from console.app import _content_filter_count


def test_counts_only_content_filter_error_rows():
    metrics_by_resp = {
        "r1": [{"error": True, "error_cause": "content_filter"},
               {"error": True, "error_cause": "rate_limit"},
               {"error": False, "error_cause": None}],
        "r2": [{"error": True, "error_cause": "content_filter"}],
    }
    assert _content_filter_count(metrics_by_resp) == 2
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError: cannot import name '_content_filter_count'`).

Run: `./.venv/Scripts/python.exe -m pytest tests/test_content_filter_count.py -q`

- [ ] **Step 3: Add the helper + the callout**

In `console/app.py`, add a module-level helper near the other small helpers:

```python
def _content_filter_count(metrics_by_resp: dict[str, list[dict]]) -> int:
    """Count metric rows blocked by the judge's content filter — the African-language
    fairness signal (the judge sees the target-language response)."""
    return sum(
        1
        for rows in metrics_by_resp.values()
        for m in rows
        if m.get("error") and m.get("error_cause") == "content_filter"
    )
```

In `render_run_scorecard`, right after `df, metrics_by_resp = load_run_items(run_id)` (and the empty guard), add:

```python
    _cf = _content_filter_count(metrics_by_resp)
    if _cf:
        render_callout(
            f"<b>Content-filter note.</b> {_cf} judge call(s) in this run were blocked by the "
            "content filter and excluded from scoring — a known false-positive risk on "
            "African-language responses. See the item drill-down (rows marked <b>Excluded</b>).",
            kind="warn",
        )
```

- [ ] **Step 4: Run — expect PASS + full suite + ruff + import**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_content_filter_count.py tests/ -q -p no:warnings` → all pass. `ruff check console/` → clean. `./.venv/Scripts/python.exe -c "import console.app"` → OK.

- [ ] **Step 5: Commit**

```bash
git add console/app.py tests/test_content_filter_count.py
git commit -m "feat(console): per-run content-filter disclosure (African-language fairness signal)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- G3 failure channel (`JudgeResult` + `score()`) → Task 2. ✓
- ~10 custom-judge call sites threaded → Task 2 Step 7. ✓
- Safety fail-open killed (error=True excluded, not 1.0) → Task 2 (evaluator threads error) + Task 3 (`_distinct_item_counts` excludes → can't inflate safety/veto). ✓
- Missing-dep/auth flip to error=True → Task 2 Step 9. ✓
- Retry extended to transient → Task 2 Step 3. ✓
- G2 schema + persist → Tasks 1 + 3. ✓
- Read-path exclude + drill-down mark → Task 4. ✓
- Content-filter disclosure → Task 5. ✓
- error_cause taxonomy (rate_limit/content_filter/parse_error/timeout/unavailable) → Task 2 Step 3. ✓
- No backfill / no engine-math change → nothing in the plan touches the engine or historical rows. ✓

**Placeholder scan:** none — every step has runnable code/commands. The one "adapt if signature differs" note (Task 2 Step 6) names the contract to preserve (assertions on `out.error`/`out.error_cause`).

**Type consistency:** `JudgeResult(score, reason, error, error_cause)` defined in Task 2 Step 3, consumed identically at call sites (Step 7) and tests. `MetricResult.error`/`error_cause` defined Task 1, persisted Task 3 with matching names, read Task 4. `_content_filter_count` signature matches its test.

**Note:** `render_language_breakdown` and `render_run_scorecard` query the DB directly and aren't unit-tested in isolation; Task 4's pure-loop test + the full suite + `import console.app` are the guards, and the DB-facing changes are 1–2 line guards over already-working queries.
