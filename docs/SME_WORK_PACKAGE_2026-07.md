# AfroEval — SME Work Package (July 2026)

**For:** contracted SMEs (item authoring, response calibration, gold reference scoring)
**Prepared:** 2026-07-19
**Status:** ready to delegate. Phase 3 (validation) is blocked on a build — see Sequencing.

---

## 1. Why this package exists

The corpus is thinner than its headline numbers suggest, and three separate vocabularies for
`cohort` are in circulation. Both problems are invisible until you are mid-way through a
calibration cycle. This document resolves them **before** SMEs are contracted, so nobody
authors items against a standard that will be rejected later.

### The corpus, measured

136 active items — but **only 96 are scored**. Gold (28) and held-out (12) items are never
scored, so they do not count toward coverage.

**Eleven of twelve packs sit below the `MIN_ITEMS_PER_DIMENSION = 10` floor on scored items.**
This is the direct cause of the recurring `low_coverage` confidence flag.

| pack | language | scored now | needed to reach 20 |
|---|---|---|---|
| `safety_mixed_v1.0.0` | yo | **4** | **16** |
| `customer_service_yo_v1.0.0` | yo | 7 | 13 |
| `mobile_money_sw_v1.0.0` | sw | 7 | 13 |
| `agriculture_ha_v1.0.0` | ha | 8 | 12 |
| `agriculture_om_v1.0.0` | om | 8 | 12 |
| `code_switching_mixed_v1.0.0` | sheng | 8 | 12 |
| `cross_border_trade_ha_v1.0.0` | ha | 8 | 12 |
| `urban_digital_sheng_v1.0.0` | sheng | 8 | 12 |
| `customer_service_en_v1.0.0` | en | 9 | 11 |
| `public_services_zu_v1.0.0` | zu | 9 | 11 |
| `remittance_so_v1.0.0` | so | 9 | 11 |
| `community_health_am_v1.1.0` | am | 11 | 9 |
| | | | **144 total** |

**`safety_mixed` is the priority.** It holds 4 scored items, and `safety_robustness` is the
one dimension carrying a **veto** — it can cap a verdict on its own. A veto resting on four
items is the most fragile thing in the corpus.

### Why the target is 20 and not 12

Sizing against the coverage floor (10, plus a couple spare) is what produces a corpus that
degrades back into `low_coverage` the first time anything goes wrong. Four independent
constraints converge on 20:

| target | 1 item moves a group's rate by | margin over the floor | validator pair-batches |
|---|---|---|---|
| 12 | 8.3% | 2 | 1, barely |
| **20** | **5.0%** | **10** | **2** |
| 24 | 4.2% | 14 | 2 |

1. **Resolution.** At 20 items a single item is 5% of a group's selection rate. At 12 it is
   8.3%, so one flaky item visibly moves `bias_fairness` — reintroducing through the data the
   volatility v1.4 removed from the code.
2. **Failure margin.** Ten items of headroom. Items are occasionally lost mid-run to content
   filters (a Zulu item was blocked as a false positive in a recent run); at 12, one filter
   loss plus one bad item puts the pack back under the floor.
3. **Validation feasibility.** A validator pair needs ≥10 shared items before kappa means
   anything. At 20 a pack supports two full pair-batches; at 12 it supports one, with nothing
   spare.
4. **Tier 2 cap relief.** `community_health_am` at 20 scored puts its 4 single-expert items at
   20% rather than 36.4%, so the 40% cap stops blocking new single-expert items structurally
   rather than case by case.

---

## 2. RESOLVED — the cohort vocabulary

Three vocabularies were in circulation. **Founder decision (2026-07-19): the packs' three
real cohorts govern.**

### Author only these three values

| `cohort` | meaning |
|---|---|
| `formal` | formal-economy, banked, institutional context |
| `informal_economy` | informal-economy worker or trader, urban or peri-urban |
| `informal_rural` | rural, smallholder, distance-from-services context |

### Everything else becomes a tag, not a cohort

`low_literacy`, `feature_phone`, `urban`, `rural`, `elderly`, and similar distinctions are
still valuable and still recorded — as **tags**. They stay searchable and reportable.

**Why this matters mechanically.** `bias_fairness` (15% of the composite) computes a
disparate-impact ratio across cohort groups, and any group with fewer than 5 items is
excluded as too volatile. Introducing `low_literacy`, `feature_phone`, and `informal_urban`
as cohorts would create three new groups at sizes 6, 1 and 5 — small enough to swing the
fairness score hard, or be silently excluded. Tags carry the same information without
destabilising the metric.

`agent` is a legacy label appearing only on non-scored items. Do not author new items with it.

---

## 3. Phase 1 — Item authoring (48 items)

### Per-pack targets

Author to the counts in the table in §1. Priority order: `safety_mixed` (8) first, then
`customer_service_yo` and `mobile_money_sw` (5 each), then the rest.

### Cohort mix within each pack

Most packs are currently near-monocultural on cohort — `agriculture_ha` is 8/8
`informal_economy`, `customer_service_en` is 9/9 `formal`. A disparity metric cannot see a
gap that isn't represented.

**Author roughly 60% `informal_economy`, 25% `formal`, 15% `informal_rural`** across the new
items, adjusting per pack so no pack ends up single-cohort.

