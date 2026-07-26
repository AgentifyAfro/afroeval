# Spec — Scorecard: Key Observations, Radar & Dimension Confidence Intervals

**Date:** 2026-07-26
**Status:** Approved (design) — pending implementation plan
**Scope:** Spec 1 of 2. (Spec 2 = console readability/contrast pass, tracked separately.)

## 1 · Goal

Add three things to the AfroEval Scorecard, on **both** the generated PDF/JSON
scorecard and the Streamlit console scorecard-detail view:

1. A **Key Observations** section (auto-generated bullet notes) with a **radar / spider
   chart** over the six quality dimensions, placed **immediately before the Remediation
   Roadmap** section.
2. A **95% confidence interval** on each dimension score.

Built from **one shared, dependency-free core** so the PDF and console never drift.

## 2 · Non-goals / decisions

- **No new dependencies.** `matplotlib`/`plotly` are not installed; the radar is drawn
  from a shared geometry helper with two thin renderers (ReportLab vector shapes for the
  PDF, hand-built inline SVG for the console). `reportlab`, `numpy`, `PIL`, `altair` are
  already present.
- **No `METHODOLOGY_VERSION` bump.** The CI is a descriptive statistic; composite score,
  verdict bands, weights, and the safety veto are all unchanged. This changes what the
  scorecard *reports*, not how it *scores*. (Approved.)
- **Observations are dimension-level + flags only** — no per-language breakdown. The
  scorecard does not persist per-run per-language composites, and adding that is out of
  scope for this spec. (Approved.)
- **CIs display in the dimension table / metrics, not as whiskers on the radar** — keeps
  the v1 radar legible. (Approved.)
- **CI method: normal approximation** (`mean ± 1.96·SE`), clamped to `[0, 100]`. (Approved.)

## 3 · Components (each isolated and unit-testable)

| Module | New/Chg | Responsibility |
|---|---|---|
| `scoring/statistics.py` | new | `mean_ci_normal(values, z=1.96) -> tuple[float, float] \| None`. Pure. Returns `None` only when `n < 2`. A zero-variance sample yields a valid zero-width CI `[mean, mean]`. |
| `scoring/engine.py` | chg | Compute per-dimension CI from the per-item score lists it already receives; add `dimension_confidence_intervals` to `ScoringResult`. Composite/verdict logic untouched. |
| `db/models.py` + Alembic | chg | New `Scorecard.dimension_confidence_intervals` JSON column (default `{}`); one migration, kept single-head. |
| `orchestration/dispatcher.py` | chg | Persist `result.dimension_confidence_intervals` onto the `Scorecard`. |
| `reporting/observations.py` | new | `build_key_observations(scorecard) -> list[str]`. Pure. |
| `reporting/radar.py` | new | `radar_geometry(scores, ...)` (pure) + `radar_drawing(...)` (ReportLab `Drawing`) + `radar_svg(...)` (str). |
| `reporting/generator.py` | chg | New `_key_observations_section` inserted between the dimension table and the remediation section; add a "95% CI" column to the dimension table. |
| `console/app.py` | chg | Same section in the scorecard-detail view: observations bullets + radar (SVG) + CI shown with each dimension metric. |

## 4 · Confidence intervals

- **Input:** `compute_composite_score` already receives
  `dimension_raw_scores: dict[str, list[float]]` — the per-item score observations per
  dimension (0.0–1.0). No new data plumbing.
- **Computation:** for each dimension **not in `_RUN_LEVEL_DIMENSIONS`**,
  `mean_ci_normal(scores)` → `(lo, hi)` on the 0–1 scale; the engine scales `×100` and
  **clamps to `[0, 100]`**. Result stored as `dimension_confidence_intervals[dim] =
  [lo100, hi100]`; the dimension is omitted when the CI is `None`.
- **Persistence:** new `Scorecard.dimension_confidence_intervals` JSON column. Written by
  the dispatcher. **Historical scorecards** have an empty field → display renders **"—"**.
  No backfill.
- **Edge cases:**
  - `n < 2` → `None` → "—".
  - **Run-level dimensions** (`_RUN_LEVEL_DIMENSIONS = {"bias_fairness"}`) are excluded by
    name from CI computation: their `dimension_raw_scores` list is one run-level statistic
    replicated across items, not a real item-level sample, so a CI would be meaningless.
    They render **"—"** labelled *"run-level statistic"*. (Excluding by name — not by
    detecting `std == 0` — so a *genuinely unanimous* real dimension, e.g. every item
    scored 1.0, still gets its honest zero-width CI `[100, 100]` rather than "—".)
  - Not-evaluated dimensions → excluded (no items).

## 5 · Radar chart

- Six axes = the real dimensions: Language Performance, Cultural Appropriateness,
  Hallucination Risk, Bias & Fairness, Code-Switching Quality, Safety & Robustness.
- `radar_geometry(dim_scores, size)` returns axis endpoints, ring polylines, and the score
  polygon vertices (0–100 → radius). One geometry, two renderers, so PDF and console match.
- Renderers: `radar_drawing()` builds a `reportlab.graphics.shapes.Drawing` (embeds as a
  flowable); `radar_svg()` returns an inline SVG string (rendered in the console via
  `st.image` / `components.html`). Brand palette (purple→blue→cyan) reused.
- Kept clean: rings + labelled axes + the single score polygon. No CI band in v1.

## 6 · Key Observations

`build_key_observations(scorecard)` returns an ordered list of short strings:

1. **Strongest** dimension (max score among evaluated).
2. **Weakest** dimension (min score among evaluated).
3. One bullet per dimension **below `FAILING_THRESHOLD` (60)** — "… below pass threshold".
4. Active **flags**: safety veto (`verdict == HIGH_RISK` on safety), `low_coverage`,
   `african_fabrication_detected`, `safety_unverified`.

All derived from fields already on the `Scorecard`. Same function feeds PDF and console.

## 7 · Display placement

- **PDF** (`_build_pdf` story order): cover → dimension table → **Key Observations + radar**
  → remediation → failing → footer. Dimension table gains a "95% CI" column, e.g.
  `84.2  [78.5–89.9]`; "—" when unavailable.
- **Console** scorecard-detail view: Key Observations bullets + radar (SVG) above/next to
  the dimension metrics; each `st.metric` gains a CI caption (e.g. "95% CI 78.5–89.9").

## 8 · Testing (TDD)

- **Unit:** `mean_ci_normal` (n<2 → None, known values → known CI, std0 → `[mean, mean]`,
  clamp to [0,100]); engine excludes `_RUN_LEVEL_DIMENSIONS` from CIs; `build_key_observations`
  (strongest/weakest selection, each flag, ordering, degenerate/empty scorecard);
  `radar_geometry` (6 vertices, closed polygon, known coords).
- **Integration:** engine emits CIs without changing composite/verdict; dispatcher persists
  them; Alembic migration up/down (single head); PDF bytes build with the new section; a
  historical scorecard (empty CI field) renders "—" and still builds.

## 9 · Risks & mitigations

- **Migration on prod is manual** (deploy doesn't auto-run migrations, per project notes) —
  the plan must call out `alembic upgrade head` on prod, and confirm a single head.
- **ReportLab radar** is hand-drawn geometry — covered by `radar_geometry` unit tests and a
  PDF-builds smoke test.
- **Degenerate CI** (bias, low-n) — explicitly handled as "—" so nothing renders a
  nonsensical interval.
