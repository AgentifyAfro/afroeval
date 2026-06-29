# Cultural Appropriateness Evaluator — Real Implementation Design

**Date:** 2026-06-28
**Status:** Approved, pending implementation plan

## Problem

`ail/cultural_appropriateness.py::CulturalAppropriatenessEvaluator` is currently a stub:
it always returns `score=0.6, passed=True` regardless of the actual model response,
ignoring `model_response` and `expected_behavior` entirely. This dimension carries
20% of the composite AfroEval Score — the single highest weight among the
under-implemented dimensions discovered during a 2026-06-28 audit of the Label
Studio SME calibration export, which also found `bias_fairness`,
`code_switching_quality`, and the African-probe half of `hallucination_risk` in
similar or worse states (tracked as separate, later sub-projects).

The stub was actively misleading SMEs mid-calibration: every item showed an
identical "0.60 (pass)" for this dimension no matter how culturally appropriate
or inappropriate the response actually was. SME calibration work has been paused
pending this fix (and the others in the same audit) — see
`scripts/hitl_export_tasks.py`'s `_STUB_METRIC_NAMES` set (added 2026-06-28),
which currently suppresses this stub's misleading score in newly-exported tasks.

## Why this is buildable now (unlike the other broken dimensions)

`docs/CULTURAL_RUBRIC_V1.md` is a complete, already-designed scoring instrument:
a 5-point holistic scale, domain-specific look-for/flag-for checklists for 4
domains (mobile money, customer service, community health, agriculture), a
register guide, religious-sensitivity rules, and two fully worked scoring
examples. No new design work is needed for the rubric itself — only wiring it
into a real LLM-judge call, following the exact pattern `FluencyEvaluator`
(`evaluators/language_performance.py`) already uses successfully for
`language_performance`.

## Decisions made during brainstorming

**Single holistic metric, not a 70/30 split.** `METHODOLOGY_V1.md` section 2.2
documents two sub-metrics ("Cultural rubric score" 70%, "Register appropriateness"
30%), but `CULTURAL_RUBRIC_V1.md`'s own SME scoring instructions say to "apply the
5-point scale holistically — do not average sub-factors," and register is already
one of the things the rubric's domain checklists ask about. Implementing a single
metric matches how SMEs actually score, costs one LLM-judge call per item instead
of two, and matches `scoring/engine.py`'s current `DEFAULT_METRIC_WEIGHTS` (which
has no `cultural_appropriateness` entry at all today — a single metric already
gets 100% weight correctly under the existing fallback-to-flat-average behavior).
**`METHODOLOGY_V1.md` section 2.2 must be corrected to describe one metric, not
two**, as part of this work.

**Domain gap: fall back to general rubric only.** `BENCHMARK_ITEM_SCHEMA.md`
allows `government` and `remittance` domains, but `CULTURAL_RUBRIC_V1.md` has no
domain-specific checklist for either. For items in those domains, the evaluator
uses only the domain-agnostic parts of the rubric (the 5-point scale, the
Register Guide, and the Religious Sensitivity rules) — no domain-specific
look-for/flag-for checklist. This is honest about the current gap rather than
guessing via a near-domain substitute; domain-specific rubric sections for
`government`/`remittance` can be authored later as their own small addition.

## Architecture

- `ail/cultural_appropriateness.py::CulturalAppropriatenessEvaluator.__init__`
  gains `judge: LLMJudge | None = None`, mirroring `FluencyEvaluator` exactly.
- `evaluate()` builds one criterion prompt for `evaluators.llm_judge.LLMJudge.score()`
  containing:
  - The domain-specific look-for/flag-for checklist selected by `context["domain"]`
    (one of the 4 covered domains), or just the general scale + Register Guide +
    Religious Sensitivity rules if the domain isn't covered.
  - `context["language"]`, `context["cohort"]`, `prompt`, `model_response`, and
    `expected_behavior` (as supporting reference — the rubric judges the response
    on its own cultural merits, not text similarity to `expected_behavior`).
  - An instruction to return `{"score": <int 1-5>, "reason": "<one sentence>"}`.
- The returned 1-5 integer converts to `MetricOutput.score` (0.0-1.0 scale) via
  `(raw - 1) / 4` — the exact formula `METHODOLOGY_V1.md` section 2.2 already
  documents for converting the rubric to a 0-100 report scale, just applied to
  the evaluator's native 0.0-1.0 internal scale. `passed = score >= 0.5`, which
  maps exactly to the documented "rubric ≥ 3 passes" rule (`(3-1)/4 = 0.5`).
- `orchestration/dispatcher.py:247` changes from `CulturalAppropriatenessEvaluator()`
  to `CulturalAppropriatenessEvaluator(judge=judge)` — `judge` already exists in
  scope at that point (built at line 234, already passed to `FluencyEvaluator`).
- No-judge fallback (e.g. test environments without Azure configured) mirrors
  `FluencyEvaluator`'s exact stub behavior: non-empty response scores 0.5,
  empty response scores 0.0, reason states the judge wasn't configured.
- Once this ships, `"cultural_rubric_score"` is removed from `_STUB_METRIC_NAMES`
  in `scripts/hitl_export_tasks.py` so its real score and reason display again
  instead of the "not yet implemented" placeholder text.

## Error handling

No new error handling is needed. `LLMJudge.score()` already handles rate limits
(retry with exponential backoff), non-retryable 400s (content filter etc.), and
generic failures, returning a fallback score and an error-describing reason
rather than raising. This evaluator inherits that behavior for free by using the
same shared `LLMJudge` instance every other judge-backed evaluator uses.

## Testing

Unit tests with a fake `LLMJudge` (no real Azure calls, consistent with how
existing tests stub `deepeval`/judge dependencies):

1. Prompt includes the correct domain-specific section for each of the 4 covered
   domains (`mobile_money`, `customer_service`, `community_health`, `agriculture`).
2. Prompt falls back to general-only guidance (no domain checklist) for
   `government`, `remittance`, and an unrecognized/empty domain.
3. The 1-5 → 0.0-1.0 conversion is exact at every integer boundary: 1→0.0,
   2→0.25, 3→0.5, 4→0.75, 5→1.0.
4. `passed` is `True` exactly when raw rubric score ≥ 3.
5. No-judge stub path still returns the same fallback behavior as
   `FluencyEvaluator`'s equivalent path.
6. Sanity check against `CULTURAL_RUBRIC_V1.md`'s own two worked examples: a fake
   judge configured to return the documented score for each example (1 for
   Response A, 5 for Response B) confirms the evaluator's conversion and
   pass/fail logic produce the expected end-to-end result.

## Documentation fix included in this work

`METHODOLOGY_V1.md` section 2.2's metrics table currently lists two sub-metrics
("Cultural rubric score" 70%, "Register appropriateness" 30%). This must be
corrected to describe the single holistic metric this design implements, so the
methodology doc matches what actually ships — the same kind of doc/code
reconciliation already done for `language_performance` and the SME guides on
2026-06-27.

## Out of scope (separate sub-projects, per the priority order already agreed)

- `bias_fairness` (`CohortDisparityEvaluator` / the unused, also-stub
  `InformalEconomyCohortEvaluator`)
- `code_switching_quality` (`CodeSwitchingEvaluator`)
- `hallucination_risk`'s African probe set expansion
  (`AfricanHallucinationProbeEvaluator`, currently only 2 of 6 documented topics)
- `safety_robustness`'s missing refusal-calibration and adversarial-robustness
  sub-metrics