**`informal_rural` is the specific shortfall**: 4 scored items corpus-wide, below the 5-item
floor, so it is currently excluded from the fairness calculation entirely. **Target 8.**
Rural items are most natural in `community_health_am`, `agriculture_ha`, `agriculture_om`,
and `cross_border_trade_ha`.

### What makes a good item

Each item must be answerable and gradeable. The `expected_behavior` is the ground truth an
automated judge scores against, so it carries as much weight as the prompt.

- **Test something a model can plausibly get wrong** — especially Africa-specific
  institutional facts (agency names, tariffs, schedules, operator rules, referral pathways).
  Generic questions that any model answers correctly measure nothing.
- **`expected_behavior` must be verifiable, not aspirational.** Write what a correct answer
  contains, not what a good answer feels like.
- **Never invent a fact in `expected_behavior`.** An item whose own ground truth contains a
  fabricated detail is worse than no item — it trains the benchmark to reward fabrication.
  If you cannot verify a schedule, price, or rule, write the item so the correct behaviour is
  to defer to a named authority rather than to state the number.
- **Provenance must cite a checkable source** — a document with a **year, edition, version, or
  URL**. "Ministry of Health website" names a publisher, not a source. This is enforced
  automatically; items without it will not pass the publication gate.

### Where to work

Label Studio → **`AfroEval — SME Item Authoring`** (project id 8). Each task carries an
English draft scaffold: scenario, prompt intent, expected-behaviour sketch, provenance hint.
**The scaffold is a starting point, not a translation exercise** — write the real prompt and
expected behaviour in the target language, in the register a real user would use.

---

## 4. Phase 2 — Response calibration

Label Studio → **`AfroEval — SME Calibration`**. SMEs rate model responses on the six
scorecard dimensions (0–10 each, with a rationale).

**Known limitation, being fixed:** calibration ratings are currently stored and not yet
consumed by any report. The build that closes this loop is specified
(`docs/superpowers/specs/2026-07-19-item-validation-path-design.md`, gap 9). Calibration work
done now is not wasted — it lands in the database and the report reads historical rows — but
be aware the feedback loop is not yet visible in the console.

---

## 5. Phase 3 — Gold reference scoring (28 items) — NEEDS AN SME PER LANGUAGE

28 gold items exist. **All 28 have `cultural_rubric_gold_score` unpopulated**, and no code
reads the field. Gold items are meant to be hidden calibration anchors that measure whether a
reviewer is drifting — without reference scores, they do nothing at all.

| language | gold items needing a reference score |
|---|---|
| sw | 8 |
| ha | 4 |
| yo | 4 |
| am | 4 |
| sheng | 3 |
| om | 2 |
| en | 1 |
| zu | 1 |
| so | 1 |

Each needs a cultural-appropriateness score (1–5, per `CULTURAL_RUBRIC_V1.md`) from an SME
with native/fluent command of the language **and** domain familiarity. This is the
prerequisite for any reviewer-drift monitoring.

---

## 6. Phase 4 — Item validation (BLOCKED — do not contract for this yet)

Tier 1 publication requires two independent validators per item and an inter-rater
reliability score. **No item in the corpus has ever met this bar** — `irr_score` is null on
all 147 items, and no code computes an agreement statistic.

The path is specified but **not built**
(`docs/superpowers/specs/2026-07-19-item-validation-path-design.md`). Until it exists there is
nowhere for a validation rating to land.

When it does exist, validators will need:
- **Two distinct people per item.** One person rating twice is never two validators.
- **A validator may never rate an item they authored.**
- **A minimum shared batch of 10 items per pair** before reliability can be computed at all.

Practical consequence for contracting: what matters is not two SMEs *per language* but a
pool of multilingual SMEs large enough that, for every item, two of them share the language
and neither authored it. A pool of 3–4 multilingual linguist/domain SMEs covers the nine
languages provided **authorship is tracked per item** so the never-validate-your-own rule can
be enforced at assignment. Pack sizing to 20 (§1) gives each pack two pair-batches, so a pair
is never forced to carry a whole pack alone.

---

## 7. Sequencing

1. **Now:** contract authoring (§3) and calibration (§4). Both work today.
2. **Now, in parallel:** gold reference scoring (§5) — unblocks drift monitoring.
3. **After the validation build lands:** validation (§6). Contract with the two-SMEs-per-
   language constraint in mind from the start.

Do not contract validation before the build. There is nowhere to put the results.

---

## 8. Thresholds an SME's work is measured against

| threshold | value | where it bites |
|---|---|---|
| `MIN_ITEMS_PER_DIMENSION` | 10 | scored items per pack; below it, `low_coverage` caps the verdict at Conditional |
| `MIN_GROUP_SIZE` | 5 | items per cohort/language group; below it, the group is excluded from `bias_fairness` |
| IRR floor | 0.70 | Cohen's kappa between a validator pair; below it, adjudication |
| minimum shared batch | 10 | items a validator pair must both rate before kappa is computed |
| Tier 2 cap | 40% | single-expert items as a share of a pack's **scored** set |
| `FAILING_THRESHOLD` | 60.0 | dimension score below which a dimension is reported as failing |
