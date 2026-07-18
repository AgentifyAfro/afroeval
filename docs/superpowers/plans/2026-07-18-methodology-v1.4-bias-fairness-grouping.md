# Methodology v1.4 — Bias & Fairness Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `bias_fairness` measure cross-language disparity as well as cohort disparity, and score it continuously, so the dimension stops reporting 100.0 on a real 10% language gap.

**Architecture:** `CohortDisparityEvaluator.compute_run_disparity()` gains a second optional grouping axis (`languages`). Each axis with ≥2 distinct non-blank groups yields a disparate impact ratio; the **worst** ratio drives a **continuous** score. Both ratios are reported in the `reason`. The dispatcher passes the language labels it already has.

**Tech Stack:** Python 3.12, Fairlearn `MetricFrame`/`selection_rate`, SQLModel, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-methodology-v1.4-bias-fairness-grouping-design.md`

## Global Constraints

- Formula, verbatim from the spec:
  `governing_ratio = min(r for r in (language_ratio, cohort_ratio) if r is not None)`;
  `score = governing_ratio`; `passed = governing_ratio >= 0.80`;
  `applicable = at least one axis has >= 2 distinct non-blank groups`.
- `DISPARITY_PASS_THRESHOLD = 0.80` is retained but sets `passed` ONLY — it must not scale the score.
- `DISPARITY_FLOOR` is removed entirely. No hard-zero cliff.
- Selection rates stay **binarized** (pass/fail booleans). Do not switch to continuous per-item scores.
- The `reason` string must name BOTH axes, their ratios, their worst/best groups, and which axis governed.
- `reason` must remain ASCII-only (no `≥`, no smart quotes) — enforced by an existing test.
- `benchmarks/packs/*.jsonl` are SME-validated and **read-only**. No task edits them.
- Historical scorecards are frozen: no re-scoring, no back-fill, no migration.
- `METHODOLOGY_VERSION` → `"v1.4"`.
- Blank/empty group labels are dropped before grouping, on both axes.
- Backwards compatibility: `compute_run_disparity(cohorts, outcomes)` must still work with the `languages` argument omitted.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `evaluators/bias_fairness.py` | disparity computation, both axes, scoring, reason text | Modify |
| `orchestration/dispatcher.py` | pass language labels into the evaluator | Modify |
| `scoring/engine.py` | `METHODOLOGY_VERSION` | Modify |
| `tests/test_bias_fairness.py` | evaluator behaviour incl. 3 rewritten tests | Modify |
| `tests/test_methodology.py` | version assertion | Modify |
| `tests/test_scoring.py` | version assertion | Modify |
| `docs/METHODOLOGY_V1.md` | §2.4 bias dimension description | Modify |
| `docs/ENGINEERING_BIBLE_V1.html` | §04 table, §05.4 mechanism, Rev strings | Modify |

---

### Task 1: Two-axis disparity with continuous scoring

**Files:**
- Modify: `evaluators/bias_fairness.py`
- Test: `tests/test_bias_fairness.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `compute_run_disparity(cohorts: list[str], outcomes: list[bool], languages: list[str] | None = None) -> MetricOutput`. Task 2 calls this with `languages=`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bias_fairness.py`:

```python
def test_language_axis_governs_when_worse_than_cohort():
    evaluator = CohortDisparityEvaluator()
    # cohort axis: formal 1.0, informal 1.0 -> ratio 1.0 (parity)
    # language axis: sw 1.0, am 0.5        -> ratio 0.5 (the real gap)
    cohorts = ["formal"] * 2 + ["informal_economy"] * 2
    languages = ["sw", "am", "sw", "am"]
    outcomes = [True, True, True, False]
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert abs(result.score - 0.5) < 1e-9
    assert result.passed is False
    assert "0.500" in result.reason and "1.000" in result.reason


def test_cohort_axis_governs_when_worse_than_language():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal", "formal", "informal_economy", "informal_economy"]
    languages = ["sw", "am", "sw", "am"]
    outcomes = [True, True, False, False]  # cohort ratio 0.0, language ratio 1.0
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert result.score == 0.0
    assert result.passed is False


def test_score_is_continuous_above_threshold():
    evaluator = CohortDisparityEvaluator()
    # formal 1.0, informal 0.9 -> ratio 0.90. Old code clamped this to 1.0.
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 10 + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.90) < 1e-9
    assert result.passed is True  # 0.90 >= 0.80


def test_single_language_axis_is_ignored_not_fatal():
    evaluator = CohortDisparityEvaluator()
    # only one language -> that axis does not qualify; cohort axis still scores.
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    languages = ["sw"] * 20
    outcomes = [True] * 10 + [True] * 9 + [False]
    result = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages)
    assert abs(result.score - 0.90) < 1e-9
    assert result.applicable is True


def test_neither_axis_qualifies_is_not_applicable():
    evaluator = CohortDisparityEvaluator()
    result = evaluator.compute_run_disparity(["formal"] * 4, [True] * 4, languages=["sw"] * 4)
    assert result.applicable is False
    assert "insufficient" in result.reason.lower()


def test_languages_argument_is_optional():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 10 + ["informal_economy"] * 10
    outcomes = [True] * 10 + [True] * 9 + [False]
    assert evaluator.compute_run_disparity(cohorts, outcomes).score == \
        evaluator.compute_run_disparity(cohorts, outcomes, languages=None).score


def test_reason_names_both_axes_and_the_governing_one():
    evaluator = CohortDisparityEvaluator()
    cohorts = ["formal"] * 2 + ["informal_economy"] * 2
    languages = ["sw", "am", "sw", "am"]
    outcomes = [True, True, True, False]
    reason = evaluator.compute_run_disparity(cohorts, outcomes, languages=languages).reason
    assert "language" in reason.lower()
    assert "cohort" in reason.lower()
    assert "governing" in reason.lower()
```

Rewrite these three existing tests — they assert the removed clamp and floor. Replace the
old bodies entirely:

```python
def test_disparity_at_threshold_is_scored_continuously():
    evaluator = CohortDisparityEvaluator()
    # formal=1.0, informal=0.85 -> ratio 0.85. v1.2 clamped this to 1.0.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 17 + [False] * 3
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.85) < 1e-9
    assert result.passed is True  # 0.85 >= 0.80


def test_disparity_below_threshold_is_scored_continuously():
    evaluator = CohortDisparityEvaluator()
    # formal=1.0, informal=0.65 -> ratio 0.65. v1.2 scored 0.65/0.80 = 0.8125.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 13 + [False] * 7
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.65) < 1e-9
    assert result.passed is False


def test_severe_disparity_scores_low_without_a_floor_cliff():
    evaluator = CohortDisparityEvaluator()
    # formal=1.0, informal=0.30 -> ratio 0.30. v1.2 hard-zeroed anything below 0.50.
    cohorts = ["formal"] * 20 + ["informal_economy"] * 20
    outcomes = [True] * 20 + [True] * 6 + [False] * 14
    result = evaluator.compute_run_disparity(cohorts, outcomes)
    assert abs(result.score - 0.30) < 1e-9
    assert result.passed is False
```

`test_clean_parity_scores_near_one` and `test_unexpected_cohort_label_is_grouped_like_any_other`
still pass unchanged (ratios 1.0 and 0.0 map to themselves) — do not modify them.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py -v`
Expected: the new tests FAIL with `TypeError: compute_run_disparity() got an unexpected keyword argument 'languages'`; the three rewritten tests FAIL on the score assertion.

- [ ] **Step 3: Replace the constants**

In `evaluators/bias_fairness.py`, delete the `DISPARITY_FLOOR` line and leave:

```python
DISPARITY_PASS_THRESHOLD = 0.80   # sets `passed` only; does NOT scale the score (v1.4)
```

- [ ] **Step 4: Add the per-axis ratio helper**

Add above the class:

```python
def _axis_ratio(labels: list[str], outcomes: list[bool]) -> tuple[float, dict, str, str] | None:
    """Disparate impact ratio for one grouping axis.

    Returns (ratio, per_group_rates, worst_group, best_group), or None when the
    axis has fewer than 2 distinct non-blank groups and therefore cannot support
    a comparison.
    """
    paired = [(lbl, out) for lbl, out in zip(labels, outcomes) if lbl]
    if len({lbl for lbl, _ in paired}) < 2:
        return None

    group_labels = [lbl for lbl, _ in paired]
    outcome_values = [out for _, out in paired]

    # selection_rate(y_true, y_pred) only consumes y_pred (mean of positive
    # predictions); passing outcome_values for both is correct here since
    # AfroEval items have no separate ground-truth correctness label.
    mf = MetricFrame(
        metrics={"selection_rate": selection_rate},
        y_true=outcome_values,
        y_pred=outcome_values,
        sensitive_features=group_labels,
    )
    rates = mf.by_group["selection_rate"]
    ratio = float(rates.min() / rates.max()) if rates.max() > 0 else 1.0
    return ratio, rates.to_dict(), str(rates.idxmin()), str(rates.idxmax())
```

- [ ] **Step 5: Rewrite `compute_run_disparity`**

Replace the whole method body below the fairlearn-unavailable guard:

```python
    def compute_run_disparity(
        self,
        cohorts: list[str],
        outcomes: list[bool],
        languages: list[str] | None = None,
    ) -> MetricOutput:
        """
        Disparate impact ratio = min(selection rate) / max(selection rate), computed
        independently over two axes: user cohort and item language. The WORSE of the
        two governs the score (v1.4) — parity on one axis must not mask a gap on the
        other. Score is the governing ratio itself: continuous, no clamp, no floor.
        An axis with fewer than 2 distinct non-blank groups is skipped; if neither
        axis qualifies the dimension is not applicable and is excluded from the
        composite.
        """
        if not _FAIRLEARN_AVAILABLE:
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=1.0,
                passed=True,
                reason="fairlearn unavailable in this environment; neutral pass-through score.",
            )

        axes = {
            "cohort": _axis_ratio(cohorts, outcomes),
            "language": _axis_ratio(list(languages or []), outcomes),
        }
        qualified = {name: res for name, res in axes.items() if res is not None}

        if not qualified:
            found = sorted({c for c in cohorts if c})
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=0.0,
                passed=False,
                reason=(
                    f"Insufficient group diversity on both axes to measure disparity "
                    f"(cohorts found: {found or 'none'}). "
                    "Dimension not applicable - excluded from composite score."
                ),
                applicable=False,
            )

        governing_axis = min(qualified, key=lambda name: qualified[name][0])
        governing_ratio = qualified[governing_axis][0]

        score = governing_ratio
        passed = bool(governing_ratio >= DISPARITY_PASS_THRESHOLD)

        parts = []
        for name in ("language", "cohort"):
            res = qualified.get(name)
            if res is None:
                parts.append(f"{name} axis: not measured (fewer than 2 groups).")
                continue
            ratio, rates, worst, best = res
            parts.append(
                f"{name} disparity ratio: {ratio:.3f} "
                f"(per-group selection rates: {rates}; "
                f"worst: '{worst}', best: '{best}')."
            )
        reason = (
            " ".join(parts)
            + f" Governing axis: {governing_axis} at {governing_ratio:.3f} "
            f"(threshold >={DISPARITY_PASS_THRESHOLD}; score is the ratio itself)."
        )

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=passed,
            reason=reason,
        )
```

Note the ASCII `>=` and `-` in the strings — an existing test asserts the reason encodes as ASCII.

- [ ] **Step 6: Update the module docstring**

In `evaluators/bias_fairness.py`, replace the first paragraph:

```
Uses Fairlearn to measure performance disparities across two axes: user cohort
(formal/informal economy, rural/urban) and item language. The worse of the two
ratios governs the score (v1.4); both are reported. This is AfroEval's first
run-level (not per-item) evaluator: a single item has no group to compare
against, so the real computation happens once per run in compute_run_disparity(),
called by orchestration/dispatcher.py after every item has been scored by every
other evaluator. See
docs/superpowers/specs/2026-07-18-methodology-v1.4-bias-fairness-grouping-design.md
for why the language axis was added.
```

- [ ] **Step 7: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bias_fairness.py -v`
Expected: all PASS, including the unmodified `test_cohort_disparity_reason_is_ascii_safe`.

- [ ] **Step 8: Commit**

```bash
git add evaluators/bias_fairness.py tests/test_bias_fairness.py
git commit -m "feat(bias): v1.4 - language axis + continuous disparity scoring

bias_fairness reported exactly 100.0 on 8 of 9 scorecards because
min(ratio/0.80, 1.0) clamped every ratio at or above 0.80 to a full score, and
because disparity was measured only over cohort, where formal and informal
perform near-identically (0.8251 vs 0.8222 on run 64e9519b). Grouping the same
run by language exposes a 0.900 ratio - Amharic vs Swahili - that the old
formula reported as perfect parity.

Both axes are now computed and reported; the worse governs. Score is the
governing ratio itself, so 0.86 and 1.00 no longer read alike. The 0.80
threshold now sets passed only, and the DISPARITY_FLOOR hard-zero cliff is
removed as a second arbitrary discontinuity."
```

---

### Task 2: Wire the language axis through the dispatcher

**Files:**
- Modify: `orchestration/dispatcher.py` (the `Step 4c` bias block, ~line 509)
- Test: `tests/test_sprint1.py`

**Interfaces:**
- Consumes: `compute_run_disparity(cohorts, outcomes, languages=...)` from Task 1.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sprint1.py`:

```python
class TestBiasLanguageAxis:
    def test_dispatcher_passes_language_labels(self):
        """The language axis is useless if the dispatcher never supplies it."""
        import inspect
        from orchestration import dispatcher
        src = inspect.getsource(dispatcher.dispatch_run)
        assert "bias_languages" in src
        assert "languages=bias_languages" in src
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_sprint1.py::TestBiasLanguageAxis -v`
Expected: FAIL on the first assertion.

- [ ] **Step 3: Pass the language labels**

In `orchestration/dispatcher.py`, in the `Step 4c` block, add `bias_languages` beside the
existing `bias_cohorts` line and pass it through. `all_items` already carries `language`
(it is read at ~line 371):

```python
                bias_cohorts = [item.get("cohort", "") for item in all_items]
                bias_languages = [item.get("language", "") for item in all_items]
                bias_outcomes = [
                    (sum(item_passed_flags[idx]) / len(item_passed_flags[idx]) >= 0.5)
                    if item_passed_flags[idx] else False
                    for idx in range(len(all_items))
                ]
                bias_result = CohortDisparityEvaluator().compute_run_disparity(
                    bias_cohorts, bias_outcomes, languages=bias_languages
                )
```

- [ ] **Step 4: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_sprint1.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestration/dispatcher.py tests/test_sprint1.py
git commit -m "feat(bias): supply per-item language labels to the disparity evaluator

all_items already carries language; the bias block simply never read it, which
is why the language axis could not be measured."
```

---

### Task 3: Version bump, docs, and Engineering Bible

**Files:**
- Modify: `scoring/engine.py:38`
- Modify: `tests/test_methodology.py:28`, `tests/test_scoring.py:372`
- Modify: `docs/METHODOLOGY_V1.md` (bias & fairness section)
- Modify: `docs/ENGINEERING_BIBLE_V1.html` (§04 aggregation table, §05.4, Rev strings)

**Interfaces:**
- Consumes: the final formula from Task 1.
- Produces: nothing.

- [ ] **Step 1: Bump the version**

`scoring/engine.py:38`: `METHODOLOGY_VERSION = "v1.4"`

- [ ] **Step 2: Update the two version assertions**

`tests/test_methodology.py:28` and `tests/test_scoring.py:372`: `assert METHODOLOGY_VERSION == "v1.4"`

- [ ] **Step 3: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all PASS. If any other test asserts `"v1.2"`, update it the same way — do not weaken an assertion to make it pass.

- [ ] **Step 4: Update METHODOLOGY_V1.md**

In the Bias & Fairness section, replace the disparity description with:

```
Disparate impact ratio is computed independently over two axes:

| axis | grouping | source |
|---|---|---|
| language | item language (am, sw, yo, zu, ha, so, om, en, sheng) | `BenchmarkItem.language` |
| cohort | user cohort (formal, informal_economy) | `BenchmarkItem.cohort` |

**Score:** the worse of the two ratios, mapped continuously to 0-100. An axis with
fewer than 2 distinct groups is skipped; if neither qualifies the dimension is not
applicable and is renormalised out of the composite.

**Pass threshold:** ratio >= 0.80 (sets the pass flag; it does not scale the score).
```

Add below it:

> **v1.4 change.** Disparity was previously measured over `cohort` alone and scored with
> `min(ratio / 0.80, 1.0)`. That clamp mapped every ratio at or above 0.80 to a full 100,
> so observed ratios of 0.857, 0.905, 0.971 and 1.000 all scored identically — and the two
> cohorts perform near-identically anyway (0.8251 vs 0.8222 on run `64e9519b`), while the
> same run has a 0.900 language ratio between Amharic and Swahili. The dimension was blind
> to the disparity AfroEval exists to measure. Historical v1.0-v1.3 scorecards are frozen
> and are NOT re-scored; compare across versions only with `methodology_version` in hand.

- [ ] **Step 5: Update the Engineering Bible (As-Built)**

In `docs/ENGINEERING_BIBLE_V1.html`:
1. §4.2 aggregation table, Bias & Fairness row — sub-metric cell becomes
   `cohort_disparity = min(language_ratio, cohort_ratio), continuous 0-1`.
2. §5.4 Bias & Fairness — replace the single-axis mechanism description with the two-axis
   formula and the run-`64e9519b` evidence (cohort 0.971 vs language 0.900).
3. Replace `Rev 1.2 - Methodology v1.2` with `Rev 1.4 - Methodology v1.4` in the
   confidential bar, hero meta, and footer.
4. **Search the whole file for any surviving claim that bias uses a 0.80-scaled score or a
   0.50 floor, and for any "cohort" -only description of the dimension.** Both v1.2 doc
   rounds were failed by exactly this kind of stale claim surviving in prose.

- [ ] **Step 6: Verify no stale references remain**

Run: `grep -rn "DISPARITY_FLOOR\|ratio / 0.80\|0.80, 1.0" --include=*.py --include=*.md --include=*.html .`
Expected: no hits outside this plan and the spec.

- [ ] **Step 7: Commit**

```bash
git add scoring/engine.py tests/test_methodology.py tests/test_scoring.py \
        docs/METHODOLOGY_V1.md docs/ENGINEERING_BIBLE_V1.html
git commit -m "docs: methodology v1.4 - bias measured on language and cohort axes"
```

- [ ] **Step 8: Re-baseline (controller/owner, NOT the implementer)**

Billable live runs. The v1.2 baseline is run `64e9519b`. Expected from the spec's
simulation: `bias_fairness` 100.00 -> ~90.00, composite 87.92 -> ~86.42, verdict holds
Deployment-Ready. Exact values differ with fresh model output; the check is that
`bias_fairness` is no longer exactly 100.0 and that the reason string names both axes.

```bash
AFROEVAL_ENV=production .venv/Scripts/python.exe scripts/run_and_export.py \
  --assessment-name "v1.4 baseline - all packs" --skip-export
```

---

## Self-Review Notes

**Spec coverage:** two-axis computation (T1 S4-S5) · `min` over axes (T1 S5) · continuous
score, no clamp (T1 S3, S5) · floor removed (T1 S3) · threshold sets `passed` only (T1 S5) ·
binarized selection rates retained (T1 S4 — `_axis_ratio` consumes the existing boolean
`outcomes` unchanged) · both ratios in the reason (T1 S5, test in T1 S1) · ASCII reason
(T1 S5) · applicable rule (T1 S5) · backwards-compatible signature (T1 S5 default `None`,
test in T1 S1) · dispatcher wiring (T2) · version bump (T3 S1-S2) · docs (T3 S4-S5) ·
frozen history (Global Constraints — no migration task exists) · re-baseline (T3 S8).

**The three rewritten tests** are called out in the spec's Migration section and given
complete replacement bodies in T1 S1 — they assert the removed clamp and floor, so leaving
them would block the change, and deleting them would silently drop coverage.

**Type consistency:** `_axis_ratio(labels: list[str], outcomes: list[bool]) -> tuple[float, dict, str, str] | None`
is defined once (T1 S4) and called twice in T1 S5. `compute_run_disparity(..., languages: list[str] | None = None)`
is defined in T1 S5 and called with `languages=bias_languages` in T2 S3. `bias_languages: list[str]`
matches `bias_cohorts: list[str]`.

**No migration.** v1.4 adds no column — both ratios ride in the existing `MetricResult.reason`.
