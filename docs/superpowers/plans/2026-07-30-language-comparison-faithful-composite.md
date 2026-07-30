# Faithful Per-Language Composite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Language Comparison table's per-language dimension scores and composite use the engine's weighted, metric-filtered methodology instead of an unweighted pooling that folds in engine-excluded metrics.

**Architecture:** Add one pure helper (`scoring/aggregate.py`) that applies the engine's `DEFAULT_WEIGHTS` + `DEFAULT_METRIC_WEIGHTS` to already-aggregated per-metric means, then rewire `console/app.py:load_language_breakdown` to group metrics per `(language, dimension, metric_name)` and call it. No engine/scoring behavior changes — read/display re-aggregation only.

**Tech Stack:** Python 3.12, SQLModel, pandas, Streamlit, pytest, ruff. Venv: `.venv/`.

## Global Constraints

- Run everything through the venv: `./.venv/Scripts/python.exe`.
- Metric scores in the DB (`MetricResult.score`) are **0–1**; dimension/composite display values are **0–100**.
- Single source of truth for weights = `scoring/engine.py` `DEFAULT_WEIGHTS` + `DEFAULT_METRIC_WEIGHTS`. Do NOT hardcode weight numbers anywhere else.
- Excluded-from-scoring metrics (must NOT affect scored dimensions): `chrf_score`, `multilingual_similarity`, `african_hallucination_probe`.
- `cultural_appropriateness` and `bias_fairness` are NOT in `DEFAULT_METRIC_WEIGHTS` → flat mean of their metric means (matches the engine).
- Do not touch `scoring/engine.py`, evaluators, packs, or the certified run composite.
- Work on branch `feat/lang-faithful-composite`. ruff must pass; full suite (`./.venv/Scripts/python.exe -m pytest tests/ -q`) must stay green.
- Never commit without following the repo rhythm (branch → tests green → commit). End commit messages with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: `scoring/aggregate.py` helper + unit tests

**Files:**
- Create: `scoring/aggregate.py`
- Test: `tests/test_scoring_aggregate.py`

**Interfaces:**
- Consumes: `scoring.engine.DEFAULT_WEIGHTS`, `scoring.engine.DEFAULT_METRIC_WEIGHTS`.
- Produces:
  - `composite_from_metric_means(metric_means: dict[str, dict[str, float]]) -> tuple[dict[str, float | None], float | None]` — input `{dimension: {metric_name: mean_0-1}}`; returns `(dimension_scores_0-100, composite_0-100)`. `dimension_scores` maps every input dimension to a 0–100 score or `None`; `composite` is `None` when no dimension is present.
  - `_dimension_score(dimension: str, metric_means: dict[str, float]) -> float | None` — one dimension's 0–100 score.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scoring_aggregate.py
"""Tests for scoring.aggregate — the post-hoc composite helper the Language Comparison
view uses so it stays consistent with the engine's weighted, metric-filtered composite."""
import pytest

from scoring.aggregate import composite_from_metric_means, _dimension_score


def test_language_performance_ignores_excluded_metrics():
    # semantic 0.50 + completeness 0.30 + fluency 0.20; chrf / multilingual must NOT count.
    mm = {"semantic_similarity": 1.0, "answer_completeness": 0.345, "fluency": 1.0,
          "chrf_score": 0.246, "multilingual_similarity": 0.0}
    # 0.5*1.0 + 0.3*0.345 + 0.2*1.0 = 0.8035 -> 80.35
    assert _dimension_score("language_performance", mm) == pytest.approx(80.35, abs=0.01)


def test_hallucination_ignores_probe_gate():
    mm = {"faithfulness": 0.984, "african_hallucination_probe": 1.0}
    assert _dimension_score("hallucination_risk", mm) == pytest.approx(98.4, abs=0.01)


def test_unweighted_dimensions_use_flat_mean():
    # cultural_appropriateness is not in DEFAULT_METRIC_WEIGHTS -> flat mean of metric means.
    mm = {"cultural_score": 0.5, "some_other": 0.7}
    assert _dimension_score("cultural_appropriateness", mm) == pytest.approx(60.0, abs=0.01)


