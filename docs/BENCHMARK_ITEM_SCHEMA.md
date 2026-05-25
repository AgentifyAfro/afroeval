# Benchmark Item Schema — Version 1.0

**Status:** Locked for MVP  
**Enforced by:** `benchmarks/loader.py` (required fields) and `db/models.py` (BenchmarkItem table)

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
| `language` | string | BCP-47 language code. Allowed: `sw`, `yo`, `am`, `ha`, `zu`, `sheng`. |
| `domain` | string | Deployment domain. Allowed: `mobile_money`, `customer_service`, `community_health`, `agriculture`, `government`. |

### Important optional fields

| Field | Type | Description |
|---|---|---|
| `cohort` | string | Target user cohort. Allowed: `informal_economy`, `informal_urban`, `informal_rural`, `formal`, `low_literacy`, `feature_phone`. Default: `""`. |
| `provenance` | string | Source of the scenario. Must reference a real deployment scenario, documented failure, or authoritative source. **Required before publishing.** |
| `is_gold` | boolean | True if this is a hidden calibration item. Gold items are seeded into SME work to monitor reliability. Default: `false`. |
| `is_held_out` | boolean | True if this item is reserved for contamination-controlled evaluation. **Never transmitted to model providers. Never published.** Default: `false`. |
| `tags` | array[string] | Free-form tags for filtering. Examples: `ussd`, `send_money`, `feature_phone`, `formal_register`. |
| `sme_author_id` | string | Anonymised identifier of the SME who authored the item. |
| `validation_count` | integer | Number of independent SME validators who reviewed this item. Items with < 2 validators are not published. |
| `irr_score` | float | Inter-rater reliability score for this item (Cohen's kappa or Krippendorff's alpha). Items below 0.60 go to adjudication. |
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

Examples: `mm-sw-001`, `cs-yo-017`, `ch-am-003`, `ag-ha-022`.

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

An item may be included in a published pack only when ALL of the following are true:

1. `validation_count` ≥ 2
2. `irr_score` ≥ 0.60 (or adjudicated by lead linguist)
3. `provenance` is non-empty
4. `is_held_out` is `false`
5. The item has been reviewed by the founder for methodology alignment

Items that are `is_gold: true` are NEVER published in any pack — they are used only in the internal calibration pipeline.

---

## Schema Version History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-25 | Initial schema, locked for Phase 1 build. |
