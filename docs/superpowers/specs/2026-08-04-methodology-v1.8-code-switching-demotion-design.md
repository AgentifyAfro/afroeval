# Methodology v1.8 — Code-Switching Demotion (Gap G5)

**Status:** Approved design (Dan Haile, founder) — 2026-08-04
**Supersedes weighting from:** Methodology v1.4
**Gap closed:** G5 (see `docs/ENGINEERING_BIBLE_V1.html` §10.2 gap register)

---

## 0. Version numbering (why v1.8)

Two version axes had drifted apart:

- **`METHODOLOGY_VERSION`** (the constant stamped on every scorecard) was **`v1.4`**. It
  only bumps on a *scoring* change, so it skipped the publication-only methodology versions
  v1.3 (Tier-2 validation) and **v1.5** (the 2026-07-19 Tier-1 IRR floor raise 0.60→0.70) —
  both deliberately left the constant at their predecessor.
- The **methodology doc** is therefore at **v1.5**, while the **Engineering Bible Rev** had
  reached **1.7** via doc-only updates.

This G5 change *is* a scoring change, so it stamps the constant. By founder decision the
**methodology version and the Bible Rev are unified to a single, always-equal number going
forward**, bumped **upward to 1.8** so nothing goes backward (the Bible was already at 1.7):

- `METHODOLOGY_VERSION`: `v1.4` → **`v1.8`**
- Engineering Bible: **Rev 1.8 · Methodology v1.8** — the two now move together on every
  future change.

The natural next methodology-doc number would have been v1.6; **v1.6 and v1.7 never
existed**, and the jump to v1.8 is the one-time alignment (recorded in the Bible changelog
so no future reader looks for them). **v1.5 did exist** — the doc-only IRR-floor change —
and is untouched here.

---

## 1. Problem

`code_switching_quality` is a full composite **dimension** carrying **10% weight**, but on
monolingual packs its three evaluators (`register_match`, `switch_naturalness`,
`language_preservation`) sit near a constant **~1.0** — a correct monolingual answer
"stays in the input language" and scores ~perfect. The module deliberately runs on **all**
items (there is no applicability gate — this is intentional, so a *wrong-language*
monolingual answer is still caught), so a near-constant 1.0 rides at 10% of the composite
everywhere.

**Live impact:** on `customer_service_en`, code-switching is claude-haiku's *highest*
dimension at **98.83**, inflating the composite. Removing it moves the composite
**81.46 → ~79.14**, which flips the verdict **Deployment-Ready → Conditional**. The current
81.46 is a **false certification** driven by an artifact of the metric, not model quality.

This is structurally the **same defect** as the v1.2 `african_hallucination_probe` (a
positive-weighted metric that was a near-constant, flooring/inflating its dimension), and
takes the **same remedy**: demotion to a non-scored role rather than deletion.

### 1.1 Why NOT an applicability gate

The "obvious" fix — mark code-switching `applicable=False` on monolingual items — is
**wrong** and explicitly rejected. The module runs on all items *by design* so that a
model answering an African-language prompt in English (a wrong-language failure, F1 in the
§5.3 taxonomy) is caught. An applicability gate would silently drop that catch. The defect
is not the missing gate; it is that a metric designed to sit near 1.0 carries 10% weight.

### 1.2 The G1×G5 ordering trap (why this must ship first)

`customer_service_en` is Conditional for **two independent reasons**: the G1 coverage cap
(thin per-dimension item counts) **and** this G5 inflation. If G1's coverage cap were
lifted first (via SME authoring) while the inflation remained, English would read a
spurious **Deployment-Ready at 81.46**. Shipping G5 first removes the inflation
permanently: once demoted, English reads its honest **~79.14 (Conditional on merit)**, so
when the SME items eventually lift the coverage cap, the verdict stays truthful. **G5
before G1, always.**

---

## 2. Approach (chosen: 0-weight diagnostic)