def test_empty_dimension_is_none():
    assert _dimension_score("language_performance", {}) is None
    assert _dimension_score("cultural_appropriateness", {}) is None


def test_partial_submetrics_renormalize():
    # Only fluency present (weight 0.20) -> renormalized to 100% of that metric.
    assert _dimension_score("language_performance", {"fluency": 0.9}) == pytest.approx(90.0, abs=0.01)


def test_composite_weighted_and_renormalized_when_bias_absent():
    # English gpt-4o profile (no bias_fairness) -> faithful composite ~77.9.
    metric_means = {
        "language_performance": {"semantic_similarity": 1.0, "answer_completeness": 0.345,
                                 "fluency": 1.0, "chrf_score": 0.246, "multilingual_similarity": 0.0},
        "cultural_appropriateness": {"cultural_score": 0.528},
        "hallucination_risk": {"faithfulness": 0.984, "african_hallucination_probe": 1.0},
        "code_switching_quality": {"register_match": 0.787, "switch_naturalness": 0.787,
                                   "language_preservation": 0.787},
        "safety_robustness": {"harmful_content": 0.806, "refusal_calibration": 0.806,
                              "adversarial_robustness": 0.806},
    }
    dim_scores, composite = composite_from_metric_means(metric_means)
    assert dim_scores["language_performance"] == pytest.approx(80.35, abs=0.01)
    assert dim_scores.get("bias_fairness") is None  # absent input -> not in dict / None
    assert round(composite, 1) == 77.9  # weighted over 0.85 (bias 0.15 dropped), renormalized


def test_no_dimensions_composite_none():
    dim_scores, composite = composite_from_metric_means({})
    assert composite is None
    assert dim_scores == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_scoring_aggregate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scoring.aggregate'`.

- [ ] **Step 3: Write the helper**

```python
# scoring/aggregate.py
"""Post-hoc composite aggregation from persisted metric means.

The live scoring path (scoring/engine.py) computes the certified composite per RUN, per item.
This helper applies the SAME weighting rules (DEFAULT_WEIGHTS + DEFAULT_METRIC_WEIGHTS) to
already-aggregated per-metric means, so re-aggregations — e.g. the console's per-LANGUAGE
Language Comparison table — stay methodologically consistent with the scorecard instead of
inventing an unweighted formula. The engine constants below are the single source of truth.
"""
from scoring.engine import DEFAULT_METRIC_WEIGHTS, DEFAULT_WEIGHTS


def _dimension_score(dimension: str, metric_means: dict[str, float]) -> float | None:
    """One dimension's 0-100 score from its {metric_name: mean_0-1}.

    Dimensions in DEFAULT_METRIC_WEIGHTS: weighted mean over the NAMED sub-metrics present
    (renormalized over their weights); unnamed metrics (chrf_score, multilingual_similarity,
    african_hallucination_probe) are ignored. Other dimensions (cultural_appropriateness,
    bias_fairness): flat mean of all their metric means. None if nothing usable.
    """
    if not metric_means:
        return None
    weights = DEFAULT_METRIC_WEIGHTS.get(dimension)
    if weights:
        present = {m: metric_means[m] for m in weights if m in metric_means}
        total = sum(weights[m] for m in present)
        if not present or total == 0:
            return None
        return sum(metric_means[m] * weights[m] for m in present) / total * 100.0
    vals = list(metric_means.values())
    return sum(vals) / len(vals) * 100.0


def composite_from_metric_means(
    metric_means: dict[str, dict[str, float]],
) -> tuple[dict[str, float | None], float | None]:
    """Return (dimension_scores_0-100, composite_0-100) from {dimension: {metric_name: mean_0-1}},
    applying scoring.engine.DEFAULT_WEIGHTS + DEFAULT_METRIC_WEIGHTS. The composite is a weighted
    mean over the dimensions present, renormalized over their weights (mirrors engine.py). Composite
    is None when no weighted dimension is present."""
    dim_scores: dict[str, float | None] = {
        dim: _dimension_score(dim, mm) for dim, mm in metric_means.items()
    }
    present = {d: s for d, s in dim_scores.items() if s is not None and d in DEFAULT_WEIGHTS}
    if not present:
        return dim_scores, None
    total_w = sum(DEFAULT_WEIGHTS[d] for d in present)
    composite = sum(present[d] * DEFAULT_WEIGHTS[d] for d in present) / total_w
    return dim_scores, composite
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_scoring_aggregate.py -q`
Expected: PASS (7 tests). Then `./.venv/Scripts/python.exe -m ruff check scoring/aggregate.py tests/test_scoring_aggregate.py` → All checks passed.

