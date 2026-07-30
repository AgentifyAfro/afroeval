# Design — Faithful per-language composite in Language Comparison

**Date:** 2026-07-30
**Status:** Approved design, pre-implementation
**Author:** Dan Haile (with Claude)

## Problem

The **Language Comparison** view shows a per-language "composite" (e.g. English 72.8,
Amharic 79.7 on the gpt-4o run) that viewers naturally read as *the* composite score. It is
**not** the certified composite the Run Scorecard reports. `console/app.py:load_language_breakdown`
re-aggregates from raw `MetricResult` rows with a **different, unweighted formula** that
diverges from the engine (`scoring/engine.py`) in load-bearing ways:

1. **No dimension weights.** The engine weights `language_performance` at 0.25 and
   `code_switching`/`safety` at 0.10 each (`DEFAULT_WEIGHTS`). The table takes an **unweighted
   mean of the six dimension means** — low-weight dimensions pull as hard as high-weight ones.
2. **It pools in metrics the engine deliberately excludes.** `DEFAULT_METRIC_WEIGHTS` scores
   `language_performance` from `semantic_similarity`/`answer_completeness`/`fluency` only, and
   `hallucination_risk` from `faithfulness` only. The table also folds in `chrf_score`,
   `multilingual_similarity`, and the `african_hallucination_probe` gate rows.
3. No renormalization / safety-veto / coverage logic beyond skipping `None` dimensions.

### Evidence (verified against the live gpt-4o run)

| Lang | LP table→engine | Cultural | Halluc. | Code-switch | Safety | Composite table → engine |
|---|---|---|---|---|---|---|
| English | 51.8 → **80.4** | 52.8 | 98.4 | 78.7 | 80.6 | **72.8 → 77.9** |
| Amharic | 45.0 → 75.2 | 69.6 | 82.0 | 95.0 | 93.5 | 79.7 → 80.5 |
| Oromo | 50.9 → 78.4 | 71.9 | 95.9 | 100 | 100 | 84.1 → 86.1 |

English's language-performance metric means: `semantic_similarity=100, fluency=100,
answer_completeness=34.5` (engine LP = 80.4) — but the pooled table LP is dragged to 51.8 by
`chrf_score=24.6` and `multilingual_similarity=0.0`. Correcting the aggregation lifts English's
composite from the displayed 72.8 to a faithful **77.9**. The bug deflates every language.

## Non-goals / out of scope

- **Not** changing the engine, the certified run composite, the packs, or any score-affecting
  logic. This is a **read/display re-aggregation fix** only.
- English will still read ~77.9 — **below** Amharic/Oromo — because its
  `cultural_appropriateness = 52.8` on a US customer-service pack under African-context rubrics
  is genuine (the methodology measuring contextual quality, not capability). Making the number
  *truthful* is the goal, not making English "win."
- `multilingual_similarity = 0.0` across all languages (a dead/broken metric persisting zeros)
  is a **separate** investigation, parked.
- Judge-LLM upgrade (Azure gpt-4.1-mini → newer) is a **separate** methodology experiment, parked.

## Design

### New: `scoring/aggregate.py`

A single, pure, tested helper that applies the engine's weighting rules to already-aggregated
per-metric means — the single source of truth both the engine constants and this view share.

```python
def composite_from_metric_means(
    metric_means: dict[str, dict[str, float]],
) -> tuple[dict[str, float | None], float | None]:
    """Given {dimension: {metric_name: mean_score_0-1}}, return
    (dimension_scores_0-100, composite_0-100) using scoring.engine.DEFAULT_WEIGHTS +
    DEFAULT_METRIC_WEIGHTS.

    - Scored dimensions in DEFAULT_METRIC_WEIGHTS (language_performance, hallucination_risk,
      code_switching_quality, safety_robustness): weighted mean over the NAMED sub-metrics
      present, renormalized over their weights. Unnamed metrics (chrf_score,
      multilingual_similarity, african_hallucination_probe) are ignored.
    - Other dimensions (cultural_appropriateness, bias_fairness): flat mean of their metric
      means (matches the engine, which does not sub-weight them).
    - A dimension with no usable metric means -> None (dropped).
    - Composite: weighted over present dimensions via DEFAULT_WEIGHTS, renormalized over the
      present weights (mirrors engine.py:217-226). None if no dimension is present.
    """
```

Reuses the existing `DEFAULT_WEIGHTS` / `DEFAULT_METRIC_WEIGHTS` — **no new numbers**.

### Changed: `console/app.py:load_language_breakdown`

- Pull metric means per `(language, dimension, metric_name)` (add `metric_name` to the current
  `(language, dimension)` grouping — accumulate `{metric_name: [scores]}` then mean each).
- For each language, call `composite_from_metric_means(...)` → dimension scores + composite.
- Populate the existing DataFrame columns (`DIM_SHORT` per-dimension means + `composite`) from
  the helper's output. The downstream table, heatmap tint, and Δ-vs-EN logic are unchanged —
  they just consume corrected numbers.

### Data flow

`MetricResult` rows → group by (lang, dim, metric_name) → per-metric means (0-1) →
`composite_from_metric_means` → per-dim scores (0-100) + composite (0-100) → DataFrame → table.

## Approximation note

The engine computes each dimension **per item** (weighted sub-metric average) then means over
items; this helper computes a weighted average of **per-metric means**. Under full metric
coverage these are algebraically equal; with uneven coverage they differ negligibly. This is a
per-**language** re-aggregation (the certified composite is per-**run**), so it is intentionally
*methodologically consistent* with the engine, not bit-identical to a stored run composite.

## Error handling / edge cases

- Empty dimension / no metrics → dimension `None`, dropped from composite (renormalized).
- `bias_fairness` frequently absent per-language (single-cohort/language packs) → dropped,
  weights renormalize over the remaining five (as the engine does).
- No dimensions at all (empty language) → composite `None` → renders as `—` (existing behavior).
- All values remain `round(..., 1)` for display parity.

## Testing

- **Unit** (`tests/test_scoring_aggregate.py`): `composite_from_metric_means` on a fixed input
  reproduces the engine's dimension + composite math; asserts excluded metrics (`chrf_score`,
  `multilingual_similarity`, `african_hallucination_probe`) do NOT affect the result; asserts
  renormalization when `bias_fairness` is absent.
- **Regression**: a case mirroring the English gpt-4o profile → composite ≈ 77.9, and confirms
  it is higher than the old unweighted pooling would give.
- Full suite stays green; ruff clean.

## Rollout

Presentation/read-path change on `master` via the usual branch → review → merge → Cloud reboot.
No migration, no re-scoring, no pack changes.
