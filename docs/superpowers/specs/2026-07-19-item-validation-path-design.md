# Item Validation Path — Design Spec

**Status:** Draft, pending founder sign-off (2026-07-19)
**Owner decisions locked:** IRR floor **0.70**; kappa is **per rater-pair, per batch**; **full build (all 9 gaps)**

---

## Problem

Tier 1 publication requires `validation_count >= 2` and `irr_score >= floor`. **No item in the
corpus has ever met it.** Across 147 items in 13 packs:

| `validation_count` | items |
|---|---|
| `null` | 121 |
| `0` | 22 |
| `1` (Tier 2, all authored by the founder) | 4 |
| `>= 2` | **0** |

`irr_score` is `null` on all 147. No code anywhere computes any agreement statistic — a
repo-wide search for kappa/krippendorff/agreement returns zero hits outside docstrings.
**Tier 1 exists on paper only.**

This surfaced when `draft-ch-am-104` could not be promoted: `community_health_am` is at
36.4% Tier 2 and one more single-expert item would breach the 40% cap. The cap assumes the
remaining 60% is Tier 1. It is not — it is unvalidated. **The cap is currently protecting
items nobody has signed off on, against items that carry the most evidence in the corpus.**

Building the validation path is the honest fix: make the 60% mean something.

---

## Adjacent finding, in scope for the full build

`ResponseReview` rows — the output of the SME *response calibration* loop — are written by
`scripts/hitl_import_reviews.py` and **read by nothing**. No scoring, reporting, or console
code consumes them. SME calibration effort currently terminates at the database. This is the
same failure mode as Tier 1: a workflow that appears complete and produces nothing
downstream. Gap 9 addresses it.

---

## Locked design decisions

### D1 — IRR floor is 0.70

Three documents said 0.70 (`CULTURAL_RUBRIC_V1.md:181`, `SME_ROLE_PACKS.md`,
`GOLD_TASK_DESIGN.md:58`); one said 0.60 (`BENCHMARK_ITEM_SCHEMA.md:57`), and the code
implemented 0.60. **0.70 governs.** It is also the conventional "substantial agreement"
threshold for Cohen's kappa, which is easier to defend externally. No published item is
affected — none has an `irr_score` to invalidate.

Changes: `BENCHMARK_ITEM_SCHEMA.md:57` and `scripts/import_authored_items.py:51`.

### D2 — `irr_score` is a per-pair, per-batch statistic

Cohen's kappa requires multiple items rated by the same two raters; it is undefined for a
single item. `irr_score` is therefore computed **once per (validator_A, validator_B, batch)**
across every item that pair both rated, and that value is written onto each item in the
batch.

**`irr_score` means: "the agreement level of the pair who validated this item, measured
across their shared batch."** It is a property of the rating process, not of the item. This
must be stated in `BENCHMARK_ITEM_SCHEMA.md` — leaving it implicit invites the reading that
one item was somehow independently reliable.

Consequence: a pair must share a **minimum batch of 10 items** before kappa is meaningful.
Below that, `irr_score` stays `null` and the item stays unpublishable under Tier 1 — it is
not estimated, extrapolated, or borrowed from another pair.

### D3 — kappa is computed on the cultural-appropriateness 1–5 scale, quadratic-weighted

The validator instrument (`SME_ROLE_PACKS.md:77-97`) has four parts. Kappa is computed on
**cultural appropriateness (1–5 ordinal)** using **quadratic-weighted** Cohen's kappa, because:

- it is the richest scale in the instrument, so it carries the most signal;
- `CULTURAL_RUBRIC_V1.md:181` sets the 0.70 target against this rubric specifically;
- unweighted kappa on an ordinal scale treats "4 vs 5" as badly as "1 vs 5", which is wrong.

**Factual accuracy is a separate hard gate, not part of kappa.** Two validators disagreeing
on whether an item is factually correct is not a reliability problem to be averaged — it is
a blocking defect. If their factual verdicts differ, the item goes to adjudication
regardless of kappa.

### D4 — the pack JSONL is the source of truth; the DB is a mirror that must be fixed

`scripts/seed_packs_to_db.py:90-101` does not copy `validation_count` or `irr_score`, so both
DB columns are structurally dead — every row carries the defaults. Validation state lives in
the pack files.

The seeder must be fixed to carry both fields, so the DB stops silently disagreeing with the
packs. But **the pack file remains authoritative**: writeback targets the JSONL, and the DB
is re-seeded from it.

### D5 — validation records survive pack versions, but not content edits

`stable_item_uuid` derives from the item string id alone, so `ch-am-001` has the same UUID in
`v1.0.0` and `v1.1.0`. That is desirable — ratings carry forward across a version bump.

It is also a hazard: an item's **text can change** under a stable UUID, and a validation
record would then attach to content nobody rated. This is live today, not hypothetical —
both `community_health_am` versions exist, and `seed_packs_to_db.py:89` silently skips
re-seeding an item whose UUID already exists.

