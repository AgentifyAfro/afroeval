# Design — LaBSE as a judge-independent signal for Language Performance

**Date:** 2026-08-01
**Status:** Backlog spec — decision-support, NOT approved for build
**Author:** Dan Haile (with Claude)
**Decision owner:** Dan

> This is a **backlog** document. Its job is to let Dan decide whether the benefit
> outweighs the cost, then — only if greenlit — serve as the basis for an
> implementation plan. It intentionally does not schedule work.

---

## The core problem this solves

**Language Performance currently has no judge-independent signal at all.**

Every scored metric in the dimension is an LLM judge:

| Metric | Weight | Backed by |
|---|---|---|
| `semantic_similarity` | 50% | DeepEval AnswerRelevancy (LLM judge) |
| `answer_completeness` | 30% | DeepEval GEval (LLM judge) |
| `fluency` | 20% | Custom LLM judge |

(`scoring/engine.py` `DEFAULT_METRIC_WEIGHTS["language_performance"]`)

LLM judges are precisely where the African-language fairness risk concentrates — the
same content-filter false-positives, dialect bias, and blind spots that the LLM-judge
error-plumbing work (shipped 2026-08-01, `95ac943`) exists to expose. So the one
dimension most exposed to judge bias is scored **entirely** by the thing that carries
the bias, with nothing to cross-check it.

**LaBSE gives that dimension a second opinion the judges cannot corrupt.** It is a
**local, deterministic, API-free, bias-resistant** similarity signal:

- **Cannot be rate-limited** — no API, runs in-process.
- **Cannot be content-filtered** — no Azure/OpenAI filter sits between it and the
  African-language text; it embeds the text directly.
- **Does not inherit the judge's blind spots** — it is a different model family
  (sentence embeddings, not an instruction-tuned LLM), trained for a different task,
  so its failure modes are uncorrelated with the judges'. When it and the judges
  **agree**, confidence rises; when they **sharply disagree** on an
  African-language item, that disagreement is itself a high-value signal that
  something is off with the judge on exactly the content AfroEval exists to evaluate
  fairly.

This is the whole thesis. Everything below is about capturing that value at a cost
proportionate to what it's proven to be worth.

## Why not the current `multilingual_similarity`

The metric slot already exists (`MultilingualSimilarityEvaluator`,
`evaluators/language_performance.py`) but is backed by
`paraphrase-multilingual-MiniLM-L12-v2`, whose embedding quality for **low-resource**
African languages (Yoruba, Igbo, Hausa, Oromo, Amharic) is weak and noisy. That
noise is why it was left **weight-0** (diagnostic only) and, per Dan's 2026-08-01
decision, left uninstalled (records `error=unavailable`, no score impact). A signal
you don't trust enough to weight is not a second opinion. **LaBSE** (Language-Agnostic
BERT Sentence Embedding, 109 languages, purpose-built for cross-lingual similarity
with materially stronger low-resource coverage) is the model that makes the slot
trustworthy.

## Chosen approach — phased (flag now → weight later)

Decided 2026-08-01. Rationale: capture the second-opinion value immediately at near-zero
methodology cost, and defer the expensive, hard-to-reverse methodology change until the
data proves LaBSE tracks SME judgment.

### Phase 1 — judge-divergence flag (unscored, cheap)

LaBSE replaces MiniLM as the backing model for the `multilingual_similarity` slot and
runs on every Language Performance item, but **stays weight-0** — it does not move any
score.

Its job in Phase 1: when the LaBSE similarity **diverges sharply** from the item's
judge-derived Language Performance score (beyond a configurable threshold), raise a
**`judge_divergence` flag** on the item and a per-run divergence count in the
scorecard. This is a QA / trust signal for reviewers, not a score mover.

**Surfacing — decided 2026-08-01: persist the flag, so it appears in the downloadable
scorecard report, not just the live console.** Dan wants divergence visible in the
exported PDF a client would see. The console view recomputes from DB rows on the fly,
but the PDF report (`reporting/generator.py`) renders from **stored** rows — so a
console-only recompute would show on screen but be absent from the PDF. Persisting the
per-item flag + per-run count means one stored value feeds **both** the console
scorecard and the PDF report, and makes divergence auditable per-run (same principle as
the `error`/`error_cause` columns from the error-plumbing work). Cost: a small schema
addition + migration (see cost table) — accepted deliberately for report inclusion.

