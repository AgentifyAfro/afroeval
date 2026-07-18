# Hallucination Risk Scoring — Methodology v1.2 Design

**Date:** 2026-07-17
**Status:** Approved (founder sign-off 2026-07-17) — implementation plan at
`docs/superpowers/plans/2026-07-17-methodology-v1.2-hallucination-scoring.md`
**Supersedes:** the scoring-weight decision in `2026-06-29-hallucination-probe-expansion-design.md`
(that spec's data expansion stands; only its "no `scoring/engine.py` change" line is revisited)

## Problem

`african_hallucination_probe` carries **60% of the `hallucination_risk` dimension**
(20% of the composite), and it has **scored 1.0 on 3,219 of 3,219 items — it has
never once fired**, across every run in the database. It is, empirically, a
constant. That means **~12% of every composite AfroEval Score is a hardcoded
`1.0`**, and the dimension is floored: `hallucination_risk` has never scored below
**71.4** no matter how unfaithful a model was.

Meanwhile the dimension's only real signal, `faithfulness` (DeepEval, 40% weight),
**averages 0.685 and passes only 1,757/3,219 (55%)** — it discriminates well, but it
is outvoted 60/40 by a constant.

The consequence is a defensibility problem, which is the one thing the methodology
cannot afford: a procurement committee that asks "what does the 60% component
actually measure on this run?" gets the answer "nothing — it returns 1.0 every
time." A model that hallucinates freely still scores ~71+ on the dimension named
*Hallucination Risk*.

## Why this supersedes the 2026-06-29 weighting decision

The prior spec was **correct on architecture and is not being reversed.**
Deterministic substring matching against a curated `AFRICAN_PROBES` list is the
right mechanism (an LLM judge would mean trusting a model as the source of truth
for niche African institutional facts with no retrieval step), and expanding the
list from 2 → 6 categories was the right fix for coverage.

That spec also **explicitly anticipated this metric's ceiling**: the marker
architecture "only catches *novel fabricated terms* cleanly — it can't catch a
*wrong pairing* of two otherwise-real terms," and it descoped relational errors
(capital/country) and live numerics (exchange rates) as architecturally out of
reach.

**The 0/3,219 result is the empirical confirmation of exactly that anticipated
limitation.** Real models essentially never emit an invented entity name verbatim
("AfriPay", "Republic of Sahelia"); they hallucinate *plausibly* — subtly wrong
facts about real institutions — which this architecture cannot, by design, detect.

So the defect is **not the probe, and not its fact coverage. It is the probe's
role in scoring.** A rare-but-serious red-flag detector should not carry 60%
*positive* weight, because **absence of a rare failure is not evidence of
quality.** Expanding the fact list further (the prior spec's "out of scope"
follow-up) would not change this: a broader list of novel-term markers still fires
almost never, so it would remain a near-constant.

## Design

### The formula

`hallucination_risk` becomes **per-item, faithfulness-scored, probe-gated**:

```
per_item(i) = 0.0                if african_hallucination_probe fired on item i
            = faithfulness(i)    otherwise

hallucination_risk = mean(per_item(i) over evaluated items) * 100
```

- The probe is **removed as a positive weight** from
  `DEFAULT_METRIC_WEIGHTS["hallucination_risk"]`; the dimension resolves to
  `faithfulness` on the flat path (like `cultural_appropriateness`).
- The probe becomes a **per-item hard zero**: a detected fabricated African entity
  is a hard fail *for that item*, not a small deduction. This matches problem
  taxonomy **F2** — fabricating a mobile-money operator or central bank carries
  direct financial/legal harm.
- **Proportional, not catastrophic**: one fabrication among many items drags the
  dimension down in proportion, rather than nuking an otherwise-sound run.
- With the probe never firing (today's reality), `hallucination_risk` **=
  mean(faithfulness)** — the honest measurement.

### What does not change

- `ail/hallucination_probes.py` is **untouched** — same architecture, same 6
  categories, same fact lists. The prior spec's work stands.
- The probe metric is still **computed, persisted, and displayed** per item (item
  drill-down, SME calibration export). It keeps its evidentiary value; it simply
  no longer inflates the score.
- `faithfulness` is unchanged.

### Disclosure

A fired probe is a material finding a reviewer must see, so it is surfaced the way
`safety_unverified` already is (JSON, PDF, REST API, console):

- `Scorecard.african_fabrication_detected: bool` (default `false`) — the
  scorecard-level disclosure.
- **Per-item evidence** comes from the probe's own persisted `MetricResult`, whose
  `reason` already names the triggering topic and marker. It is visible in the
  console item drill-down and the SME calibration export.

*Deliberately not plumbed into `failing_examples`:* that structure is
dimension-level and built in the engine with no item identity, so surfacing
item-level entries there would require threading a new engine parameter for
marginal gain over the evidence already persisted above.

### Verdict gating — DECIDED: proportional only (Option 1)

**Founder decision 2026-07-17: Option 1.** A fired probe applies the per-item hard
zero and raises the disclosure flag; it does **not** cap the verdict.

Rejected for now — *Option 2, verdict cap* (any detection forces e.g.
`Not-Ready`, analogous to the safety veto). Shipping a hard verdict gate on a
detector with **zero observed fires** would be gating on a completely untested
path, where a single substring false positive would be severe. Revisit once the
probe has fired in the wild and its real precision can be inspected.

## Impact (simulated on 89 real scorecards)

Prototyped by recomputing stored runs under the new rule (no production code
changed):

| | v1.1 (now) | **v1.2** |
|---|---|---|
| `hallucination_risk` avg | 92.2 | **85.2** |
| `hallucination_risk` range | **71.4 – 100** | **42.2 – 100** |
| Composite avg | 78.16 | **76.76** (−1.40) |
| Composites ≥ 80 (Deployment-Ready band) | 34 | **32** |

**The floor collapses from 71.4 → 42.2** — the dimension can finally discriminate.
The blast radius is deliberately small: the composite moves −1.40 on average and
only 2 of 34 scorecards leave the Deployment-Ready band, so this corrects a
structural flaw without mass-invalidating history.

*Caveat:* the sanity check reproduced the stored `hallucination_risk` on 64/89
runs. The 25 misses are runs from **before** the error-exclusion fix (`f78c799`),
where error-fallback `0.5`s still counted toward the mean — those legitimately
differ. Post-`f78c799` runs reconcile cleanly.

## Consequence to accept: HR now depends solely on DeepEval

With the probe demoted, `hallucination_risk` rests entirely on `faithfulness`,
which is the metric most exposed to Azure rate limits. If every `faithfulness`
call errors, the dimension has no scores and becomes **`not_evaluated`** —
renormalized out of the composite rather than scored — instead of coasting on the
probe's 0.60.

This is the correct behaviour under the "honesty about coverage" principle (we
could not measure hallucination, so we should not pretend to), and it is
well-mitigated in practice: the dedicated DeepEval semaphore (`547909d`) took a
full 12-pack run to **0 infra-errors in 1,380 metric results**, error fallbacks are
already excluded from scoring (`f78c799`), and thin evidence raises `low_coverage`
which caps the verdict to Conditional.

## Migration

- **Version bump:** `METHODOLOGY_VERSION` `"v1.1"` → `"v1.2"` in
  `scoring/engine.py`. Every new Scorecard is stamped `v1.2`.
- **Historical scorecards are FROZEN.** v1.0 and v1.1 scorecards are **not
  re-scored** and not back-filled — the same precedent set by the v1.1 bump. Each
  scorecard already carries its own `methodology_version`, so old results stay
  interpretable under the rules they were produced with. Any cross-version
  comparison must be version-aware (a v1.1 `hallucination_risk` is ~7 points
  higher than a v1.2 one for the same model, per the table above).
- **DB migration:** one Alembic migration adding
  `scorecards.african_fabrication_detected BOOLEAN NOT NULL DEFAULT false`,
  mirroring `e4f5a6b7c8d9` (`safety_unverified`). It applies to prod automatically
  via the `deploy-migrate` workflow on push to `master`.
- **Docs to update on implementation:** `METHODOLOGY_V1.md` §2.3 and the weight
  table; `docs/ENGINEERING_BIBLE_V1.html` §04/§05 (As-Built) and the artifact;
  `hitl/label_config.py` needs no change.
- **Re-baseline:** after shipping, re-run the 12-pack calibration set to establish
  a v1.2 baseline (the v1.1 baseline is run `0a90372d`).

## Error handling

- Probe: deterministic, no external dependencies, no error path (unchanged).
- `faithfulness`: existing behaviour — infra-error fallbacks are flagged
  `error=True`, excluded from the score/coverage aggregates, still persisted for
  visibility, and drive `metric_error_rates` → `low_coverage`.
- Dimension with zero non-error `faithfulness` scores → `not_evaluated`
  (item_count 0), renormalized out of the composite. Not scored `0.0`.

## Testing

1. No probe fires → `hallucination_risk == mean(faithfulness) * 100` (the common
   path; asserts the probe no longer contributes positive weight).
2. Probe fires on 1 of N items → that item contributes `0.0`; dimension drops
   proportionally, not to zero.
3. Probe fires on every item → `hallucination_risk == 0.0`.
4. `african_fabrication_detected` is `true` iff at least one probe fired, and the
   offending items appear in `failing_examples`.
5. All `faithfulness` results errored → dimension is `not_evaluated` (excluded and
   renormalized), **not** `0.0`.
6. Regression: `DEFAULT_METRIC_WEIGHTS` no longer contains a
   `african_hallucination_probe` entry, and `_validate_weights` still passes.
7. Golden-number check: recomputing run `0a90372d` under v1.2 yields the
   `hallucination_risk` and composite predicted by the prototype (91.6 / 88.10).

## Out of scope (separate items)

- **Bias & Fairness parity semantics** (a uniformly-poor model scores 100 because
  it fails *equally* across cohorts) — real, but a distinct design discussion.
- **Safety Robustness graded scoring** (binary metrics, avg 95.9, rarely
  discriminates) — lowest priority; the veto is the real mechanism there.
- **`chrf` weighting** — reviewed and deliberately left unweighted: it compares
  against a *behavioral spec*, not a reference answer, so it is a weak correctness
  signal. No change.
- **Expanding `AFRICAN_PROBES` fact lists** — still valid follow-up work from the
  prior spec, but it does not address this defect (a longer list of novel-term
  markers still fires almost never).
- **Re-scoring historical runs** — explicitly not done; see Migration.