- [ ] **Step 5: Commit**

```bash
git add scoring/aggregate.py tests/test_scoring_aggregate.py
git commit -m "feat(scoring): composite_from_metric_means — engine-faithful post-hoc aggregation

Applies DEFAULT_WEIGHTS + DEFAULT_METRIC_WEIGHTS to per-metric means so
re-aggregations match the certified composite. Excludes chrf_score /
multilingual_similarity / african_hallucination_probe from scored dims.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Rewire `load_language_breakdown` to use the helper

**Files:**
- Modify: `console/app.py` (import near line 66; `load_language_breakdown` body, currently lines 486–567)

**Interfaces:**
- Consumes: `scoring.aggregate.composite_from_metric_means` (from Task 1).
- Produces: same `pd.DataFrame` shape as before — one row per (language, model-group) with `DIM_SHORT` columns (`LP`, `CA`, `HR`, `BF`, `CS`, `SR`) and `composite`, now weighted + metric-filtered. Downstream consumers (`render_language_breakdown`, heatmap tint, Δ-vs-EN) are unchanged.

- [ ] **Step 1: Add the import**

Add near the other `console/app.py` imports (after line 66, `from hitl.label_config import AUTHORING_PROJECT_TITLE`):

```python
from scoring.aggregate import composite_from_metric_means
```

- [ ] **Step 2: Change the accumulator type**

In `load_language_breakdown`, replace the per-dimension list accumulator (currently line ~502):

```python
        lang_dim_scores: dict[str, dict[str, list[float]]] = {}
```

with a per-metric accumulator:

```python
        lang_metric_scores: dict[str, dict[str, dict[str, list[float]]]] = {}
```

- [ ] **Step 3: Change the per-language init and the metric-append loop**

Replace the per-language init (currently lines ~538–539):

```python
                    if lang not in lang_dim_scores:
                        lang_dim_scores[lang] = {dim: [] for dim in DIM_SHORT}
```

with:

```python
                    if lang not in lang_metric_scores:
                        lang_metric_scores[lang] = {dim: {} for dim in DIM_SHORT}
```

Replace the metric-append loop (currently lines ~541–544):

```python
                for m in metrics:
                    lang = resp_to_lang.get(str(m.response_id), "unknown")
                    if m.dimension in lang_dim_scores.get(lang, {}):
                        lang_dim_scores[lang][m.dimension].append(m.score)
```

with (accumulate per metric_name):

```python
                for m in metrics:
                    lang = resp_to_lang.get(str(m.response_id), "unknown")
                    dims = lang_metric_scores.get(lang, {})
                    if m.dimension in dims:
                        dims[m.dimension].setdefault(m.metric_name, []).append(m.score)
```

- [ ] **Step 4: Change the row-building block to use the helper**

Replace the aggregation block (currently lines ~549–565):

```python
        key_run_id = group_run_ids[0]
        for lang, dim_data in lang_dim_scores.items():
            row: dict = {
                "language":   lang,
                "model":      model_label or "unknown",
                "provider":   provider,
                "run_id":     key_run_id,
                "item_count": lang_counts.get(lang, 0),
            }
            dim_means = []
            for dim, short in DIM_SHORT.items():
                scores = dim_data[dim]
                mean   = round(sum(scores) / len(scores) * 100, 1) if scores else None
                row[short] = mean
                if mean is not None:
                    dim_means.append(mean)
            row["composite"] = round(sum(dim_means) / len(dim_means), 1) if dim_means else None
            rows.append(row)
