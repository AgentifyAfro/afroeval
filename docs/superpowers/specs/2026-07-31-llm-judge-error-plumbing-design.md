# Design — LLM-judge error plumbing

**Date:** 2026-07-31
**Status:** Approved design, pre-implementation
**Author:** Dan Haile (with Claude), grounded in a CTO-agent review

## Problem

When an LLM-judge call fails, AfroEval records the failure as if it were a real measurement.
Two compounding defects:

**G3 — the judge has no failure channel.** `evaluators/llm_judge.py:61` `score()` returns
`tuple[float, str]` and, on *any* error (rate-limit exhaustion, content-filter `BadRequestError`,
JSON parse error, any exception — lines 88–108), returns `(fallback, error_message)`. The caller
gets a number and a string; an infra failure is indistinguishable from a genuine score. Only the
DeepEval-path evaluators (`hallucination.py`, `language_performance.py` — 4 metrics) can set the
`error` flag at all. Every custom-judge evaluator **cannot**: `cultural_appropriateness`, the three
`code_switching` evaluators, the three `safety` evaluators, and `fluency` (~10 call sites). Worst
of all, `safety.py:120/167/224` use `fallback=1.0` — so a judge outage during a safety check
records **perfect safety**, counts toward coverage, and **cannot trip the `safety<30` veto**
(`scoring/engine.py`). Fail-open on the one dimension that must fail closed.

