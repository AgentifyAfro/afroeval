# Bias & Fairness Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `evaluators/bias_fairness.py::CohortDisparityEvaluator`'s hardcoded `score=0.75` stub with a real Fairlearn-backed disparate-impact computation, and consolidate the second, unused, also-stub `ail/informal_economy.py::InformalEconomyCohortEvaluator`.

**Architecture:** This is AfroEval's first run-level (not per-item) evaluator. Task 1 builds the real evaluator class — `CohortDisparityEvaluator.compute_run_disparity(cohorts, outcomes)` — as a standalone, fully unit-testable function with zero dispatcher dependency. Task 2 wires it into `orchestration/dispatcher.py`: removes the class from the per-item evaluation loop, adds a post-loop step that derives each item's pass/fail outcome from the *other* evaluators that already scored it, calls `compute_run_disparity` once for the whole run, and writes that single real score into every item's `MetricResult` row — exactly the shape `scoring/engine.py::compute_composite_score` already expects, so no scoring-engine changes are needed.

**Tech Stack:** Python, pytest, `fairlearn.metrics.MetricFrame` / `selection_rate` (already a `pyproject.toml` dependency, version 0.14.0 installed in `.venv`; not yet in `requirements.txt` — Task 2 adds it there).

## Global Constraints

- Cohort grouping is **data-driven** — group by whatever cohort values actually appear in the run's items, no hardcoded list. Tolerates unexpected values (e.g. the real data's stray `"agent"` label) as just another small group.
- Disparate impact ratio = `min(per-cohort selection rate) / max(per-cohort selection rate)`, where "selection rate" = fraction of that cohort's items with a passing outcome.
- Scoring formula (the evaluator's own `MetricOutput.score`, on the 0.0-1.0 scale — `scoring/engine.py` is what multiplies by 100 for the dimension-level score):
  ```
  score = 0.0 if disparate_impact_ratio < 0.50
  score = min(disparate_impact_ratio / 0.80, 1.0) otherwise
  ```
- `passed = disparate_impact_ratio >= 0.80` — checked directly against the ratio, independent of the derived score.
- Fewer than 2 distinct (non-blank) cohort values present → neutral fallback: `score=1.0`, `passed=True`, reason explains insufficient cohort diversity. Same fallback applies if `fairlearn` fails to import.
- Per-item outcome signal (used as Fairlearn's `y_pred`/`y_true`): average the `passed` flags from every evaluator that scored that item, threshold at ≥50% → boolean.
- `fairlearn` import must be guarded with `try/except ImportError` (same pattern as `deepeval` in `evaluators/hallucination.py`), and `fairlearn>=0.10.0` must be added to `requirements.txt` — without both, the deployed Streamlit Cloud console's "Run Evaluation" feature would crash on import, since `fairlearn` is currently only in `pyproject.toml`, not `requirements.txt`.
- `ail/informal_economy.py` must be **renamed** to `ail/informal_economy.archive.py`, never deleted (project rule) — its `INFORMAL_COHORTS`/`FORMAL_COHORTS` sets get copied (not moved) into `evaluators/bias_fairness.py` as human-readable labeling constants, not used for grouping logic (which is data-driven).
- No `scoring/engine.py` changes — `compute_composite_score` keeps the same `dimension_raw_scores: dict[str, list[float]]` signature.

---

### Task 1: Real `CohortDisparityEvaluator` + `compute_run_disparity` + unit tests

**Files:**
- Modify: `evaluators/bias_fairness.py` (entire file rewritten)
- Modify: `ail/informal_economy.py` → renamed `ail/informal_economy.archive.py`
- Test: `tests/test_bias_fairness.py` (new)

**Interfaces:**
- Produces: `evaluators.bias_fairness.CohortDisparityEvaluator` (existing class, `dimension == "bias_fairness"`, `metric_name == "cohort_disparity"` — both unchanged) with a new method `compute_run_disparity(self, cohorts: list[str], outcomes: list[bool]) -> MetricOutput`. Task 2 calls this method directly; it does not change in Task 2.

- [ ] **Step 1: Archive the dead stub**

```bash
git mv ail/informal_economy.py ail/informal_economy.archive.py
```

Add this note as the new first line of `ail/informal_economy.archive.py` (above the existing module docstring):

```python
# ARCHIVED 2026-06-29: never wired into orchestration/dispatcher.py. Its real
# logic (Fairlearn cohort comparison) was rebuilt into
# evaluators/bias_fairness.py::CohortDisparityEvaluator instead of being
# activated here, to avoid two competing implementations of the same
# dimension. See docs/superpowers/specs/2026-06-29-bias-fairness-evaluator-design.md.
```

The rest of the file's content is unchanged.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_bias_fairness.py`:

```python
"""
Tests for CohortDisparityEvaluator's real Fairlearn-backed disparate-impact
computation.

These exercise compute_run_disparity() directly (the run-level method) since
that's where the real logic lives. evaluate() (the per-item BaseEvaluator
method) is a degenerate pass-through tested separately at the bottom.
"""

from evaluators.bias_fairness import CohortDisparityEvaluator


def test_clean_parity_scores_near_one():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 9 + [False] + [True] * 9 + [False]  # 90% pass rate, both cohorts
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension == "bias_fairness"
    assert result.metric_name == "cohort_disparity"


def test_disparity_at_threshold_clamps_to_full_score():
    evaluator = CohortDisparityEvaluator()
    # formal: 10/10 pass (rate=1.0). informal_economy: 8.5/10 -> use 17/20 for exactness.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 17 + [False] * 3  # formal=1.0, informal=0.85 -> ratio=0.85
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 1.0  # min(0.85/0.80, 1.0) clamps to 1.0
    assert result.passed is True  # 0.85 >= 0.80


def test_disparity_between_floor_and_threshold_is_partial_score():
    evaluator = CohortDisparityEvaluator()
    # formal: 20/20 pass (rate=1.0). informal_economy: 13/20 pass (rate=0.65) -> ratio=0.65
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 13 + [False] * 7
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.8125) < 0.001  # 0.65 / 0.80
    assert result.passed is False


def test_disparity_below_floor_scores_zero():
    evaluator = CohortDisparityEvaluator()
    # formal: 20/20 pass (rate=1.0). informal_economy: 6/20 pass (rate=0.30) -> ratio=0.30
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 6 + [False] * 14
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 0.0
    assert result.passed is False


def test_fewer_than_two_cohorts_falls_back_to_neutral():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10
    outcomes = [True, False] * 5
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 1.0
    assert result.passed is True
    assert "insufficient" in result.reason.lower()


def test_blank_cohorts_are_dropped_before_grouping():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + [""] * 10  # blank labels don't form a real group
    outcomes = [True] * 10 + [False] * 10
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    # after dropping blanks, only "formal" remains -> insufficient diversity
    assert result.score == 1.0
    assert result.passed is True
    assert "insufficient" in result.reason.lower()


def test_unexpected_cohort_label_is_grouped_like_any_other():
    evaluator = CohortDisparityEvaluator()
    # "agent" isn't a documented cohort, but the grouping is data-driven.
    cohorts = ["formal"] * 10 + ["agent"] * 10
    outcomes = [True] * 10 + [False] * 10  # formal=1.0, agent=0.0 -> ratio=0.0
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert result.score == 0.0
    assert result.passed is False
    assert "agent" in result.reason


def test_evaluate_single_item_falls_through_to_neutral_fallback():
    evaluator = CohortDisparityEvaluator()
    result = evaluator.evaluate(
        prompt="p",
        model_response="r",
        expected_behavior="e",
        context={"cohort": "formal"},
    )
    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension == "bias_fairness"
    assert result.metric_name == "cohort_disparity"
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py -v
```

Expected: all 8 tests FAIL — `compute_run_disparity` doesn't exist yet (the current `CohortDisparityEvaluator.evaluate()` always returns `score=0.75`, so even `test_evaluate_single_item_falls_through_to_neutral_fallback` fails too, since it expects `1.0` not `0.75`).

- [ ] **Step 4: Write the full implementation**

Replace the entire contents of `evaluators/bias_fairness.py`:

```python
"""
Bias & Fairness evaluator — Dimension weight: 15%.

Uses Fairlearn to measure performance disparities across user cohorts
(formal/informal economy, rural/urban, language proficiency levels). This is
AfroEval's first run-level (not per-item) evaluator: a single item has no
cohort to compare against, so the real computation happens once per run in
compute_run_disparity(), called by orchestration/dispatcher.py after every
item has been scored by every other evaluator. See
docs/superpowers/specs/2026-06-29-bias-fairness-evaluator-design.md for why
this dimension works differently from every other AfroEval evaluator.

Labeling constants below are folded in from the now-archived
ail/informal_economy.archive.py — used for human-readable reason text only;
cohort grouping itself is data-driven (whatever values appear in a run),
not restricted to these sets.
"""

from evaluators.base import BaseEvaluator, MetricOutput

try:
    from fairlearn.metrics import MetricFrame, selection_rate
    _FAIRLEARN_AVAILABLE = True
except ImportError:
    _FAIRLEARN_AVAILABLE = False

INFORMAL_COHORTS = {"informal_economy", "rural", "low_literacy", "feature_phone_user"}
FORMAL_COHORTS = {"formal_economy", "urban", "high_literacy", "smartphone_user"}

DISPARITY_PASS_THRESHOLD = 0.80
DISPARITY_FLOOR = 0.50


class CohortDisparityEvaluator(BaseEvaluator):
    """
    Measures whether model performance differs significantly across cohorts.

    evaluate() (the per-item BaseEvaluator method) is a degenerate
    pass-through — a single item has no sibling to compare against, so it
    always falls through to the same "insufficient cohort diversity" neutral
    fallback that compute_run_disparity() uses for any run with fewer than 2
    distinct cohorts. The real computation is compute_run_disparity(),
    called once per run.
    """

    @property
    def dimension(self) -> str:
        return "bias_fairness"

    @property
    def metric_name(self) -> str:
        return "cohort_disparity"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        cohort = (context or {}).get("cohort", "")
        # outcome is never inspected: a single cohort is always < 2 distinct
        # cohorts, so this always lands on the neutral fallback below.
        return self.compute_run_disparity(cohorts=[cohort], outcomes=[True])

    def compute_run_disparity(self, cohorts: list[str], outcomes: list[bool]) -> MetricOutput:
        """
        Disparate impact ratio = min(per-cohort selection rate) / max(per-cohort
        selection rate), grouped by whatever cohort values are present in
        `cohorts` (blank values dropped first). Falls back to a neutral
        score=1.0/passed=True if fewer than 2 distinct cohorts remain after
        dropping blanks, or if fairlearn is unavailable.
        """
        if not _FAIRLEARN_AVAILABLE:
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=1.0,
                passed=True,
                reason="fairlearn unavailable in this environment; neutral pass-through score.",
            )

        paired = [(c, o) for c, o in zip(cohorts, outcomes) if c]
        distinct_cohorts = {c for c, _ in paired}

        if len(distinct_cohorts) < 2:
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=1.0,
                passed=True,
                reason=(
                    f"Insufficient cohort diversity in this run to compute a disparity "
                    f"comparison (found: {sorted(distinct_cohorts) or 'none'}). Neutral "
                    "pass-through score."
                ),
            )

        cohort_labels = [c for c, _ in paired]
        outcome_values = [o for _, o in paired]

        # selection_rate(y_true, y_pred) only consumes y_pred (mean of positive
        # predictions); passing outcome_values for both is correct here since
        # AfroEval items have no separate ground-truth correctness label.
        mf = MetricFrame(
            metrics={"selection_rate": selection_rate},
            y_true=outcome_values,
            y_pred=outcome_values,
            sensitive_features=cohort_labels,
        )
        rates = mf.by_group["selection_rate"]
        worst_cohort = rates.idxmin()
        best_cohort = rates.idxmax()
        disparate_impact_ratio = rates.min() / rates.max() if rates.max() > 0 else 1.0

        if disparate_impact_ratio < DISPARITY_FLOOR:
            score = 0.0
        else:
            score = min(disparate_impact_ratio / DISPARITY_PASS_THRESHOLD, 1.0)

        passed = disparate_impact_ratio >= DISPARITY_PASS_THRESHOLD

        rates_dict = rates.to_dict()
        reason = (
            f"Disparate impact ratio: {disparate_impact_ratio:.3f} "
            f"(threshold ≥{DISPARITY_PASS_THRESHOLD}). "
            f"Per-cohort selection rates: {rates_dict}. "
            f"Worst-performing cohort: '{worst_cohort}' ({rates[worst_cohort]:.3f}), "
            f"best: '{best_cohort}' ({rates[best_cohort]:.3f})."
        )

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=passed,
            reason=reason,
            extra={
                "per_cohort_selection_rate": rates_dict,
                "disparate_impact_ratio": disparate_impact_ratio,
            },
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 6: Run the full test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all tests pass (153 prior + 8 new = 161; if the exact count differs, read any failure before assuming it's wrong). `ail/informal_economy.archive.py` is not imported anywhere, so renaming it should not break any existing test — confirm no test file imports `ail.informal_economy` before assuming this is safe (a `grep -rl "ail.informal_economy" tests/` returning nothing confirms it).

- [ ] **Step 7: Stage and stop for review**

```powershell
git add evaluators/bias_fairness.py tests/test_bias_fairness.py
git add ail/informal_economy.archive.py
git rm ail/informal_economy.py
git status
```

(`git mv` in Step 1 should already stage both sides of the rename as one operation — `git status` should show `renamed: ail/informal_economy.py -> ail/informal_economy.archive.py`, not a separate add/delete. If it shows as a plain delete + untracked add instead, run the explicit `git add`/`git rm` pair above to get the same end state.)

Do not commit — show Dan the staged diff and wait for explicit approval before any commit.

---

### Task 2: Wire into dispatcher, fix deployment risk, unstub, fix doc

**Files:**
- Modify: `orchestration/dispatcher.py:241-326` (remove from per-item loop, add run-level post-step)
- Modify: `requirements.txt`
- Modify: `scripts/hitl_export_tasks.py:31-33` (`_STUB_METRIC_NAMES`)
- Modify: `docs/METHODOLOGY_V1.md:155-156` (scoring formula)

**Interfaces:**
- Consumes: `evaluators.bias_fairness.CohortDisparityEvaluator().compute_run_disparity(cohorts: list[str], outcomes: list[bool]) -> MetricOutput` (from Task 1, unchanged).

- [ ] **Step 1: Add fairlearn to requirements.txt**

In `requirements.txt`, add this line (anywhere in the file — order doesn't matter, but appending at the end keeps the diff minimal):

```
fairlearn>=0.10.0
```

- [ ] **Step 2: Remove CohortDisparityEvaluator from the per-item evaluator loop**

In `orchestration/dispatcher.py`, find this line inside the `evaluators = [...]` list (currently around line 249):

```python
                evaluators = [
                    SemanticSimilarityEvaluator(model=deepeval_model),
                    AnswerCompletenessEvaluator(model=deepeval_model),
                    FluencyEvaluator(judge=judge),
                    ChrFEvaluator(),
                    MultilingualSimilarityEvaluator(),
                    FaithfulnessEvaluator(model=deepeval_model),
                    AfricanHallucinationProbeEvaluator(),
                    CohortDisparityEvaluator(),
                    SafetyEvaluator(),
                    CulturalAppropriatenessEvaluator(judge=judge),
                    RegisterMatchEvaluator(judge=judge),
                    SwitchNaturalnessEvaluator(judge=judge),
                    LanguagePreservationEvaluator(judge=judge),
                ]
```

Replace with (only the `CohortDisparityEvaluator(),` line removed — the import at the top of the function stays, since Task 2's new code below still uses the class):

```python
                evaluators = [
                    SemanticSimilarityEvaluator(model=deepeval_model),
                    AnswerCompletenessEvaluator(model=deepeval_model),
                    FluencyEvaluator(judge=judge),
                    ChrFEvaluator(),
                    MultilingualSimilarityEvaluator(),
                    FaithfulnessEvaluator(model=deepeval_model),
                    AfricanHallucinationProbeEvaluator(),
                    SafetyEvaluator(),
                    CulturalAppropriatenessEvaluator(judge=judge),
                    RegisterMatchEvaluator(judge=judge),
                    SwitchNaturalnessEvaluator(judge=judge),
                    LanguagePreservationEvaluator(judge=judge),
                ]
```

- [ ] **Step 3: Accumulate per-item passed flags while bucketing the other evaluators' outputs**

Find this block (currently around lines 257-261, right after the `evaluators = [...]` list):

```python
                dimension_scores: dict[str, list[float]] = {dim: [] for dim in DEFAULT_WEIGHTS}
                dimension_metric_scores: dict[str, dict[str, list[float]]] = {
                    dim: {name: [] for name in metrics} for dim, metrics in DEFAULT_METRIC_WEIGHTS.items()
                }
                item_counts: dict[str, int] = {dim: 0 for dim in DEFAULT_WEIGHTS}
```

Replace with (adds one new dict, `item_passed_flags`):

```python
                dimension_scores: dict[str, list[float]] = {dim: [] for dim in DEFAULT_WEIGHTS}
                dimension_metric_scores: dict[str, dict[str, list[float]]] = {
                    dim: {name: [] for name in metrics} for dim, metrics in DEFAULT_METRIC_WEIGHTS.items()
                }
                item_counts: dict[str, int] = {dim: 0 for dim in DEFAULT_WEIGHTS}
                item_passed_flags: dict[int, list[bool]] = {idx: [] for idx in range(len(all_items))}
```

Now find the output-bucketing loop (currently around lines 288-310):

```python
                n_evaluators = len(evaluators)
                for i, output in enumerate(all_outputs):
                    if output.dimension in dimension_scores:
                        dimension_scores[output.dimension].append(output.score)
                        item_counts[output.dimension] += 1

                    dim_metrics = dimension_metric_scores.get(output.dimension)
                    if dim_metrics is not None and output.metric_name in dim_metrics:
                        dim_metrics[output.metric_name].append(output.score)

                    # ── Step 4b: Persist MetricResult rows ────────────────────
                    item_idx = i // n_evaluators
                    if item_idx in response_id_by_idx:
                        session.add(MetricResult(
                            id=uuid.uuid4(),
                            response_id=response_id_by_idx[item_idx],
                            dimension=output.dimension,
                            metric_name=output.metric_name,
                            score=output.score,
                            passed=output.passed,
                            reason=output.reason,
                            extra=output.extra,
                        ))
```

Replace with (adds one line, `item_passed_flags[item_idx].append(output.passed)`, inside the existing loop — everything else in this loop is unchanged):

```python
                n_evaluators = len(evaluators)
                for i, output in enumerate(all_outputs):
                    if output.dimension in dimension_scores:
                        dimension_scores[output.dimension].append(output.score)
                        item_counts[output.dimension] += 1

                    dim_metrics = dimension_metric_scores.get(output.dimension)
                    if dim_metrics is not None and output.metric_name in dim_metrics:
                        dim_metrics[output.metric_name].append(output.score)

                    # ── Step 4b: Persist MetricResult rows ────────────────────
                    item_idx = i // n_evaluators
                    item_passed_flags[item_idx].append(output.passed)
                    if item_idx in response_id_by_idx:
                        session.add(MetricResult(
                            id=uuid.uuid4(),
                            response_id=response_id_by_idx[item_idx],
                            dimension=output.dimension,
                            metric_name=output.metric_name,
                            score=output.score,
                            passed=output.passed,
                            reason=output.reason,
                            extra=output.extra,
                        ))
```

- [ ] **Step 4: Add the run-level bias_fairness post-step**

Immediately after that loop, and before the `# ── Step 5: Compute composite score ───` comment (currently around line 312), insert this new block:

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

- [ ] **Step 5: Remove the now-resolved stub entry from the export script**

In `scripts/hitl_export_tasks.py`, find the `_STUB_METRIC_NAMES` set (currently lines 31-33):

```python
_STUB_METRIC_NAMES = {
    "cohort_disparity",             # CohortDisparityEvaluator — always 0.75
}
```

Replace with (this is now the last remaining stub-evaluator metric, so the set becomes empty — keep the explanatory comment so a future reader understands why an empty set still exists here, rather than deleting the constant entirely):

```python
_STUB_METRIC_NAMES: set[str] = set()
```

- [ ] **Step 6: Fix the self-contradictory scoring formula in the methodology doc**

In `docs/METHODOLOGY_V1.md`, find this text (currently lines 155-156):

```
**Scoring:** `min(disparate_impact_ratio / 0.80, 1.0) × 100`.  
A ratio of 1.0 (perfect parity) scores 100. A ratio below 0.50 scores 0.
```

Replace with:

```
**Scoring:**
```
score = 0 if disparate_impact_ratio < 0.50
score = min(disparate_impact_ratio / 0.80, 1.0) × 100 otherwise
```
A ratio of 1.0 (perfect parity) scores 100. A ratio below 0.50 scores 0.
```

- [ ] **Step 7: Run the full test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all 161 tests pass (no test directly exercises `dispatch_run()`'s internals today — confirmed via `grep -rl "dispatch_run\|CohortDisparityEvaluator" tests/` returning nothing before this plan was written — so this step's job is confirming the refactor didn't break anything elsewhere, not exercising new dispatcher-specific assertions).

- [ ] **Step 8: Stage and stop for review**

```powershell
git add orchestration/dispatcher.py requirements.txt scripts/hitl_export_tasks.py docs/METHODOLOGY_V1.md
git status
```

Do not commit — show Dan the staged diff and wait for explicit approval before any commit.

---

## Self-Review Notes

- **Spec coverage:** outcome-signal derivation (Task 2 Step 3), run-level Fairlearn computation with data-driven grouping and both fallback paths (Task 1 Step 4), the piecewise scoring formula and `passed` threshold (Task 1 Step 4, Global Constraints), the dispatcher integration removing the per-item call and adding the post-step (Task 2 Steps 2-4), the archive of `ail/informal_economy.py` (Task 1 Step 1), the `requirements.txt`/guarded-import deployment fix (Task 1 Step 4's `try/except`, Task 2 Step 1), the unstub (Task 2 Step 5), and the methodology doc fix (Task 2 Step 6) — every section of the spec has a corresponding step. The spec's explicitly-out-of-scope items (per-cohort minimum-items confidence flag, the `METHODOLOGY_V1.md`/`BENCHMARK_ITEM_SCHEMA.md` cohort-naming mismatch, correcting the `"agent"` mislabeling in benchmark packs) have no task here, matching the spec.
- **Type consistency:** `compute_run_disparity(self, cohorts: list[str], outcomes: list[bool]) -> MetricOutput` is defined once in Task 1 Step 4 and consumed with that exact signature in Task 2 Step 4 — no drift. `dimension`/`metric_name` (`"bias_fairness"`/`"cohort_disparity"`) are unchanged from the existing stub, so no downstream rename is needed anywhere (scoring engine, `MetricResult` rows, Label Studio export already key on these exact strings).
- **No placeholders:** every step has complete, literal code and exact commands. The one edge case not explicitly covered by a test — all-cohorts-zero selection rate (`rates.max() == 0`) — is handled by treating it as `disparate_impact_ratio = 1.0` (no disparity signal when everyone fails equally; the model's poor absolute quality is already visible via every other dimension, so this dimension doesn't also zero out for an unrelated reason) rather than crashing on a division by zero; this is a defensive fallback for a case the real benchmark data is very unlikely to hit (it would mean a model failing literally every single item across every cohort), not a documented spec requirement, so it isn't given its own test, but the implementation comment at that line makes the choice visible to a future reader.
