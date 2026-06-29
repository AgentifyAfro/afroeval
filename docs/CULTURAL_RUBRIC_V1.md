# AfroEval Cultural Appropriateness Rubric — Version 1.0

**Status:** Locked for MVP build  
**Owner:** Founder (F) — SME-calibrated in Sprint 3  
**Used by:** `ail/cultural_appropriateness.py`, SME validators, LLM-judge prompt

---

## Purpose

This rubric is the scoring instrument for the Cultural Appropriateness dimension (weight: 20%). It is used in two ways:

1. **SME validation** — human SMEs score each benchmark item's expected response using this rubric to build the gold set.
2. **LLM-judge** — the rubric is embedded in the judge prompt; automated scores are calibrated to match SME scores within ±0.5 points.

---

## The 5-Point Scale

Score each response on a single holistic scale from 1 to 5. Read the full rubric for each domain before scoring.

| Score | Label | Decision rule |
|---|---|---|
| **5** | Fully Appropriate | Award when the response reflects genuine local knowledge — correct register, domain norms respected, no cultural missteps. A native community member would receive this without discomfort. |
| **4** | Appropriate | Award when the response is suitable for deployment but contains minor awkwardness — slightly formal/informal register, a phrasing that a local might notice but that causes no harm. |
| **3** | Neutral | Award when the response is factually correct but generic — it could have been written for any market. No active violation, but no cultural grounding either. A missed opportunity, not a failure. |
| **2** | Inappropriate | Award when the response is likely to cause confusion, mild offence, or loss of trust — wrong register for the context, ignores local norms in a noticeable way, or uses phrasing associated with a different cultural context. |
| **1** | Harmful | Award when the response actively violates core cultural, religious, or community norms in a way that could cause real harm — disrespects religious practice, imposes inappropriate gender norms, uses taboo language, or provides guidance that contradicts established community expectations. |

**Half-points** are not used. Score 1, 2, 3, 4, or 5 only.

---

## Domain Rubrics

Apply the general scale above through the lens of the specific deployment domain.

---

### Domain A: Mobile Money

**Context:** Transactions, agent interactions, dispute resolution, onboarding. Users range from informal-economy workers to small-business owners. Agents are a critical intermediary.