**G2 — the flag that exists never reaches the database.** `MetricResult` (`db/models.py`) has no
`error` column. The dispatcher uses `output.error` **in memory** to exclude error rows from the
score, pass-rate, and coverage aggregates (`orchestration/dispatcher.py:487, 513` — "so a 429
can't drag a dimension toward the 0.5 fallback"), which is correct at scoring time — but it
**drops the flag at persist** (`dispatcher.py:496–505` writes score/passed/reason/extra only). So
nothing reading `metric_results` can tell an infra-error fallback from a real score. Archived runs
cannot be reconstructed or audited: a prior review found ~50 archived runs diverging on
reconstruction, worst case **19.2 composite points**. This directly attacks the product thesis —
"defensible down to the individual test case."

**Also:** content-filter failures bias against African languages — the judge prompt embeds the
African-language model response, and Azure's content filter false-positives more often on that
content, so the judge is more likely to fail (→ silent fallback) on exactly the languages AfroEval
exists to evaluate fairly. And retry today covers only `RateLimitError`; transient network/timeout
errors get an immediate fallback.

**Live impact today = 0** error-shaped rows across 1,837 non-archived metric rows. This is a
**latent architecture gap**, not a data problem — easy to leave, expensive to discover during a
client run.

## The failure model (semantic core)

Three distinct outcomes for one metric on one item:

| Outcome | Meaning | `applicable` | `error` | Persisted | Scored | Drill-down |
|---|---|---|---|---|---|---|
| **Measured** | Normal result | `True` | `False` | yes | yes | shown |
| **N/A** | Metric doesn't apply, or can't run this deployment (monolingual code-switch, single-cohort bias, **missing dependency**) | `False` | — | **no** | no | not shown |
| **Infra error** | Metric applies + could run, but the measurement **failed on this item** (rate-limit, content-filter, parse, timeout) | `True` | `True` (+`error_cause`) | **yes** | **no** | marked "excluded — <cause>", not a red FAIL |

- `applicable=False` **stays "not persisted"** — preserves the prior `multilingual_similarity`
  missing-dependency decision (a config-level gap is not a per-item event; do not re-persist it).
- `error=True` is the new **auditable** path — a per-item judge failure is persisted with its
  `error_cause`, excluded from the score (dispatcher already does this in memory; now it is also
  recoverable from the DB), and read paths mark it rather than show a misleading number.
- **Safety fail-open dies here.** A failed safety judge → `error=True` → excluded → it can no
  longer post a `1.0` that suppresses the `safety<30` veto. If enough safety items fail, the
  dimension goes low-coverage → `safety_unverified` → the existing coverage gate caps the verdict
  at Conditional. No new veto logic — the fix stops failures masquerading as perfect scores.

## Components

### A. `LLMJudge.score()` — failure channel (`evaluators/llm_judge.py`)

Return a small dataclass instead of a tuple:

```python
@dataclass
class JudgeResult:
    score: float
    reason: str
    error: bool = False
    error_cause: str | None = None   # rate_limit | content_filter | parse_error | timeout | unavailable
```

- Success → `JudgeResult(score, reason)` (error `False`, cause `None`).
- `RateLimitError` after `_MAX_RETRIES` → `error_cause="rate_limit"`.
- `BadRequestError` whose payload indicates a content-filter block → `"content_filter"`; other 400s → `"unavailable"`.
- `json.JSONDecodeError` / malformed judge output → `"parse_error"`.
- timeout exceptions → `"timeout"`; anything else → `"unavailable"`.
- **Retry** now also covers transient network/timeout errors, not only `RateLimitError` (same 4×
  exponential backoff). Content-filter 400s remain non-retryable.
- The `fallback` value is still returned as `score` (cosmetic for the persisted row) but is
  excluded from scoring by virtue of `error=True`.

### B. `MetricOutput` + the ~10 judge call sites

- `evaluators/base.py`: add `error_cause: str | None = None` beside the existing `error: bool`.
- Every judge call site changes from `score, reason = self._judge.score(...)` to
  `r = self._judge.score(...)` and constructs `MetricOutput(..., score=r.score, reason=r.reason,
  error=r.error, error_cause=r.error_cause)`. Sites: `ail/cultural_appropriateness.py:197`,
  `ail/code_switching.py:79/140/202`, `evaluators/safety.py:120/167/224`,
  `evaluators/language_performance.py:233` (fluency).
- The DeepEval-path evaluators already set `error`; give them an `error_cause` too
  (`"unavailable"` or a mapped cause) so all error rows carry a cause.

### C. Schema — `MetricResult` + migration

- `db/models.py` `MetricResult`: add `error: bool = Field(default=False)` and
  `error_cause: str | None = Field(default=None)`.
- New Alembic migration: `ALTER TABLE metric_results ADD COLUMN error BOOLEAN NOT NULL DEFAULT
  false, ADD COLUMN error_cause TEXT`. Down-migration drops both.
- Prod migrations must be applied — the deploy-migrate workflow handles this (needs
  `DATABASE_URL` secret). Existing rows read as `error=false` (normal).

### D. Dispatcher (`orchestration/dispatcher.py`)

- `dispatcher.py:496–505` persists `error=output.error, error_cause=output.error_cause`.
- The in-memory scoring exclusion (`is_error`, lines 487/513) is unchanged — but persisted rows now
  carry the flag, so reconstruction from `metric_results` matches scoring (closes G2).

### E. Read paths filter on `error`

- `console/app.py:load_language_breakdown` (re-aggregates raw `MetricResult`) → drop rows where
  `error` is true before computing per-metric means, so the per-language composite matches the
  engine (which already excluded errors at scoring). This is the reconstruction fix in the console.
- Item drill-down (`render_run_scorecard` / `render_item_detail`) → error rows render as
  **"excluded — <error_cause>"**, not a red FAIL; not counted. Honest for audit, clean UI.
- Stored Scorecard composite is already correct (engine excluded errors at scoring), so
  `load_runs_summary` / `load_provider_comparison` need no change.
- **Minimal content-filter disclosure**: a per-run count of `error_cause='content_filter'` rows,
  surfaced in the console (e.g. a caption/metric) — the African-language fairness signal. A full
  dashboard is out of scope.

### F. Safety

Falls out of A–E: a failed safety judge is `error=True` → excluded → no counted `1.0` → cannot
suppress the veto; substantial safety failure → low-coverage → `safety_unverified` → existing
coverage gate caps at Conditional. No new veto logic; add a regression test.

## Testing (TDD)

- `LLMJudge.score()` returns a `JudgeResult` with the correct `error`/`error_cause` for each
  failure mode (mock the client: `RateLimitError` exhausted, `BadRequestError` content-filter,
  `json.JSONDecodeError`, timeout); success path unchanged, retry fires on transient errors.
- Each judge-backed evaluator threads `error`/`error_cause` into its `MetricOutput` on failure.
- **Safety regression:** a failed safety judge yields `error=True` (excluded), not a counted `1.0`;
  it cannot suppress the `safety<30` veto.
- Dispatcher persists `error`/`error_cause`; error rows remain excluded from scoring and are now
  reconstructable from the DB.
- `load_language_breakdown` excludes error rows; drill-down marks them.
- Alembic migration up and down.

## Rollout

- Apply the migration to prod (deploy-migrate workflow). New columns default to non-error.
- **No backfill.** Archived runs' error info was dropped historically and is unrecoverable; the
  ~50-run / 19.2-pt divergence stays a documented historical artifact. New runs are correct and
  auditable from day one.

## Non-goals

- A full content-filter *dashboard* (only a count/flag now).
- Changing or A/B-ing the judge model (decided separately — staying on `gpt-4.1-mini`).
- Re-scoring or backfilling historical/archived runs.
- Reworking the `applicable=False` N/A paths (monolingual code-switch, single-cohort bias,
  missing-dependency) — those stay as-is.

## Implementation sequencing (for the plan)

One spec, sequenced as TDD tasks: (1) schema + migration → (2) `JudgeResult` channel →
(3) evaluator call sites (~10) → (4) dispatcher persist → (5) read-path filter + drill-down
marking → (6) minimal content-filter disclosure. Steps 3–4 are broad-but-mechanical — guard with
tests first.
