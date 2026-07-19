# Benchmark Item Schema — Version 1.3

**Status:** Locked for MVP  
**Enforced by:** `benchmarks/loader.py` (required fields, `SINGLE_EXPERT_VALIDATED_TAG`) and `db/models.py` (BenchmarkItem table)  
**Versioning:** This document carries its own version line (see Schema Version History), independent of the methodology version — v1.1 and v1.2 were schema-only changes with no methodology counterpart. v1.3 records the Tier 1 / Tier 2 publication regime introduced alongside **Methodology v1.3**; the matching numbers are coincidental, not a lockstep.

---

## JSONL Format

Each benchmark item is one JSON object on a single line in a `.jsonl` file. Every item MUST contain the required fields. Optional fields should be included wherever the information is known.

```json
{
  "id":                 "mm-sw-001",
  "prompt":             "Niambie jinsi ya kutuma pesa kwa M-Pesa.",
  "expected_behavior":  "Eleza hatua za kutuma pesa kwa M-Pesa kupitia USSD *334#...",
  "language":           "sw",
  "domain":             "mobile_money",
  "cohort":             "informal_economy",
  "provenance":         "Safaricom M-Pesa USSD guide 2024 — verified against live flow",
  "is_gold":            false,
  "is_held_out":        false,
  "tags":               ["send_money", "ussd", "feature_phone"],
  "sme_author_id":      "sme-nairobi-04",
  "validation_count":   2,
  "irr_score":          0.83,
  "cultural_rubric_gold_score": 5,
  "difficulty":         "standard"
}
```

---

## Field Reference

### Required fields (loader raises on missing)

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique item identifier. Format: `{domain_abbr}-{lang}-{seq}`. Example: `mm-sw-001`. |
| `prompt` | string | The exact input sent to the model. Written in the target language. Must be a real-world scenario grounded in documented deployment evidence. |
| `expected_behavior` | string | Description of what a correct response looks like. Not a sample answer — a behavioral specification. Used by evaluators and SME validators. |
| `language` | string | BCP-47 language code. Allowed: `sw`, `yo`, `am`, `ha`, `zu`, `sheng`, `om`, `so`, `en`. |
| `domain` | string | Deployment domain. Allowed: `mobile_money`, `customer_service`, `community_health`, `agriculture`, `government`, `remittance`. |

### Important optional fields

| Field | Type | Description |
|---|---|---|
| `cohort` | string | Target user cohort. Allowed: `informal_economy`, `informal_urban`, `informal_rural`, `formal`, `low_literacy`, `feature_phone`. Default: `""`. |
| `provenance` | string | Source of the scenario. Must reference a real deployment scenario, documented failure, or authoritative source. **Required before publishing.** |
| `is_gold` | boolean | True if this is a hidden calibration item. Gold items are seeded into SME work to monitor reliability. Default: `false`. |
| `is_held_out` | boolean | True if this item is reserved for contamination-controlled evaluation. **Never transmitted to model providers. Never published.** Default: `false`. |
| `tags` | array[string] | Free-form tags for filtering. Examples: `ussd`, `send_money`, `feature_phone`, `formal_register`. **Reserved:** `single_expert_validated` marks a Tier 2 item (see Publication Rules) and must not be applied by hand. |
| `sme_author_id` | string | Anonymised identifier of the SME who authored the item. |
| `validation_count` | integer | Number of **distinct people** who independently validated this item. Items with < 2 validators are not published under Tier 1; a value of exactly 1 may publish under Tier 2. Never incremented to represent one person reviewing twice, or to clear a gate. |
| `irr_score` | float \| null | Inter-rater reliability score for this item (Cohen's kappa or Krippendorff's alpha). Items below 0.60 go to adjudication. **`null` when `validation_count` < 2** — IRR is undefined for a single rater and is never estimated or backfilled. |
| `cultural_rubric_gold_score` | integer (1–5) | Agreed SME score on the Cultural Appropriateness rubric for the expected behavior. Used in LLM-judge calibration. |
| `difficulty` | string | `easy`, `standard`, `hard`. Informational; not used in scoring formula. |

---

## ID Naming Convention

```
{domain_abbr}-{language}-{sequence_number}
```

| Domain | Abbreviation |
|---|---|
| mobile_money | `mm` |
| customer_service | `cs` |
| community_health | `ch` |
| agriculture | `ag` |
| government | `gov` |
| remittance | `re` |

Examples: `mm-sw-001`, `cs-yo-017`, `ch-am-003`, `ag-ha-022`, `re-so-001`.

Held-out items append `-holdout`: `mm-sw-003-holdout`.  
Gold items append `-gold`: `cs-yo-011-gold`.

---

## Pack File Naming Convention

```
{domain}_{language}_{version}.jsonl
```

