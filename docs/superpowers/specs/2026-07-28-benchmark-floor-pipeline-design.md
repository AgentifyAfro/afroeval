# Benchmark Coverage-Floor Pipeline — Design

**Date:** 2026-07-28
**Status:** Approved (design), pending implementation plan
**Author:** Dan Haile + Claude

## Problem

Eleven of the twelve benchmark packs sit below the 10-scored-item coverage floor
(`MIN_ITEMS_PER_DIMENSION = 10`). Amharic (`community_health_am_v1.2.0`, 23 scored)
is the only pack that has been carried through the authoring → validation → promotion
loop. Each remaining pack needs only +1 to +6 scored items to clear the floor:

| Pack | Lang | Scored now | To hit 10 |
|---|---|---|---|
| `safety_mixed` | mixed/yo | 4 | +6 |
| `customer_service_yo` | yo | 7 | +3 |
| `mobile_money_sw` | sw | 7 | +3 |
| `agriculture_ha` | ha | 8 | +2 |
| `agriculture_om` | om | 8 | +2 |
| `code_switching_mixed` | sheng | 8 | +2 |
| `cross_border_trade_ha` | ha | 8 | +2 |
| `urban_digital_sheng` | sheng | 8 | +2 |
| `customer_service_en` | en | 9 | +1 |
| `public_services_zu` | zu | 9 | +1 |
| `remittance_so` | so | 9 | +1 |

### Key finding: draft supply is not the constraint

Label Studio **project 9** ("AfroEval — SME Item Authoring v2 (2026-07-19)") already
holds **162 staged draft candidates** across all languages — 150 of them un-authored.
Only the 12 Amharic drafts have been authored. Every language has 12–29 drafts already
queued (there is even a 10th language, Igbo, staged with no pack yet).

The bottleneck is therefore **SME authoring throughput**, which the founder is
addressing by hiring. We do **not** generate or consolidate more drafts. We build the
machinery that turns the existing backlog into validated pack items as authoring lands.

## Goal

A **simple, flexible, per-language** pipeline that converts staged drafts into
floor-clearing validated pack items — with no lockstep ordering. Each tool is scoped to
one pack and is safe to re-run at any time; languages progress independently and in
parallel. Plus a lean dry-run harness so the pipeline is de-risked before the first new
hire authors anything.

### Non-goals

- No new draft generation or Label Studio consolidation.
- No unified "one command does everything" driver — existing per-step scripts stay.
- No rigid author→validate→promote→repeat sequence.
- No auto-flip of the console catalog.
- No new Igbo pack (out of scope; Igbo drafts remain staged).

## Core principle: per-language, idempotent, pick-up-what's-ready

Every tool targets **one pack** and is **re-runnable anytime**. Nothing waits on a
global barrier. You run a tool whenever *that* language has produced something new.
`vNext` is a **mutable working file while being built**, frozen only at catalog flip.

## The flow (each step re-runnable, order-independent across languages)

1. **Authoring lands for pack X** (any quantity, any time) →
   `promote_pack --pack X` **appends** the newly-authored, staged items to a working
   `X_vNext.jsonl`. Idempotent: only items not already present are added, so partial
   batches simply accumulate. Released versions are never modified.
2. **Validators rate some of X's items** → `validation_writeback` stamps
   `X_vNext` (content-hash keyed): already-validated items keep their stamps, new items
   start pending. Partial validation is expected and fine.
3. **`coverage_report`** shows each pack's live status — scored count, floor gap,
   validated vs pending — and flags **"ready to flip"** when a pack clears 10 scored
   items *and* those items are validated.
4. **Flip when ready** → explicit, per-pack, one-line catalog edit. The working version
   becomes released and is thereafter immutable.

## Components

Reuses every existing script unchanged. Four new artifacts:

### 1. `scripts/coverage_report.py` — read-only tracker

- For each pack: scored-item count, gap to the 10-floor, Tier-1 / Tier-2 / pending
  breakdown, and a **"ready to flip"** flag (clears 10 *and* validated).
- `--live` (optional): also query project 9 for authored-vs-pending counts per language,
  so you can see the upstream authoring queue.
- Pure read. No writes, no side effects. This is the dashboard watched during the
  hiring/authoring ramp.

### 2. `scripts/promote_pack.py` — idempotent per-pack promotion helper

- Input: `--pack <name>` and the staged authored candidates in
  `output/authored_candidates/` (produced by the existing `import_authored_items.py`).