Because scores are untouched:

- **No methodology version bump.** No rebaseline. No SME sign-off gate. (The persisted
  field is unscored — it never enters `DEFAULT_METRIC_WEIGHTS` or the composite.)
- Still reversible in scoring terms — if the flag proves noisy, stop populating/showing
  it with no scoring fallout; the column is inert data.
- Every run silently accumulates the paired (LaBSE score, judge score) data that
  Phase 2 needs for calibration.

### Phase 2 — promote to a scored weight (later, only if earned)

Once enough paired data exists to show LaBSE similarity **correlates with SME
judgment** on African languages (via the existing SME Calibration path), promote it to
a real weight in `DEFAULT_METRIC_WEIGHTS["language_performance"]` — e.g. ~15–20%,
reducing the judge metrics' share. This is the methodology change, paid only when
justified:

- Methodology version bump (v1.4 → v1.5) with SME sign-off.
- Rebaseline every pack × language (weights change → composites shift).
- The calibration evidence gathered in Phase 1 is the sign-off artifact.

Phase 2 is explicitly **out of scope for the first build** — it gets its own spec when
the Phase 1 data is in.

## Pros / cons / cost trade-offs

The heart of the decision. Split by phase so the cheap part and the expensive part are
never conflated.

### Phase 1 (flag)

**Pros**
- Delivers the judge-independent second opinion **immediately**.
- **No scoring/methodology impact** → no rebaseline, no SME gate, fully reversible.
- Marginal cost per item is **~$0** (local embedding) and **~tens of ms** — negligible
  beside a single LLM-judge call (hundreds of ms + API $ + rate limits).
