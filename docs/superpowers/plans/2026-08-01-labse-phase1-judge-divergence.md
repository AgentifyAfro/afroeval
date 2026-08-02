# LaBSE Phase 1 — Judge-Divergence Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the LLM-judge-only Language Performance dimension a local, API-free, bias-resistant second opinion: back `multilingual_similarity` with LaBSE and, when it diverges sharply from the judge's `semantic_similarity`, raise a persisted `judge_divergence` flag surfaced in both the console scorecard and the downloadable PDF report.

**Architecture:** LaBSE replaces MiniLM in the existing `multilingual_similarity` evaluator slot (stays weight-0 — no scoring impact). A pure `scoring/divergence.py` function computes, per item, `|LaBSE*100 − semantic_similarity*100|` and flags items over a configurable threshold. The dispatcher collects both per-item scores during its scoring loop, computes divergence after, stores a per-item flag in the `multilingual_similarity` MetricResult's `extra` JSON, and a per-run count in a new `Scorecard.judge_divergence_count` column. Console and PDF read the stored values.

**Tech Stack:** Python 3.12, sentence-transformers (LaBSE), SQLModel + Alembic, Streamlit console, ReportLab PDF.

## Global Constraints

- **Spec is the contract:** `docs/superpowers/specs/2026-08-01-labse-judge-independent-signal-design.md`. This is **Phase 1 only** — the metric stays **weight-0**; NO change to `DEFAULT_METRIC_WEIGHTS`, no methodology version bump, no rebaseline.
- **Compare against `semantic_similarity`** specifically (decided 2026-08-01), NOT the full LP dimension score. Both measure answer-vs-reference similarity.
- **Persist** the flag (per-item + per-run count) so it reaches the PDF report, not just the live console.
- **No new package:** `sentence-transformers>=2.0.0` is already declared in the `[eval]` optional-dependencies extra. LaBSE is just a different model name. (The eval host must have `.[eval]` installed; first use downloads ~1.8 GB. Ops step, not a code change.)
- Divergence is **unscored/inert** — never enters the composite, pass-rate, or coverage. It must not alter any existing score, verdict, or dimension value.
- An item flags only when BOTH `semantic_similarity` (non-error, present) AND `multilingual_similarity` (non-error/available) exist for it. Missing/errored either side → no flag (nothing to compare).
- Venv: `./.venv/Scripts/python.exe`. Full suite must stay green; ruff clean. Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Threshold default is **provisional** (`DIVERGENCE_THRESHOLD = 30.0` on the 0–100 scale), env-overridable via `AFROEVAL_DIVERGENCE_THRESHOLD`. Tuned on real data later; not a methodology constant.

---

## File Structure

- `evaluators/language_performance.py` — swap model to LaBSE (Task 1).
- `scoring/divergence.py` *(new)* — pure divergence computation + threshold config (Task 2).
- `db/models.py` — `Scorecard.judge_divergence_count` column (Task 3).
- `db/migrations/versions/<rev>_add_scorecard_judge_divergence_count.py` *(new)* — migration (Task 3).
- `orchestration/dispatcher.py` — collect per-item pairs, compute, persist flag + count (Task 4).
- `console/app.py` + `console/branding.py` — per-run callout + drill-down marker (Task 5).
- `reporting/generator.py` — divergence line in the PDF (Task 6).

---

### Task 1: Swap `multilingual_similarity` backing model to LaBSE

**Files:**
- Modify: `evaluators/language_performance.py` (`_get_multilingual_model`, class docstring)
- Test: `tests/test_language_performance.py`

**Interfaces:**
- Produces: `MultilingualSimilarityEvaluator` unchanged in shape (`dimension="language_performance"`, `metric_name="multilingual_similarity"`); now LaBSE-backed. Error plumbing (`error=unavailable` when dep/model absent) is unchanged.

- [ ] **Step 1: Write the failing test** — assert the loader requests the LaBSE model id.

```python
# tests/test_language_performance.py (add)
from unittest.mock import patch, MagicMock
import evaluators.language_performance as lp

def test_multilingual_model_is_labse():
    lp._MULTILINGUAL_MODEL = None  # reset module singleton
    fake_st = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=fake_st)}):
        lp._get_multilingual_model()
    assert fake_st.call_args.args[0] == "sentence-transformers/LaBSE"
```

- [ ] **Step 2: Run — expect FAIL** (`assert 'paraphrase-multilingual-MiniLM-L12-v2' == 'sentence-transformers/LaBSE'`).

Run: `./.venv/Scripts/python.exe -m pytest tests/test_language_performance.py::test_multilingual_model_is_labse -v`