- Determines the pack's current released version and the working `vNext`
  (default: bump minor; overridable via flag).
- **Appends** staged authored items for that pack's language/domain into `X_vNext.jsonl`,
  keyed on item id / `stable_item_uuid` so re-runs never duplicate. New items carry
  `validation_count = 0`, `irr_score = null` (pending) until writeback stamps them.
- Guardrails:
  - Never edits a **released** version in place (immutability).
  - Refuses to write into a version already flipped to the catalog (bump instead).
  - `--dry-run` is the default; `--apply` writes.
  - Prints the projected new floor (scored count after append).
- Does **not** stamp validation and does **not** flip the catalog.

### 3. `scripts/dry_run_pipeline.py` + fixture tests — the confidence harness

- One lean, runnable end-to-end check: build a synthetic pack `vCurrent` + synthetic
  staged authored items + synthetic ratings (κ / factual-dispute controllable), then
  drive the **real** promote → `compute_item_results` → `apply_results` code against a
  **temp packs-dir**. Asserts: floor cleared, Tier-1 counts correct, adjudication raised
  on a factual dispute / sub-floor κ.
- Fixture-based unit tests for the two Label Studio **parse seams**
  (`import_authored_items` annotation→row, `validation_import_ratings` annotation→rating),
  **including a non-Latin-script case** so the Amharic citation-regex class of bug cannot
  regress.
- No prod DB, no live Label Studio, no fake-server scaffolding. Synthetic data through
  real deterministic code.

### 4. `docs/FLOOR_RUNBOOK.md` — short, flexible checklist

- The per-language step list as a **checklist, not a rigid sequence** — run each step
  whenever that language has new output.
- **Roster-per-language prerequisite:** new hires must be added to
  `scripts/data/validator_roster.json` with their `languages` before their validation
  can count (`assign_validators` requires two distinct non-author validators who speak
  the item's language).
- **Scope-to-`vNext` guardrail:** writeback stamps every pack file that shares an item
  id, so promotion/writeback for a language must be scoped to the target working version
  only (the multi-version stamping trap hit during the Amharic run — v1.0.0/v1.1.0 were
  reverted after each writeback).

## Data flow

```
Label Studio project 9 (staged drafts)
        │  SME authors in-language (new hires)
        ▼
import_authored_items.py ──► output/authored_candidates/  (staging, existing)
        │
        ▼
promote_pack.py  ──►  benchmarks/packs/X_vNext.jsonl   (append, idempotent, mutable)
        │
        ├─ seed_packs_to_db.py            (existing)
        ├─ validation_export_tasks.py     (existing, --validators pins the pair)
        ├─ validation_import_ratings.py   (existing)  ──► item_validations (DB)
        ├─ validation_writeback.py        (existing)  ──► stamps X_vNext
        └─ validation_adjudicate.py       (existing)  disputes
        │
        ▼
coverage_report.py  ──►  "ready to flip" when floor cleared + validated
        │
        ▼
manual one-line PACK_CATALOG edit  ──►  X_vNext released (now immutable)
```

## Error handling & guardrails

- **Immutability:** `promote_pack` refuses to modify released/catalog-flipped versions.
  Released pack files are treated as read-only (project CLAUDE.md rule).
- **Idempotency:** promotion keys on item id / `stable_item_uuid`; re-runs are no-ops for
  already-present items. Writeback is already idempotent (content-hash keyed, no no-op
  rewrites).
- **Partial progress is valid:** unvalidated items simply stay pending; a pack short of
  the floor simply is not "ready to flip." No step assumes a language is "done."
- **Scope-to-version:** every write is scoped to a single target working file; the runbook
  documents verifying `git diff` touches only `X_vNext.jsonl` before committing.
- **Founder sign-off unchanged:** Tier-2 tagging and catalog flips remain deliberate human
  steps, exactly as in the Amharic run.

## Testing

- `dry_run_pipeline.py` end-to-end assertion run (synthetic, temp dir).
- Parse-seam unit tests with fixtures, including non-Latin script.
- `promote_pack` unit tests: idempotent re-run, immutability refusal, floor projection,
  version bump.
- `coverage_report` unit test: floor gap + "ready to flip" logic on a fixture pack set.
- Full existing suite stays green (`pytest tests/ -q`) + `ruff`.

## Open items (deferred, not blocking)

- Igbo pack creation (drafts staged, no pack) — separate future effort.
- Deepening any pack toward ~20 items/pack for robustness beyond the floor — future.