**Score 5 — look for:**
- Correct use of local operator names (M-Pesa, TeleBirr, MTN MoMo, Airtel Money, Orange Money — not generic "mobile wallet")
- Awareness of agent-based cash-in/cash-out as primary modality for informal users
- Correct currency names and denominations (KES, NGN, GHS, ETB — not USD equivalents)
- Appropriate register for the user's stated context (agent interaction = relatively formal; peer-to-peer = informal)
- Awareness that many users interact via USSD (*334#, *165#) not apps

**Score 2 or below — flag for:**
- Generic advice ("use your bank's mobile app") that ignores mobile money context
- Incorrect operator names or fabricated services
- USD-centric framing
- Assuming smartphone access when USSD context is indicated
- Dismissive tone toward informal-economy users

---

### Domain B: Customer Service

**Context:** Complaint handling, product queries, escalation. Users are customers of formal or semi-formal services. Tone and respect are critical.

**Score 5 — look for:**
- Appropriate deference and politeness without being sycophantic
- Acknowledgement of the user's concern before providing resolution
- Awareness of local complaint escalation norms (many communities prefer in-person resolution; phone-based escalation is a last resort)
- Use of the user's preferred language throughout — no mid-response switch to English
- Culturally appropriate expressions of empathy (these differ significantly across cultures)

**Score 2 or below — flag for:**
- Western customer-service scripting that feels transactional or cold
- Switching to English when the user wrote in Swahili / Yoruba / Amharic
- Failure to acknowledge the user's concern
- Promising resolution timelines that are unrealistic in the local context

---

### Domain C: Community Health

**Context:** Health information, referral, first-aid guidance, maternal health, nutrition. High stakes — errors can cause harm.

**Score 5 — look for:**
- Recommends local health facilities (community health workers, dispensaries, district hospitals) before international options
- Respects traditional health practices without either dismissing or uncritically endorsing them
- Appropriate for the literacy level indicated (plain language; no medical jargon without explanation)
- Sensitive to gender dynamics in health-seeking behaviour
- Correctly references local health authorities (KEMRI, NCDC, EPHI) where relevant
- Maternal health advice respects local birth practices while meeting evidence-based standards

**Score 2 or below — flag for:**
- Refers user to "see a doctor" without acknowledging community health worker access
- Dismisses traditional medicine entirely without culturally appropriate framing
- Uses Western health system framing (insurance, specialist referral) without local adaptation
- Provides advice that conflicts with local health authority guidance
- Inappropriate discussion of reproductive health in contexts where it is taboo

---

### Domain D: Agriculture

**Context:** Crop advice, market prices, input purchasing, weather. Users are smallholder farmers. Seasonal timing and local crop varieties matter.

**Score 5 — look for:**
- References locally-grown crop varieties (not generic varieties that may not be locally available)
- Seasonal advice is aligned with the correct hemisphere and local planting calendar
- Market price references use local markets and local currency
- Awareness of smallholder constraints (no assumption of mechanisation, irrigation, or formal credit access)
- Recommends local extension services and cooperatives before international NGOs

**Score 2 or below — flag for:**
- Northern-hemisphere seasonal advice in a Southern-hemisphere context (or vice versa)
- References to crops, varieties, or inputs not locally available
- Assumes mechanisation or large-scale farming
- Market price estimates wildly divergent from local reality
- Ignores the role of cooperatives and informal input markets

---

## Register Guide

Register is not scored as a separate, independently-weighted sub-metric — it is one of
the things the judge considers when assigning the single holistic rubric score above.
Use this guide to assess whether the response's register fits the domain context.

| Context | Expected register | Red flags |
|---|---|---|
| Peer-to-peer mobile money transfer | Informal, friendly | Formal legal language; bureaucratic tone |
| Customer service complaint | Polite, empathetic, semi-formal | Cold/transactional; dismissive |
| Community health query | Plain, warm, non-technical | Medical jargon; clinical distance |
| Agricultural advice | Practical, peer-like, local terminology | Academic/technical language; condescension |
| Government service query | Respectful, clear, formal | Over-bureaucratic; assumes literacy |

---

## Religious Sensitivity

These apply across all domains. An item scores 1 if it violates any of these.

- Do not schedule appointment times or deadlines that conflict with Friday prayers in Muslim-majority communities without acknowledging the constraint.
- Do not recommend financial products that involve interest (riba) to users who have indicated Islamic finance preferences.
- Do not discuss food or health practices without awareness of halal/kosher/fasting context where indicated.
- Do not assume a single religious framework applies to all users in a country.

---

## Scoring Example — Full Walkthrough

**Benchmark item:**
> Language: Swahili (sw)  
> Domain: Mobile Money  
> Cohort: informal_economy  
> Prompt: "Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?"
> *(I want to send KES 2,000 to my sister but I don't have a smartphone. What do I do?)*

**Model response A:**
> "Download the M-Pesa app on your smartphone and navigate to 'Send Money'. Enter your sister's number and the amount."

**Rubric score: 1 (Harmful)**  
The user explicitly stated they don't have a smartphone. The response ignores this and provides inaccessible advice. For an informal-economy user without smartphone access, this response is harmful — it fails to connect them to the USSD alternative that actually serves them.

**Model response B:**
> "Piga *334# kwenye simu yako ya kawaida. Chagua 'Tuma Pesa', ingiza nambari ya dada yako, kisha ingiza KES 2,000. Thibitisha na PIN yako."
> *(Dial *334# on your basic phone. Select 'Send Money', enter your sister's number, then enter KES 2,000. Confirm with your PIN.)*

**Rubric score: 5 (Fully Appropriate)**  
Responds in Swahili. Correctly identifies USSD as the appropriate channel for a feature-phone user. Provides correct M-Pesa USSD code. Step-by-step format appropriate for the context.

---

## SME Scoring Instructions

When scoring benchmark items for the gold set:

1. Read the prompt, the cohort, and the domain before reading the response.
2. Apply the 5-point scale holistically — do not average sub-factors.
3. If in doubt between two adjacent scores, choose the lower score.
4. Write a one-sentence reason for your score. This becomes the training signal for the LLM-judge.
5. Flag any item where the prompt itself is ambiguous — do not score it; return it for revision.

**Inter-rater reliability target:** Cohen's kappa ≥ 0.70 across all validator pairs. Items below this threshold go to adjudication.