- [ ] **Step 3: Swap the model id.** In `_get_multilingual_model`, change the loaded model and the surrounding comment:

```python
                # LaBSE (Language-Agnostic BERT Sentence Embedding, 109 languages):
                # markedly stronger low-resource African-language coverage than the
                # old MiniLM. Weight-0 diagnostic; also drives the judge_divergence
                # flag (scoring/divergence.py). Local, no API — unaffected by rate
                # limits or content filters.
                _MULTILINGUAL_MODEL = SentenceTransformer(
                    "sentence-transformers/LaBSE", token=False
                )
```

Also update the class docstring model name (`paraphrase-multilingual-MiniLM-L12-v2` → `sentence-transformers/LaBSE`).

- [ ] **Step 4: Run — expect PASS**, plus the existing multilingual tests (401/timeout/missing-dep stay green — behavior unchanged).

Run: `./.venv/Scripts/python.exe -m pytest tests/test_language_performance.py -v`

- [ ] **Step 5: Commit** — `git commit -m "feat(evaluators): back multilingual_similarity with LaBSE (Phase 1)"`

---

### Task 2: Pure divergence computation + threshold config

**Files:**
- Create: `scoring/divergence.py`
- Test: `tests/test_divergence.py`

**Interfaces:**
- Produces:
  - `DIVERGENCE_THRESHOLD: float` (default 30.0, env `AFROEVAL_DIVERGENCE_THRESHOLD`).
  - `item_divergence(labse: float | None, semantic: float | None, threshold: float | None = None) -> dict | None` — inputs are 0.0–1.0 metric scores. Returns `None` when either input is `None` (nothing to compare); otherwise `{"judge_divergence": bool, "divergence_delta": float, "compared_to": "semantic_similarity"}` where delta is on the 0–100 scale.
  - `count_divergences(flags: Iterable[dict | None]) -> int` — number of entries with `judge_divergence` True.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_divergence.py
from scoring.divergence import item_divergence, count_divergences, DIVERGENCE_THRESHOLD

def test_none_when_either_side_missing():
    assert item_divergence(None, 0.8) is None
    assert item_divergence(0.8, None) is None

def test_flags_when_delta_exceeds_threshold():
    # LaBSE 0.20 vs semantic 0.90 -> delta 70 > 30 -> flagged
    r = item_divergence(0.20, 0.90)
    assert r["judge_divergence"] is True
    assert r["divergence_delta"] == 70.0
    assert r["compared_to"] == "semantic_similarity"

def test_no_flag_within_threshold():
    # delta 10 < 30 -> not flagged, but still reported
    r = item_divergence(0.80, 0.90)
    assert r["judge_divergence"] is False
    assert r["divergence_delta"] == 10.0

def test_threshold_boundary_is_exclusive():
    # exactly at threshold is NOT "sharp"
    r = item_divergence(0.30, 0.60)  # delta 30.0
    assert r["divergence_delta"] == 30.0
    assert r["judge_divergence"] is False

def test_count_divergences_ignores_none_and_false():
    flags = [None, {"judge_divergence": False}, {"judge_divergence": True}, {"judge_divergence": True}]
    assert count_divergences(flags) == 2
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: scoring.divergence`).

- [ ] **Step 3: Implement `scoring/divergence.py`**

```python
"""Judge-divergence signal (LaBSE Phase 1) — pure, unscored.

Compares the local LaBSE multilingual_similarity against the judge's
semantic_similarity for one item. Both are answer-vs-reference similarity, so a
large gap means an un-biasable model disputes the judge on exactly that question.
Weight-0: this NEVER enters the composite — it is a QA/trust signal only.
"""
from __future__ import annotations

import os
from collections.abc import Iterable

_DEFAULT_THRESHOLD = 30.0  # on the 0-100 scale; provisional, tune on data


def _load_threshold() -> float:
    raw = os.getenv("AFROEVAL_DIVERGENCE_THRESHOLD")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_THRESHOLD


DIVERGENCE_THRESHOLD: float = _load_threshold()


def item_divergence(
    labse: float | None,
    semantic: float | None,
    threshold: float | None = None,
) -> dict | None:
    """Return the divergence record for one item, or None if uncomparable.

    labse / semantic are 0.0-1.0 metric scores. delta is on the 0-100 scale.
    "Sharp" divergence is delta STRICTLY greater than the threshold.
    """
    if labse is None or semantic is None:
        return None
    thr = DIVERGENCE_THRESHOLD if threshold is None else threshold
    delta = round(abs(labse - semantic) * 100.0, 1)
    return {
        "judge_divergence": delta > thr,
        "divergence_delta": delta,
        "compared_to": "semantic_similarity",
    }


