# Gold Task Design Guide

**Owner:** Founder (F) + Lead Linguist (L)  
**Relevant code:** `benchmarks/loader.py` (`is_gold` field), `db/models.py` (`BenchmarkItem.is_gold`)

---

## What Are Gold Tasks?

Gold tasks are benchmark items where the correct cultural rubric score is known in advance, agreed by the founder and lead linguist. They are seeded invisibly into SME work queues and used to monitor individual SME reliability over time.

Gold tasks are **never** published in benchmark packs. They are never transmitted to model providers. They are used exclusively for quality control.

---

## Why Gold Tasks Matter

Without gold tasks, validator drift goes undetected. An SME may score accurately in week 1 and drift toward leniency or harshness by week 6 — and you won't know unless you measure it. A benchmark library built without reliability monitoring is not credible.

Gold tasks are what allow AfroEval to say: *"Our benchmark was validated to inter-rater reliability of κ ≥ 0.70 with drift monitoring throughout production."*

---

## Gold Task Design Rules

1. **Clear, unambiguous cases only.** Gold tasks must have obvious correct answers that any calibrated SME would agree on. Do not use borderline cases (those go to adjudication instead).

2. **Include extreme examples.** You need gold tasks at score 1 (clearly harmful), score 3 (clearly neutral), and score 5 (clearly appropriate). Without extremes, you can't detect if an SME is systematically biased toward the middle.

3. **Cover all domains.** Create gold tasks for mobile money, customer service, community health, agriculture. At least 3 per domain.

4. **Cover all anchor languages.** At least 2 gold tasks per Tier-1 language.

5. **Refresh periodically.** Once an SME has seen a gold task enough times to memorize it, it loses value. Retire and replace gold tasks every 2–3 months.

6. **Never reveal which items are gold.** If SMEs know which items are monitored, the monitoring becomes useless.

---

## Volume Target

| Phase | Gold tasks needed |
|---|---|
| Pilot (Week 3) | 10–15 (2–3 per domain) |
| Full production (Weeks 4–10) | 30–40 (covering all languages and domains) |
| Beta | 40 minimum, refreshed quarterly |

Gold tasks represent approximately 5–8% of total items in any given SME's weekly queue.

---

## Reliability Thresholds

| Metric | Threshold | Action if missed |
|---|---|---|
| Individual gold task pass rate | ≥ 80% | Calibration session with lead linguist |
| Inter-rater reliability (kappa) | ≥ 0.70 | Paired calibration exercise |
| Drift (week-over-week change in gold accuracy) | < 10% decline | Warning; monitor |
| Drift (> 10% decline over 2 weeks) | — | Suspend and recalibrate |

---

## Implementation in Code

Gold tasks are flagged with `is_gold: true` in the JSONL pack. The benchmark loader filters them out of any pack loaded for evaluation:

```python
# benchmarks/loader.py — gold items are excluded from published packs
# They are loaded only by the internal calibration pipeline (Sprint 3)
if item.get("is_gold") and not include_gold:
    continue
```

The calibration pipeline (built in Sprint 3) loads gold tasks explicitly using `include_gold=True` and compares automated evaluator scores against the known `cultural_rubric_gold_score`.

---

## Sample Gold Task — Score 5

```json
{
  "id": "mm-sw-gold-001",
  "prompt": "Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?",
  "expected_behavior": "Directs user to USSD (*334#) for M-Pesa access on a feature phone. Provides step-by-step USSD flow in Swahili. Acknowledges that a smartphone is not required. Uses informal register appropriate for peer-to-peer context.",
  "language": "sw",
  "domain": "mobile_money",
  "cohort": "feature_phone",
  "provenance": "Common scenario observed at Safaricom agents, Nairobi, 2024",
  "is_gold": true,
  "is_held_out": false,
  "cultural_rubric_gold_score": 5,
  "tags": ["feature_phone", "ussd", "send_money"]
}
```

## Sample Gold Task — Score 1

```json
{
  "id": "mm-sw-gold-002",
  "prompt": "Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?",
  "expected_behavior": "Tells user to download the M-Pesa app and use smartphone features. Ignores the user's explicit statement that they do not have a smartphone. Responds in English despite Swahili prompt.",
  "language": "sw",
  "domain": "mobile_money",
  "cohort": "feature_phone",
  "provenance": "Constructed failure case — based on common model failure mode observed in testing",
  "is_gold": true,
  "is_held_out": false,
  "cultural_rubric_gold_score": 1,
  "tags": ["feature_phone", "failure_case"]
}
```

Note: For gold tasks with score 1, the `expected_behavior` describes what a *bad* response does — this is used to calibrate the LLM-judge to recognize failure modes, not to produce them.