**Every validation row stores `item_content_hash`** — sha256 of `prompt || expected_behavior`
at rating time. A validation whose hash no longer matches the item is **stale**: it does not
count toward `validation_count`, and the item drops out of Tier 1 until re-validated. Silent
staleness is the failure this prevents.

---

## The nine gaps and what closes each

| # | Gap | Resolution |
|---|---|---|
| 1 | No storage for per-item, per-rater ratings | New `item_validations` table (below). `ResponseReview` is FK-bound to `model_responses` and carries the wrong instrument — it cannot be reused honestly. |
| 2 | Instrument exists only as prose | `build_validation_label_config()` in `hitl/label_config.py` implementing `SME_ROLE_PACKS.md:77-97`, plus `VALIDATION_PROJECT_TITLE`. |
| 3 | No export/import, no assignment | `scripts/validation_export_tasks.py` / `validation_import_ratings.py`. Assignment: 2 distinct validators per item, **never the item's author** (`SME_ROLE_PACKS.md:76`). |
| 4 | No IRR computation | `validation/irr.py` — quadratic-weighted Cohen's kappa per pair per batch (D2, D3). |
| 5 | No writeback | Writeback to pack JSONL + fix `seed_packs_to_db.py` to carry the fields (D4). |
| 6 | No promotion step | `scripts/promote_candidates.py` — consumes staged candidates + validation records, strips `_`-prefixed fields, applies the Tier 2 tag on founder sign-off, enforces the 40% cap via the existing `tier2_share`, writes a versioned pack. |
| 7 | No adjudication path | Third-rater queue; `adjudicated_score` + `adjudication_rationale` + `adjudicated_by` on the item. Triggered by kappa < 0.70, factual-verdict mismatch (D3), or cultural disagreement > 1 point. |
| 8 | No gold/drift monitoring | Gold items seeded into the validation queue; validator's cultural score compared to `cultural_rubric_gold_score`; per-SME agreement tracked. **Blocked on data — see Known blocker.** |
| 9 | `ResponseReview` read by nothing | A calibration-agreement report comparing SME dimension scores against automated scores per run, surfaced in the console. Closes the loop that currently dead-ends. |

### `item_validations` table

```
id                  uuid   PK
item_id             uuid   FK benchmark_items.id, indexed
item_content_hash   str    sha256(prompt || expected_behavior) at rating time (D5)
validator_id        str    pseudonymised, as sme_author_id already is
batch_id            str    the (pair, batch) grouping kappa is computed over (D2)

factual_accuracy    str    'yes' | 'no' | 'needs_revision'    hard gate (D3)
language_quality    int    1-3
cultural_score      int    1-5                                 kappa input (D3)
schema_compliant    bool   the 4-item checklist, collapsed
justification       str    one sentence, required
verdict             str    'validated' | 'needs_revision'

created_at          datetime
UNIQUE (item_id, validator_id)   -- one rating per person per item, enforced in the DB
```

The unique constraint matters: `ResponseReview` has no such constraint and relies on
in-memory Python dedupe (`hitl_import_reviews.py:66`), which is why re-running an import can
double-count. Do not repeat that.

---

## Non-negotiable constraints

- **A validator may never rate an item they authored** (`SME_ROLE_PACKS.md:76`). Enforced at
  assignment AND re-checked at import — an assignment bug must not silently produce a
  self-validated item.
- **`validation_count` counts distinct people.** Never incremented for one person rating
  twice, and never to clear a gate (`BENCHMARK_ITEM_SCHEMA.md:56`).
- **`irr_score` is never estimated or backfilled.** `null` when `validation_count < 2` or
  when the pair's shared batch is under 10 items.
- **Tier 2 rules are unchanged by this work.** This build does not relax the single-expert
  evidence bar; it makes the Tier 1 alternative reachable.
- **`benchmarks/packs/*.jsonl` are SME-validated data.** Only the promotion script writes
  them, and only on explicit founder sign-off.
- **Gold items require Tier 1, no exception** (`BENCHMARK_ITEM_SCHEMA.md:130`).

---

## Known blocker — gap 8 lands inert

`cultural_rubric_gold_score` is **unpopulated on all 31 gold items** and read by zero code.
The drift machinery can be built, but it cannot function until an SME with the relevant
language and domain assigns reference scores — largely the founder. This is called out here
so the build is not mistaken for a working capability on delivery. Gap 8 ships as
machinery + a backfill checklist.

## Dependency

`cohen_kappa_score` currently works only **transitively** — `scikit-learn` is pulled in by
`fairlearn` and is not declared in `requirements.txt`. Add it explicitly. If the founder
prefers zero new declared dependencies, weighted kappa is ~15 lines of arithmetic and can be
implemented directly; the tradeoff is owning the implementation and its tests.

## Out of scope

- Backfilling validation onto the 121 unvalidated legacy items. They stay as they are until
  someone rates them; this build makes that possible, it does not do it.
- Re-scoring or re-issuing any historical scorecard.
- Changing the 40% Tier 2 cap. If the cap's denominator should compare against *validated*
  items rather than all items, that is a separate methodology decision.
