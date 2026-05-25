# Lead Linguist Onboarding Brief

**For:** Lead Linguist (L)  
**From:** AgentifyAfro.ai — Founder  
**Date:** Week 2 of the AfroEval MVP build

---

## What AfroEval Is

AfroEval Scorecard™ is an AI evaluation product that tests AI models for readiness to serve African users. It scores models across six dimensions (language performance, cultural appropriateness, hallucination risk, bias & fairness, code-switching quality, safety & robustness) and produces a governance-grade PDF scorecard.

The benchmark library — the collection of SME-validated test cases — is the product's moat. Your job is to build and protect it.

---

## Your Role

You are the Lead Linguist and Curation Coordinator. You own the pipeline that turns raw SME-authored items into validated, adjudicated, publication-ready benchmark content.

**You report to:** Founder  
**You coordinate:** 8–12 SMEs across Nairobi and Addis Ababa  
**You are NOT responsible for:** The scoring methodology (Founder), the platform engineering (Contract Engineer), or the product design

---

## What You Own

| Workstream | Your responsibility |
|---|---|
| SME coordination | Weekly rhythm, throughput tracking, communication |
| Inter-rater reliability | Compute kappa weekly; flag drift immediately |
| Gold task monitoring | Track gold pass rates; run calibration sessions |
| Adjudication | Issue final scores on disputed items with written rationale |
| Benchmark quality sign-off | No item is published without your approval |
| Pipeline reporting | Weekly throughput report to founder every Friday |

---

## The Five-Stage Pipeline

```
SEED → AUTHOR → VALIDATE → ADJUDICATE → PUBLISH
```

1. **Seed:** Founder provides scenario sources and domain coverage targets.
2. **Author:** SME authors write items in Label Studio. You review for queue balance.
3. **Validate:** Two independent validators score each item. You monitor IRR weekly.
4. **Adjudicate:** Items with validator disagreement > 1 rubric point come to you.
5. **Publish:** You sign off; items enter the versioned pack.

---

## Throughput Targets

| Week | Cumulative items target | Your weekly action |
|---|---|---|
| 3 | 50 (pilot) | Run pilot; identify schema and rubric issues |
| 6 | 250 | Full production confirmed; throughput on track |
| 8 | 450 | Validate throughput; gold tasks seeded across all domains |
| 10 | 700 | Validation + adjudication complete; gold set finalised |

**Weekly throughput:** ~12 validated items per active SME. With 8 SMEs, that's ~96 items/week net of revision cycles. Build in 20% revision overhead.

If throughput falls below target for two consecutive weeks, escalate to the founder immediately. The benchmark library is the critical path of the entire MVP.

---

## Tools You Will Use

| Tool | Purpose | Access |
|---|---|---|
| Label Studio | SME authoring, validation, adjudication queue | Provided by engineer (Week 3) |
| AfroEval Schema docs | `docs/BENCHMARK_ITEM_SCHEMA.md` | This repo |
| Cultural Rubric | `docs/CULTURAL_RUBRIC_V1.md` | This repo |
| SME Role Packs | `docs/SME_ROLE_PACKS.md` | Share with SMEs |
| Gold Task Guide | `docs/GOLD_TASK_DESIGN.md` | Your reference |
| Shared drive | SME materials, weekly reports | Provided by founder |

---

## Reliability Monitoring — Weekly Checklist

Every Friday, compute and report:

- [ ] Total items authored this week (by SME)
- [ ] Total items validated this week
- [ ] Total items adjudicated
- [ ] Items published (entered the pack)
- [ ] Items in revision queue
- [ ] Inter-rater reliability (kappa) — overall and per SME pair
- [ ] Gold task pass rate — overall and per individual SME
- [ ] Any SME with gold pass rate < 80% (flag for calibration)
- [ ] Estimated weeks to hit 700-item target at current throughput

Send this as a short written report to the founder before end of day Friday.

---

## Your First Two Weeks

**Week 2 (now):**
- Review all docs in `docs/` — especially the methodology, schema, rubric, and role packs
- Confirm your understanding of the five-stage pipeline with the founder
- Review the SME shortlist and provide input on candidates
- Suggest any changes to the rubric or schema before it is locked

**Week 3:**
- Label Studio is set up by the engineer — you configure the annotation interface
- Onboard the first 4–6 SMEs (the rest follow)
- Run the 50-item pilot (2 languages × 25 items)
- Report pilot issues by end of Week 3 Friday

---

## What the Founder Owns (Not You)

The following are founder decisions — bring questions, not recommendations:

- Which items belong in the gold set (you help, founder decides)
- Scoring methodology weights and thresholds
- Whether the benchmark schema changes (schema is now locked)
- Which SME candidates are contracted
- Publication decisions for the final benchmark library