```

with (mean each metric, then apply the engine-faithful helper):

```python
        key_run_id = group_run_ids[0]
        for lang, dim_metrics in lang_metric_scores.items():
            metric_means = {
                dim: {mn: sum(s) / len(s) for mn, s in metrics.items() if s}
                for dim, metrics in dim_metrics.items()
            }
            dim_scores, composite = composite_from_metric_means(metric_means)
            row: dict = {
                "language":   lang,
                "model":      model_label or "unknown",
                "provider":   provider,
                "run_id":     key_run_id,
                "item_count": lang_counts.get(lang, 0),
            }
            for dim, short in DIM_SHORT.items():
                val = dim_scores.get(dim)
                row[short] = round(val, 1) if val is not None else None
            row["composite"] = round(composite, 1) if composite is not None else None
            rows.append(row)
```

- [ ] **Step 5: Compile, lint, import-smoke**

Run:
```bash
./.venv/Scripts/python.exe -m py_compile console/app.py
./.venv/Scripts/python.exe -m ruff check console/app.py
./.venv/Scripts/python.exe -c "import console.app"
```
Expected: compile OK, ruff clean, import OK (Streamlit "no runtime" warnings are fine).

- [ ] **Step 6: Empirical verification against live data**

Re-run the diagnostic probe (already in scratchpad) OR this inline check; confirm English's engine-faithful composite is ~77.9 and the table now agrees:

Run:
```bash
./.venv/Scripts/python.exe -c "
import os; os.environ['AFROEVAL_SQL_ECHO']='0'
import console.app as a
from console.app import load_provider_comparison, load_language_breakdown
rows = load_provider_comparison.__wrapped__()
rids = tuple(sorted({r['run_id'] for r in rows if r['model_identifier']=='gpt-4o'}))
df = load_language_breakdown.__wrapped__(rids, ())
print(df[['language','LP','CA','composite']].to_string(index=False))
" 2>&1 | grep -avE "WARNING|runtime|streamlit run"
```
Expected: `en` composite ≈ 77.9 (was 72.8), `am` ≈ 80.5, `om` ≈ 86.1; `en` `LP` ≈ 80.4 (was 51.8).

- [ ] **Step 7: Full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q -p no:warnings`
Expected: all pass (prior baseline: 388 passed, 8 skipped) + Task 1's new tests.

- [ ] **Step 8: Commit**

```bash
git add console/app.py
git commit -m "fix(console): Language Comparison uses the engine-faithful composite

load_language_breakdown now groups metrics per (language, dimension,
metric_name) and calls scoring.aggregate.composite_from_metric_means, so
per-language dimension scores + composite are weighted (DEFAULT_WEIGHTS) and
metric-filtered — matching the Run Scorecard. Drops the unweighted pooling
that folded in chrf_score / multilingual_similarity / the hallucination probe.
English 72.8 -> 77.9; the table and the scorecard methodology now agree.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Helper `scoring/aggregate.py` with the exact interface + weighting rules → Task 1. ✓
- Excludes chrf/multilingual/probe; flat mean for cultural/bias; renormalized composite → Task 1 (`_dimension_score`, `composite_from_metric_means`) + tests. ✓
- `load_language_breakdown` rewired to per-(lang,dim,metric) + helper → Task 2. ✓
- Edge cases (empty dim → None; bias absent → renormalize; empty language → composite None) → Task 1 tests + Task 2 rounding guards. ✓
- Testing (unit reproduces engine math; English ≈ 77.9 regression) → Task 1 Step 1 + Task 2 Step 6. ✓
- Non-goals (no engine/pack changes; English still ~77.9) → honored; no engine edits in any task. ✓

**Placeholder scan:** none — every step has runnable code/commands. ✓

**Type consistency:** `composite_from_metric_means` / `_dimension_score` signatures match between Task 1 (defined) and Task 2 (consumed); DB scores 0–1 in, 0–100 out, consistent throughout. ✓

**Note:** `load_language_breakdown` queries the DB directly and isn't unit-tested in isolation (no fixtures); its correctness rests on Task 1's helper tests plus the Task 2 Step 6 live check — called out honestly rather than faking a DB test.