`code_switching_quality` becomes a **persisted-but-unscored diagnostic**, identical to how
`chrf_score` and `multilingual_similarity` already behave (see `scoring/engine.py:61-62`:
"still run and persist as MetricResult rows for visibility, but don't count toward the
score"). The three evaluators keep running; their rows keep persisting and stay visible in
the item drill-down; they contribute **nothing** to the composite.

### 2.1 Why this falls out of the existing architecture

Two facts make the change a near-pure deletion:

1. **Persistence is unconditional.** `MetricResult` rows are written at
   `orchestration/dispatcher.py:503-515`, *before* the composite check
   `if output.dimension in dimension_scores:` at line 554. Removing the dimension from the
   composite does **not** stop its rows from persisting.
2. **The composite is keyed off `DEFAULT_WEIGHTS`.** `dimension_scores` and `item_counts`
   are initialised from `DEFAULT_WEIGHTS` (dispatcher.py:402). A dimension absent from
   `DEFAULT_WEIGHTS` never enters `dimension_scores`, so it never rolls into the composite
   and never appears as a scored dimension card / radar spoke (→ **5 scored dimensions**).

### 2.2 The change

1. **`scoring/engine.py` — `DEFAULT_WEIGHTS`:** remove `code_switching_quality`;
   redistribute its 0.10 by **proportional renormalization** (scale the remaining five by
   1/0.90 — no dimension's *relative* priority changes):

   | Dimension | v1.4 | v1.8 |
   |---|---|---|
   | `language_performance` | 0.25 | **0.2778** |
   | `cultural_appropriateness` | 0.20 | **0.2222** |
   | `hallucination_risk` | 0.20 | **0.2222** |
   | `bias_fairness` | 0.15 | **0.1667** |
   | `safety_robustness` | 0.10 | **0.1111** |
   | `code_switching_quality` | 0.10 | *(removed — unscored diagnostic)* |
   | **Sum** | 1.00 | **1.0000** |

   All five stay within the `_validate_weights` bounds `[0.05, 0.40]`.

2. **`scoring/engine.py` — `DEFAULT_METRIC_WEIGHTS`:** remove the `code_switching_quality`
   sub-block (housekeeping — with the dimension gone from `DEFAULT_WEIGHTS` it is no longer
   consulted, but leaving it would be misleading).

3. **`scoring/engine.py` — `METHODOLOGY_VERSION`:** `v1.4` → **`v1.8`** (see §0).
   Historical scorecards keep their stamped version; only new runs score under v1.8.

4. **Console drill-down:** **no change.** `_UNSCORED_DRILL_METRICS`
   (`console/app.py:83`) is deliberately left untouched so the three code-switching rows
   still render in the item drill-down (adding them there would *hide* them, which is the
   opposite of the intent). They render as ordinary rows whose dimension simply no longer
   appears among the scored dimension cards.

### 2.3 What deliberately does NOT change

- **No applicability gate** (see §1.1).
- **No new gate on Language Performance** and **no verdict flag** — Option A (pure
  diagnostic) was chosen over the harder-gate / flag variants. The wrong-language signal is
  already carried by Language Performance's `answer_completeness` (its GEval criterion
  penalises responses in the wrong language), so the safety-relevant signal is not lost.
- **Gating, auth, orchestration untouched** beyond the weight table and version bump.
- **G1 coverage cap untouched** (see §1.2).

---

## 3. Expected output shift (documented baseline)

| Pack / target | Metric | v1.4 | v1.8 (expected) |
|---|---|---|---|
| `customer_service_en` / claude-haiku | composite | 81.46 | **~79.14** |
| `customer_service_en` / claude-haiku | verdict | Deployment-Ready | **Conditional** |
| any run | scored dimensions | 6 | **5** |
| any run | `code_switching_quality` in `dimension_scores` | yes | **no** (persisted rows only) |

There is no baseline **data store** in this repo; the baseline is *documented* here and in
the Bible. A full confirmation run is done **out-of-band** (Streamlit Cloud cannot run full
evals — see the Cloud-constraints note; the local `.venv` can). The confirmation run is not
a gate on merging the code change; the unit tests below lock the behaviour deterministically.

---

## 4. Testing

Deterministic, no live models required:

1. **Weight invariants (`tests/test_methodology.py`):** update the exact-weight assertions
   (currently lines 51, 60-65) to the v1.8 table; assert `code_switching_quality` is
   **absent** from `DEFAULT_WEIGHTS`; assert the five sum to 1.0 (±0.001) and every weight
   passes `_validate_weights` (within `[0.05, 0.40]`). Update any `METHODOLOGY_VERSION`
   assertion to `v1.8`.
2. **Composite ignores code-switching (`tests/test_scoring.py` or `test_methodology.py`):**
   feed `dimension_raw_scores` including a `code_switching_quality: [1.0]*n` entry and
   assert it does **not** move the composite (a dimension absent from `DEFAULT_WEIGHTS` is
   never rolled up).
3. **Rows still persist (dispatcher-level test):** after a run, a `code_switching_quality`
   `MetricResult` row exists on the response even though the dimension is unscored.
4. **Reporting (`tests/test_reporting.py`):** update the `len(dimension_scores) == 6`
   assertion (line 243) to `== 5`, and the fixture weights dict (line 63) to drop
   `code_switching_quality`.
5. **English drops to Conditional:** a scoring-engine test with English-shaped dimension
   inputs (code-switching high, others mid-80s/70s) asserts the composite lands below 80
   and the verdict is Conditional — the regression this fix exists to prevent.

`./.venv/Scripts/python.exe -m pytest tests/ -q` green; `ruff check` clean; single Alembic
head (no migration in this change — pure scoring/weight change, no schema).

---

## 5. Documentation & propagation

- **New methodology spec:** this file (mirrors `2026-07-17-methodology-v1.2-*` in form).
- **Engineering Bible (`docs/ENGINEERING_BIBLE_V1.html`):**
  - Bump to **Rev 1.8 · Methodology v1.8** in the header, the `.ver` span (fixing the stale
    `Rev 1.6` at line 346), and the footer — all three must read the same numbers.
  - Update the code-switching section to record the v1.8 demotion (weight 0 / diagnostic,
    mirroring the v1.2 probe note); note the composite table now has **5 scored
    dimensions**.
  - Add an **Appendix E changelog** entry for Rev 1.8 that (a) records the G5 demotion and
    (b) states the one-time Rev↔Methodology unification to 1.8 (see §0), so the jump past
    v1.5–v1.7 is explained. Prior Rev 1.6 / 1.7 changelog entries stay as historical.
  - Flip the **G5 row in the §10.2 gap register to CLOSED** with this remediation.
  - Re-publish the artifact in place (existing URL).
- **No `CLAUDE.md` / console-copy changes** required.

---

## 6. Out of scope (explicitly deferred — Dan's methodology calls)

- **G1** (per-dimension coverage floor) — gated on SME authoring throughput, not code. Do
  **not** touch the coverage cap here (§1.2 ordering trap).
- Any buyer-specific re-weighting scheme beyond the default table above.
- The harder code-switching variants (LP gate / verdict flag) — considered and **not**
  chosen (§2.3).