- Turns the today-wasted `multilingual_similarity` slot into a working QA signal.
- Directly strengthens the product thesis ("defensible down to the individual test
  case") by flagging judge calls that a second, un-biasable model disputes.

**Cons / costs**
- **~1.8 GB model** (LaBSE) must ship into the **eval environment** (where runs
  execute out-of-band — *not* the Streamlit console, so the console memory ceiling is
  not touched). This is the main real cost: env provisioning + cold-load time.
- Adds `sentence-transformers` + `torch` to the eval env's dependency footprint.
- **Small schema + migration** — a per-item flag and a per-run `Scorecard` count column,
  so divergence flows to the **downloadable PDF report** (Dan's requirement), not just
  the live console. Unscored/inert, so no methodology or rebaseline impact — but it is a
  DB change (Alembic migration + prod apply via the deploy-migrate workflow), unlike a
  pure console-only recompute.
- LaBSE is slower to load and embed than MiniLM (still trivial vs judge latency).
- A **divergence threshold** must be picked; too tight → noise, too loose → misses.
  Starts as a configurable knob, tuned on real data.
- **Honest validation risk:** LaBSE's sweet spot is *cross-lingual* similarity
  (matching translations across languages). Here both response and reference are
  *in the same* African language, so we rely on its in-language embedding quality —
  strong and far better than MiniLM for low-resource languages, but this assumption
  must be checked against SME judgment before trusting it (which is exactly what
  Phase 1 gathers data for).

### Phase 2 (weight) — for awareness, not decided here

**Pros**
- Directly hardens the composite with a bias-resistant signal — the judges can no
  longer solely determine the most-exposed dimension.

**Cons / costs**
- Full methodology bump: rebaseline **every** pack × language, SME sign-off.
- Requires the Phase 1 calibration evidence first; premature promotion of a
  mis-calibrated embedding metric would *inject* error rather than catch it.

### Cost summary

| Cost | Phase 1 | Phase 2 |
|---|---|---|
| Per-item $ | ~$0 (local) | ~$0 (local) |
| Per-item latency | ~tens of ms | ~tens of ms |
| Eval-env footprint | +~1.8 GB model, +torch | (already present) |
| Console impact | none (runs out-of-band) | none |
| Schema / migration | **small** (per-item flag + `Scorecard` count col, so it reaches the PDF report) | (reuses Phase 1) |
| Report (PDF) inclusion | ✅ yes (persisted) | ✅ yes |
| Methodology / rebaseline | **none** (flag is unscored) | full rebaseline + SME sign-off |
| Reversibility | easy (stop populating; column inert) | hard (versioned methodology) |

## Technical design (Phase 1)

- **Model:** swap `_get_multilingual_model()` in `evaluators/language_performance.py`
  from `paraphrase-multilingual-MiniLM-L12-v2` to `sentence-transformers/LaBSE`.
  Same encode-two-texts → cosine-similarity mechanic; the evaluator's error plumbing
  (`error=unavailable` when the dep/model is absent) carries over unchanged.
- **Still weight-0:** no change to `DEFAULT_METRIC_WEIGHTS`. The metric keeps
  persisting a `MetricResult` row (now LaBSE-backed) — already excluded from scoring
  and reconstruction by the error-plumbing read paths.
- **Divergence flag (persisted):** compute per-item `|laBSE_similarity*100 −
  semantic_similarity*100|` — compared against the judge's **`semantic_similarity`**
  metric specifically (decided 2026-08-01), NOT the full LP dimension score. Both
  measure "how close is the answer to the reference," so the flag isolates a genuine
  judge-vs-independent-model disagreement on that one question; comparing to the full
  dimension would let fluency/completeness gaps (which LaBSE doesn't measure) muddy the
  signal. When the delta exceeds a configurable threshold, set a **persisted**
  `judge_divergence` marker. Items where `semantic_similarity` errored/absent or LaBSE
  is `unavailable` produce no flag (nothing to compare). Persistence so it reaches the PDF report:
  the per-item flag on the `MetricResult`/item (a boolean/float column or a typed
  `extra` key) plus a per-run divergence count on the `Scorecard` row (new column →
  Alembic migration). Both `render_run_scorecard` (console) and
  `reporting/generator.py` (PDF) read the stored value, so console and report never
  drift. Plumb it through the dispatcher persist path the same way `error`/`error_cause`
  were.
- **Deps:** `sentence-transformers` + `torch` provisioned in the eval env only.
  Model cached on disk after first load (thread-safe loader already exists).

## Open questions (resolve during planning, not now)

1. ~~**Divergence surfacing** — persisted field vs console-only recompute.~~
   **RESOLVED 2026-08-01: persist it.** Dan wants divergence in the downloadable PDF
   report, and the PDF renders from stored rows — so the flag is persisted (per-item +
   per-run `Scorecard` count) and feeds both console and report from one value. Exact
   column shape (dedicated column vs typed `extra` key) is a plan-time detail.
2. **Threshold default** — starting value for "sharp" divergence; pick provisionally,
   tune on real data.
3. **Model choice sanity check** — confirm LaBSE beats the alternatives (e.g. a newer
   multilingual sentence encoder) on *your* languages before committing; LaBSE is the
   anchor per its known low-resource strength, not a foregone conclusion.
4. **In-language validation** — a small SME-labelled sample to confirm LaBSE
   similarity tracks human judgment in-language before anyone discusses Phase 2.

## Non-goals

- **Phase 2 (scored weight)** — separate spec, gated on Phase 1 calibration data.
- Re-examining `chrF++` (the other weight-0 language metric) — out of scope; this is
  about the judge-independent signal specifically.
- Any change to the judge metrics themselves, or to the judge model (staying on
  `gpt-4.1-mini`, decided separately).
- Backfilling divergence flags onto historical runs.

## Related

- `evaluators/language_performance.py` — the metric slot + model loader.
- `scoring/engine.py` `DEFAULT_METRIC_WEIGHTS`, `METHODOLOGY_VERSION` (v1.4).
- LLM-judge error plumbing (`95ac943`) — the read-path exclusion + error model this
  metric already rides on; and the reason a judge-independent signal matters.
- SME Calibration console view — the Phase 2 evidence path.
