# SME Role Packs — AfroEval Benchmark Production

**Prepared by:** AgentifyAfro.ai  
**For:** SME Network — Kenya (Nairobi) & Ethiopia (Addis Ababa)  
**Coordinator:** Lead Linguist

These role packs describe what each SME does, what they are paid per item, and the quality standards they are held to. Share the relevant section with each SME on onboarding.

---

## The Four Roles

| Role | Owner | Focus | Joins |
|---|---|---|---|
| **Benchmark Author** | SME | Writes new test items | Week 3 |
| **Benchmark Validator** | SME | Reviews items authored by others | Week 3 |
| **Adjudicator** | Lead Linguist | Resolves validator disagreements | Week 3 |
| **Lead Linguist** | Contract | Coordinates pipeline, IRR, quality | Week 2 |

---

## Role 1: Benchmark Author

### What you do

You write benchmark items — test cases that measure how well an AI model serves real users in your language and domain. Each item is a prompt (what a user would ask or say), plus an expected behavior (what a correct, culturally appropriate response looks like).

You do NOT write sample AI responses. You write the specification of what a correct response would do.

### Eligibility

- Native or near-native speaker of the assigned language (Swahili, Yoruba, Amharic, Hausa, or Zulu)
- Domain knowledge in at least one of: mobile money, customer service, community health, agriculture
- Minimum secondary education
- Reliable internet access and ability to use a web-based tool (Label Studio)

### Your workflow (per item)

1. Log in to the AfroEval Label Studio instance.
2. Select an assigned scenario from the queue.
3. Write the prompt in the target language. The prompt must:
   - Be written as a real user would write it (not academic language)
   - Be grounded in a real deployment scenario (not invented)
   - Be appropriate for the assigned cohort (e.g., a USSD user would not reference an app)
4. Write the expected behavior in English. This is a description, not a sample answer. It should specify:
   - What the response must cover
   - What register is appropriate
   - Any cultural norms the response must respect
5. Complete the provenance field — where does this scenario come from? (e.g., "Observed at M-Pesa agent, Westlands, Nairobi, April 2026" or "Observed at TeleBirr agent, Bole, Addis Ababa, April 2026")
6. Mark the item as "authored" and submit.

### Quality standards

- Every item must have a verifiable provenance. If you cannot name the source scenario, do not author the item.
- No invented facts. If the expected behavior references a fee, code, or institution, verify it against an authoritative source.
- Write prompts that a real user would actually send. Avoid prompts that only a researcher would write.
- Your gold task pass rate must stay above 80% (the lead linguist monitors this weekly).

### Per-item rate

**$5 per validated item** (payment after the item passes two-validator review).  
Items that fail validation are returned to you for revision. A revised item that passes pays the full rate.  
Items rejected after revision are paid at $2.50 (50%).

---

## Role 2: Benchmark Validator

### What you do

You review items authored by others and score them for accuracy, cultural appropriateness, and schema compliance. You work independently of the author — you never see who wrote the item you are reviewing.

### Your workflow (per item)

1. Log in to Label Studio.
2. The system assigns you items to validate (never items you authored).
3. For each item, you score:

   **a. Factual accuracy** (Yes / No / Needs revision)  
   Is every factual claim in the expected behavior verifiable? Is the USSD code correct? Is the fee accurate? Is the institution named correctly?

   **b. Language quality** (1–3 scale)  
   - 3: Natural, native-speaker quality. The prompt reads as something a real user would send.  
   - 2: Acceptable but slightly unnatural phrasing.  
   - 1: Clearly non-native or academic. Return for revision.

   **c. Cultural appropriateness** (use the AfroEval Cultural Rubric — shared separately)  
   Score 1–5 using the rubric.

   **d. Schema compliance** (Checklist)  
   - Prompt is in the target language ✓/✗  
   - Expected behavior is a behavioral spec, not a sample answer ✓/✗  
   - Provenance field is non-empty ✓/✗  
   - Cohort is correctly assigned ✓/✗  

4. Write a one-sentence justification for your cultural rubric score.
5. Mark as "validated" (pass) or "needs revision" (fail) and submit.

### Quality standards

- Your independent score on gold tasks must agree with the known-correct score within ±1 rubric point.
- Your inter-rater reliability with other validators (measured weekly by the lead linguist) must be ≥ 0.70 kappa.
- You must not share item content outside the tool.

### Per-item rate

**$3 per item reviewed** (paid regardless of pass/fail outcome).

---

## Role 3: Adjudicator (Lead Linguist)

### What you do

When two validators disagree on a cultural rubric score by more than 1 point, the item enters adjudication. You review both validation records, the item, and the rubric, and issue a final score with a written rationale. Your score becomes the gold standard for the item.

### Adjudication workflow

1. The system flags items with validator disagreement > 1 point.
2. Review both validator scores and reasons.
3. Apply the rubric independently (without looking at validator scores first).
4. Issue a final score with a two-sentence rationale.
5. If the item itself is ambiguous or poorly written (causing the disagreement), return it for revision rather than adjudicating.

### Per-adjudication rate

Adjudication is included in the lead linguist contract — no separate per-item rate.

---

## Gold Tasks

Gold tasks are hidden benchmark items seeded into your regular work queue. You will not know which items are gold. The lead linguist uses your gold task performance to:

- Monitor your reliability over time
- Detect drift (if your scores become less accurate over a period)
- Flag any systemic quality issues early

**Your gold task scores do not reduce your pay.** They are used for quality monitoring only. If your gold task pass rate drops below 80% over two consecutive weeks, the lead linguist will schedule a calibration session with you.

---

## Confidentiality

All benchmark items are confidential. Do not:

- Share item content outside the Label Studio tool
- Discuss items on social media or messaging platforms
- Copy items to any external document
- Share the benchmark schema with third parties

Breach of confidentiality results in immediate contract termination and potential legal action. The benchmark library is proprietary intellectual property of AgentifyAfro.ai.

---

## Weekly Rhythm

| Day | Activity |
|---|---|
| Monday | New items appear in your queue |
| Wednesday | Mid-week check-in with lead linguist (15 min) |
| Friday | Submission deadline for the week's items |
| Following Monday | Payment processed for validated items from the previous week |

**Weekly throughput target:** 10–15 authored or validated items per SME.