Examples:
- `mobile_money_sw_v1.0.0.jsonl`
- `customer_service_yo_v1.0.0.jsonl`
- `community_health_am_v1.0.0.jsonl`

**Never name a pack file with `held_out` in the name** — the loader filters by `is_held_out` field, not filename.

---

## Publication Rules

An item may be included in a published pack only when it qualifies under **Tier 1** or
**Tier 2** below. Tier 1 is the default and the standard every item should meet.

### Tier 1 — Dual-SME validated (default)

ALL of the following must be true:

1. `validation_count` ≥ 2
2. `irr_score` ≥ 0.60 (or adjudicated by lead linguist)
3. `provenance` is non-empty
4. `is_held_out` is `false`
5. The item has been reviewed by the founder for methodology alignment

### Tier 2 — Single-expert validated (exception)

For items validated by exactly one reviewer who holds **both** native/fluent command of
the item's language **and** subject-matter expertise in its domain. This tier exists so
such items can be published honestly — it does **not** relax what the data claims.

ALL of the following must be true:

1. `validation_count` == 1
2. `irr_score` is `null` — **must not be populated.** Inter-rater reliability is
   undefined for a single rater. It is never estimated, asserted, or backfilled.
3. `provenance` is non-empty **and** cites an authoritative external source
   (a guideline, protocol, or publication). Self-referential provenance such as
   "SME authored" does not satisfy this tier.
4. `is_held_out` is `false`
5. `is_gold` is `false` — calibration anchors require Tier 1 validation without exception.
   A gold item is the reference other measurements are checked against; it may not itself
   rest on a single unreplicated judgment.
6. The validator's dual qualification (language + domain) is attested and recorded in
   `sme_author_id`, with the basis stated in the item's provenance or the pack's
   `metadata`.
7. Explicit, dated founder sign-off.
8. The item carries the tag `single_expert_validated`.
9. Tier 2 items may not exceed **40% of a pack's scored set** — the items the loader
   actually evaluates, i.e. excluding `is_gold` and `is_held_out` items. The scored set is
   the denominator because that is the population a score is computed over; counting
   unscored anchors would let a pack dilute its way under the cap without changing what
   any evaluation actually rests on. A pack at or above the cap must add Tier 1 items or
   move Tier 2 items back to staging before release.
10. Any pack-level or scorecard-level reporting of validation status must disclose the
    presence and count of Tier 2 items. They are never reported as dual-validated.

**Why the tier exists rather than a waiver.** `validation_count` counts distinct people and
`irr_score` measures agreement between independent raters. A single expert — however
qualified — cannot supply either. Recording a second validator or an estimated IRR to pass
Tier 1 would make the corpus assert a review that did not happen, and would corrupt any
aggregate computed over those fields. Tier 2 publishes the item on the strength of the
expert's judgment while leaving the record accurate about what was and was not done.

Items that are `is_gold: true` are calibration anchors and are **NEVER scored** — the benchmark loader (`benchmarks/loader.py`) excludes them from every evaluation run by default (Methodology v1.1). They may live inside packs for calibration/monitoring and are returned only when a caller explicitly passes `include_gold=True`.

---

## Language Code Reference

| Code | Language | Primary Region |
|---|---|---|
| `sw` | Swahili (Kiswahili) | Kenya, Tanzania, Uganda |
| `yo` | Yoruba | Nigeria, Benin |
| `am` | Amharic | Ethiopia |
| `ha` | Hausa | Nigeria, Niger, Ghana |
| `zu` | Zulu (isiZulu) | South Africa |
| `sheng` | Sheng | Nairobi, Kenya (code-switch variety) |
| `om` | Oromo (Afaan Oromoo) | Oromia/Ethiopia, Kenya |
| `so` | Somali (Af Soomaali) | Somalia, Djibouti, Horn of Africa |
| `en` | English (US) | United States — high-resource comparative baseline |

---

## Schema Version History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-25 | Initial schema, locked for Phase 1 build. |
| v1.1 | 2026-06-16 | Added `om` (Oromo) and `so` (Somali) to AnchorLanguage; added `remittance` domain and `re` ID abbreviation. |
| v1.2 | 2026-06-17 | Added `en` (US English) as high-resource comparative baseline language. |
| v1.3 | 2026-07-18 | **Tier 1 / Tier 2 publication regime** (aligns with Methodology v1.3). Publication Rules split into Tier 1 — dual-SME validated, the default and unchanged — and Tier 2 — single-expert validated, an exception requiring `validation_count == 1`, `irr_score: null`, an authoritative external source in `provenance`, `is_gold: false`, attested dual qualification, dated founder sign-off, the reserved `single_expert_validated` tag, a ≤40% cap on the pack's scored set, and mandatory disclosure. Field reference updated for `tags`, `validation_count`, and `irr_score`. No structural field added or removed. |