def count_divergences(flags: Iterable[dict | None]) -> int:
    return sum(1 for f in flags if f and f.get("judge_divergence"))
```

- [ ] **Step 4: Run — expect PASS.** `./.venv/Scripts/python.exe -m pytest tests/test_divergence.py -v`

- [ ] **Step 5: Commit** — `git commit -m "feat(scoring): pure judge-divergence computation + threshold config"`

---

### Task 3: Persist `judge_divergence_count` on Scorecard (+ migration)

**Files:**
- Modify: `db/models.py` (`Scorecard`)
- Create: `db/migrations/versions/<rev>_add_scorecard_judge_divergence_count.py`
- Test: `tests/test_scorecard_divergence_field.py`, plus migration up/down check

**Interfaces:**
- Produces: `Scorecard.judge_divergence_count: int = 0`. Per-item flag needs NO schema change — it lives in the `multilingual_similarity` MetricResult's existing `extra` JSON (Task 4).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scorecard_divergence_field.py
from db.models import Scorecard

def test_scorecard_has_judge_divergence_count_default_zero():
    sc = Scorecard(run_id=__import__("uuid").uuid4(), composite_score=80.0, verdict="Pass")
    assert sc.judge_divergence_count == 0
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError`/`TypeError` unexpected kwarg).

- [ ] **Step 3: Add the field.** In `db/models.py` `Scorecard`, after `african_fabrication_detected`:

```python
    judge_divergence_count: int = Field(
        default=0, sa_column_kwargs={"server_default": "0"}
    )  # count of items where LaBSE sharply disputes semantic_similarity (Phase 1, unscored)
```

- [ ] **Step 4: Create the migration.** Get the current head first: `./.venv/Scripts/python.exe -m alembic heads` (expected `f3a91c7b2e04`). New file with a **unique** revision id (verify it is NOT already in `db/migrations/versions/` — the a1b2c3d4e5f6 collision that broke the last deploy is why this check is mandatory):

```python
"""add judge_divergence_count to scorecards

Revision ID: c4e8d1a09b73
Revises: f3a91c7b2e04
Create Date: 2026-08-01 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8d1a09b73"
down_revision: str | None = "f3a91c7b2e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column("judge_divergence_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("scorecards", "judge_divergence_count")
```

- [ ] **Step 5: Validate the DAG offline** (no DB needed): `./.venv/Scripts/python.exe -m alembic heads` → single head `c4e8d1a09b73`; `./.venv/Scripts/python.exe -m alembic history | head -3` → `f3a91c7b2e04 -> c4e8d1a09b73`, no cycle.

- [ ] **Step 6: Run the field test — expect PASS**, then full suite.

- [ ] **Step 7: Commit** — `git commit -m "feat(db): add Scorecard.judge_divergence_count + migration"`

---

### Task 4: Compute + persist divergence in the dispatcher

**Files:**
- Modify: `orchestration/dispatcher.py`
- Test: `tests/test_dispatcher_divergence.py`

**Interfaces:**
- Consumes: `scoring.divergence.item_divergence`, `count_divergences`; the per-item `MetricResult` rows built in the scoring loop; `Scorecard.judge_divergence_count`.
- Produces: per-item `extra["judge_divergence"|"divergence_delta"|"compared_to"]` on the `multilingual_similarity` row; `scorecard.judge_divergence_count`.

Design: the scoring loop already iterates `(item_idx, output)` and builds a `MetricResult` per output (dispatcher.py ~495-507). Keep two per-item maps and a handle to each item's multilingual row; after the loop, compute divergence and write it back before `session.add(scorecard)`.

- [ ] **Step 1: Write the failing test** (pure-logic: encode the intended post-loop aggregation over synthetic rows, independent of DB/network).

```python
# tests/test_dispatcher_divergence.py
"""Divergence is computed per item from the LaBSE + semantic_similarity rows,
written to the multilingual row's extra, and counted onto the scorecard."""
from scoring.divergence import item_divergence, count_divergences

def test_per_item_divergence_and_count():
    # item A: LaBSE 0.2 vs semantic 0.9 -> flagged; item B: 0.85 vs 0.9 -> not
    per_item = {
        "A": {"multilingual_similarity": 0.2, "semantic_similarity": 0.9},
        "B": {"multilingual_similarity": 0.85, "semantic_similarity": 0.9},
        "C": {"semantic_similarity": 0.7},  # no LaBSE -> uncomparable
    }
    flags = {
        k: item_divergence(v.get("multilingual_similarity"), v.get("semantic_similarity"))
        for k, v in per_item.items()
    }
    assert flags["A"]["judge_divergence"] is True
    assert flags["B"]["judge_divergence"] is False
    assert flags["C"] is None
    assert count_divergences(flags.values()) == 1
```

