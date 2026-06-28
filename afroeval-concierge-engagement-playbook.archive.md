# AfroEval Concierge Engagement Playbook

**The end-to-end process for selling and delivering AfroEval Scorecard™ assessments before self-service infrastructure exists.**

This is the operating reference for how engagements actually run today. It's deliberately the simplest version that works — no multi-tenant API, no customer-facing SDK, no self-service anything. You are the operator for every engagement. Update this doc as the real process evolves; treat it as a living reference, not a fixed law.

---

## Why concierge, not self-service (for now)

AfroEval's existing console and evaluation pipeline already do everything needed to deliver a paid engagement — provider/model configuration, benchmark pack selection, scoring, reporting, and (for premium engagements) human SME calibration via Label Studio. None of that requires multi-tenancy, customer-facing API keys, or an SDK.

Self-service infrastructure (the multi-tenant REST API + SDK path explored separately) is a scaling investment for when there's proven repeat demand for customers to run evaluations themselves. Building it before that demand exists means guessing at requirements instead of learning them from real engagements. Concierge-first is the standard sequencing for any B2B infrastructure product pre-PMF — sell and deliver manually, automate what repeats.

---

## Who this is for (ideal customer profile)

Full audience-specific framing lives in `afroeval-messaging-playbook.md`. For sales targeting specifically, the highest-fit early customers are organizations that are:

- Already deploying (or about to deploy) an AI assistant into an African-language market — mobile money, customer service, healthcare, agriculture, public services
- Operating under real commercial or regulatory risk if the AI gets it wrong (banks, telecoms, health-tech, government services) — these are the buyers who feel the cost of *not* evaluating
- Not yet running rigorous African-language-specific evaluation internally (most aren't — that's the gap)

---

## The Engagement Lifecycle

### Phase 1 — Discovery Call

Find out, specifically:
- Which languages and markets they're deploying into
- Which domain (mobile money, healthcare, customer service, agriculture, etc.)
- Which model(s) they're running or evaluating (provider + model identifier)
- Whether an existing benchmark pack already matches their use case, or whether they need a **custom pack built** — bespoke pack authoring is a separate, higher-priced line item, not included in a standard engagement
- Their timeline and what decision the Scorecard needs to inform (a go/no-go launch decision, an internal audit, a vendor comparison, etc.)

Set expectations on turnaround time and exactly what you need from them (Phase 3).

### Phase 2 — Scope + Agreement

A simple, written scope-of-work covering:
- Which benchmark pack(s) and which model(s)/provider(s) are in scope
- Deliverable format — Scorecard PDF only, or PDF + live walkthrough call (see open decision below)
- Price and payment terms — deposit or full payment before delivery is standard consulting practice; don't deliver the full report on credit
- Data-handling terms — what happens to their model outputs and credentials during and after the engagement (see Phase 9)

**Not legal advice — get a real contract/NDA template reviewed by an actual lawyer before using it on a real client.** See the checklist below for what it needs to cover at minimum.

### Phase 3 — Credential Handoff

The client gives you API access to **their** model — their Azure OpenAI / OpenAI / Anthropic key and endpoint. This is the only "access" required; they never get access to your infrastructure, and you never need access to their broader systems.

- Receive credentials through a secure channel — a password-manager share link (1Password, etc.) or a short-lived, scope-restricted key if their platform supports it. **Never** plaintext email or chat.
- Store the credentials in your own `.env` for the duration of the engagement only, consistent with the existing security rules in this codebase (never hardcoded, never committed, never logged).

### Phase 4 — Run the Evaluation

Configure a new Assessment in the console (provider + model identifier + selected benchmark pack(s)) and launch the run exactly as the existing pipeline already works. No new code required.

Watch for connector failures or rate limits on the client's side — their production API key may have different quota/rate-limit behavior than your own test credentials.

### Phase 5 — Optional SME Calibration (Premium Tier)

For higher-stakes engagements, route a sample of model responses through the existing Label Studio HITL pipeline so a real native-speaker SME independently validates the automated scores.

This is the cleanest two-tier pricing split available, and it costs nothing to build since the pipeline already exists:
- **Standard Scorecard** — automated scoring only
- **Calibrated Scorecard** — automated scoring + human SME validation

### Phase 6 — Report Review

Generate the Scorecard (PDF/JSON export via `reporting/generator.py` — already built). Read it yourself before sending:
- Sanity-check the narrative against what you'd expect given the dimension scores
- Write a short cover note in plain language addressing the client's specific concern from Phase 1 — this interpretive layer is the actual concierge value-add over a raw automated score dump

### Phase 7 — Delivery + Walkthrough

Send the Scorecard. Where possible, walk through it live — same flow as the demo narrative in the messaging playbook (composite score and verdict first, then the dimension breakdown, then the specific example that explains the weakest dimension).

If the verdict is Conditional or Not-Ready, be concrete: name the exact failing dimension, show the specific example response, and explain what needs to change.

### Phase 8 — Retest Cycle

Conditional/Not-Ready clients fix the flagged issue and come back for a paid re-evaluation — this is recurring revenue without building any subscription infrastructure, since it's structurally just a second engagement.

For clients who pass, offer a standing retest cadence (e.g., quarterly) as a retainer — model behavior drifts as providers update the underlying model, so "evaluated once" doesn't mean "evaluated forever."

### Phase 9 — Credential Cleanup

Delete the client's credentials from your local environment (and ask them to rotate the key on their side) once the engagement closes. This is a mandatory closing step, not optional cleanup — treat it the same as any other security hygiene rule in this project.

---

## Open Decisions (yours to finalize — these are drafts, not commitments)

1. **Pricing structure** — draft recommendation: a flat fee per engagement, scoped to number of benchmark packs and number of models evaluated, with SME calibration priced as a premium add-on rather than baked into the base price. Simpler to sell than usage-based pricing, and matches how the engagement is actually delivered (bounded scope, not metered usage).
2. **Minimum viable deliverable** — Scorecard PDF alone, or always bundled with a live walkthrough call? A walkthrough is higher-touch and probably converts better early on, but doesn't scale past a handful of engagements running in parallel.
3. **Contract/NDA template** — needs real legal review before first use. At minimum it should cover: scope of evaluation, data handling and deletion of client credentials/outputs, payment terms, and a disclaimer that the Scorecard is an assessment, not a warranty or compliance certification.

---

## Security Checklist (every engagement)

- [ ] Client credentials received via secure channel, never plaintext
- [ ] Credentials stored only in local `.env`, never committed, never logged
- [ ] Scope-of-work signed before any evaluation work begins
- [ ] Payment terms satisfied per agreement before final deliverable is sent
- [ ] Credentials deleted/rotated at engagement close
- [ ] Client model outputs handled per the agreed data-handling terms (delete, retain, or anonymize as agreed)

---

## Relationship to the Self-Service Roadmap

This playbook covers the current, manual delivery model. The multi-tenant REST API + SDK path (organizations table, per-customer API keys, scoped authorization, rate limiting) remains explicitly parked until concierge engagements produce real evidence of repeat self-service demand — at which point that build should be informed by what actual customers asked for, not by assumptions made before the first sale.