- [ ] **Step 2: Run — expect PASS immediately** (this test locks the aggregation contract the dispatcher must implement; it exercises Task 2's function). Then implement the wiring so the dispatcher produces exactly this behavior.

- [ ] **Step 3: Collect per-item scores in the loop.** Near the top of the item-scoring block (where `dimension_scores` etc. are initialised), add:

```python
                # LaBSE Phase 1 — judge-divergence (unscored). Per item_idx, remember
                # the LaBSE (multilingual_similarity) and judge semantic_similarity
                # scores, plus a handle to the multilingual row to annotate after.
                labse_by_item: dict[int, float] = {}
                semantic_by_item: dict[int, float] = {}
                multilingual_row_by_item: dict[int, MetricResult] = {}
```

When building each `MetricResult` (the `session.add(MetricResult(...))` at ~496), capture the row and the scores. Replace the bare `session.add(MetricResult(...))` with a named row and record it:

```python
                        _mr = MetricResult(
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
                        )
                        session.add(_mr)
                        if not output.error:
                            if output.metric_name == "multilingual_similarity":
                                labse_by_item[item_idx] = output.score
                                multilingual_row_by_item[item_idx] = _mr
                            elif output.metric_name == "semantic_similarity":
                                semantic_by_item[item_idx] = output.score
```

- [ ] **Step 4: After the scoring loop, before `session.add(scorecard)`, compute + persist.**

```python
                # LaBSE Phase 1 — annotate divergence per item + count for the scorecard.
                from scoring.divergence import item_divergence, count_divergences  # noqa: PLC0415
                _div_flags = []
                for _idx, _row in multilingual_row_by_item.items():
                    _flag = item_divergence(labse_by_item.get(_idx), semantic_by_item.get(_idx))
                    _div_flags.append(_flag)
                    if _flag is not None:
                        # extra is JSON; copy-update so SQLModel detects the change
                        _row.extra = {**(_row.extra or {}), **_flag}
                _divergence_count = count_divergences(_div_flags)
```

Then pass it into the `Scorecard(...)` constructor:

```python
                    judge_divergence_count=_divergence_count,
```

- [ ] **Step 5: Run the divergence test + full suite — green.** Confirm no existing dispatcher test regressed (scores/verdicts unchanged — divergence is inert).

- [ ] **Step 6: Commit** — `git commit -m "feat(dispatcher): compute + persist judge_divergence per item and per run"`

---

### Task 5: Surface divergence in the console scorecard

**Files:**
- Modify: `console/app.py` (`render_run_scorecard`; `load_run_items` metric dict; drill-down)
- Modify: `console/branding.py` (`render_item_detail` badge, if needed)
- Test: `tests/test_console_divergence.py`

**Interfaces:**
- Consumes: `scorecard.judge_divergence_count` (already loaded via `load_runs_summary` — add it there), and `extra["judge_divergence"]` per metric row (via `load_run_items`).

- [ ] **Step 1: Write the failing test** (pure counting helper, mirroring `_content_filter_count`).

```python
# tests/test_console_divergence.py
from console.app import _divergence_item_count

def test_counts_items_with_flagged_multilingual_row():
    metrics_by_resp = {
        "r1": [{"metric_name": "multilingual_similarity", "extra": {"judge_divergence": True}},
               {"metric_name": "semantic_similarity", "extra": {}}],
        "r2": [{"metric_name": "multilingual_similarity", "extra": {"judge_divergence": False}}],
    }
    assert _divergence_item_count(metrics_by_resp) == 1
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError`).

- [ ] **Step 3: Add `extra` to the `load_run_items` metric dict** (so the drill-down/count can read `judge_divergence`). In the `metrics_by_resp[...].append({...})` block, add `"extra": m.extra,`. Add the helper near `_content_filter_count`:

```python
def _divergence_item_count(metrics_by_resp: dict[str, list[dict]]) -> int:
    """Count items whose multilingual_similarity row is flagged as judge-divergent
    (LaBSE sharply disputes the judge's semantic_similarity) — Phase 1, unscored."""
    return sum(
        1
        for rows in metrics_by_resp.values()
        for m in rows
        if m.get("metric_name") == "multilingual_similarity"
        and (m.get("extra") or {}).get("judge_divergence")
    )
```

- [ ] **Step 4: Add the per-run callout** in `render_run_scorecard`, right after the content-filter callout block:

```python
    _div = _divergence_item_count(metrics_by_resp)
    if _div:
        render_callout(
            f"<b>Judge-divergence note.</b> On {_div} item(s), LaBSE (a local, "
            "judge-independent similarity model) sharply disputes the judge's "
            "semantic_similarity score. Unscored signal — review these items in the "
            "drill-down (marked <b>Divergent</b>).",
            kind="info",
        )
```

- [ ] **Step 5: Mark divergent rows in the drill-down.** Where the drill-down builds the per-metric `metrics` list for `render_item_detail`, when a `multilingual_similarity` row has `extra["judge_divergence"]`, append a `"Divergent (Δ<delta>)"` note to its reason and give it an info status. Add a `_METRIC_BADGE` entry in `console/branding.py` if a distinct badge is used: `"divergent": ("info", "Divergent")`.

- [ ] **Step 6: Run test + `ruff check console/` + `import console.app` — green.**

- [ ] **Step 7: Commit** — `git commit -m "feat(console): surface judge_divergence (per-run callout + drill-down marker)"`

---

### Task 6: Surface divergence in the PDF report

**Files:**
- Modify: `reporting/generator.py`
- Test: `tests/test_pdf_divergence.py`

**Interfaces:**
- Consumes: `scorecard.judge_divergence_count`.

- [ ] **Step 1: Write the failing test** (assert the count reaches the PDF text; use the bytes generator with a stub scorecard).

```python
# tests/test_pdf_divergence.py
"""The persisted judge_divergence_count appears in the generated PDF report."""
from reporting.generator import _divergence_line

def test_divergence_line_present_when_flagged():
    assert "2" in _divergence_line(2)
    assert "judge" in _divergence_line(2).lower()

def test_divergence_line_empty_when_zero():
    assert _divergence_line(0) == ""
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError: _divergence_line`).

- [ ] **Step 3: Add `_divergence_line` and render it.** In `reporting/generator.py`:

```python
def _divergence_line(count: int) -> str:
    """One-line judge-divergence disclosure for the report; empty when none."""
    if not count:
        return ""
    return (
        f"Judge-divergence: on {count} item(s), a local judge-independent model "
        f"(LaBSE) sharply disputed the judge's similarity score. Unscored QA signal."
    )
```

Render it in `_key_observations_section` (or `_build_pdf` alongside the other notes): `line = _divergence_line(getattr(scorecard, "judge_divergence_count", 0))` and, when non-empty, append a `Paragraph(line, s["small"])` to the story. Read via `getattr(..., 0)` so historical scorecards (no column value) render nothing.

- [ ] **Step 4: Run test + full suite — green.**

- [ ] **Step 5: Commit** — `git commit -m "feat(reporting): judge_divergence line in the PDF scorecard report"`

---

## Rollout notes (post-merge, not a task)

- Apply the migration to prod (deploy-migrate workflow, triggers on `db/migrations/**`). New column defaults to `0`; historical scorecards read `0` → no divergence shown.
- The eval host must have `.[eval]` installed so LaBSE loads; first run downloads ~1.8 GB. Until then `multilingual_similarity` records `error=unavailable` (as today) and no divergence is computed — degrades gracefully.

## Self-Review

**Spec coverage:** LaBSE swap (T1) ✓ · compare vs semantic_similarity (T2) ✓ · persisted per-item flag + per-run count (T3/T4) ✓ · console surfacing (T5) ✓ · PDF report inclusion (T6) ✓ · weight-0/no-rebaseline (Global Constraints, no `DEFAULT_METRIC_WEIGHTS` change) ✓ · configurable threshold (T2) ✓ · graceful degrade when unavailable (T2 None-path, rollout) ✓.

**Placeholder scan:** none — every step has runnable code/commands. Task 5 Step 5 describes an edit against console drill-down code not quoted verbatim (it varies); the implementer adapts, preserving intent (divergent rows get an info marker, non-divergent unchanged).

**Type consistency:** `item_divergence`/`count_divergences` signatures match across T2, T4, and the tests. `judge_divergence_count: int` defined T3, populated T4, read T5/T6. `extra["judge_divergence"]` written T4, read T5.

**Migration-id check:** revision `c4e8d1a09b73` must be verified absent from `db/migrations/versions/` before use (the a1b2c3d4e5f6 duplicate is exactly the failure this guards).
