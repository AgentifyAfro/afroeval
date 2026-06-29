# Code-Switching Quality Evaluator — Real Implementation Design

**Date:** 2026-06-28
**Status:** Approved, pending implementation plan

## Problem

`ail/code_switching.py::CodeSwitchingEvaluator` is currently a stub: it always
returns `score=0.6, passed=True` regardless of the actual model response,
ignoring `model_response` entirely. This dimension carries 10% of the composite
AfroEval Score — the second item in the priority order from the 2026-06-28 audit
of the Label Studio SME calibration export (`cultural_appropriateness`, the
highest-weight broken dimension, was fixed first and is already merged).

## Why this is a different shape from `cultural_appropriateness`

`METHODOLOGY_V1.md` section 2.5 documents three named sub-metrics for this
dimension — register match (35%), switch naturalness (35%), language
preservation (30%) — with no internal contradiction the way the cultural rubric
had (no "score holistically, don't split" instruction conflicting with the
weight table). `scoring/engine.py`'s `DEFAULT_METRIC_WEIGHTS` already has a
working, generic mechanism for exactly this shape — `language_performance` and
`hallucination_risk` both implement their documented sub-metrics as **separate
evaluator classes**, each independently registered in the dispatcher, each
producing its own `MetricResult` row, combined via
`_weighted_dimension_average()` (`scoring/engine.py:165`), which renormalizes
over whichever named metrics actually produced scores. This design follows that
established pattern rather than the single-holistic-metric shape used for
cultural appropriateness.

There is no dedicated rubric doc for this dimension (no `CODE_SWITCHING_RUBRIC.md`
exists), and `METHODOLOGY_V1.md` doesn't reference one as a companion doc for
this dimension the way it does for cultural appropriateness — implying the
methodology table was meant to be the full spec here. The scoring guide for each
sub-metric is therefore authored as part of this design (approved during
brainstorming), not transcribed from an existing doc — following the same
precedent as the already-working `FluencyEvaluator`, which also has no separate
rubric doc and keeps its scoring anchors directly in its prompt string.

## Architecture

- `ail/code_switching.py` is rewritten to contain three evaluator classes
  instead of one: `RegisterMatchEvaluator`, `SwitchNaturalnessEvaluator`,
  `LanguagePreservationEvaluator` — kept together in one file, mirroring how
  `evaluators/language_performance.py` keeps its sibling sub-metrics together.
- Each: `__init__(self, judge: LLMJudge | None = None)` (matching
  `FluencyEvaluator`'s exact pattern), `dimension` returns
  `"code_switching_quality"`, `metric_name` returns one of `"register_match"`,
  `"switch_naturalness"`, `"language_preservation"` respectively.
- Each builds its own focused criterion prompt for `LLMJudge.score()`, asking
  for an already-normalized 0.0-1.0 score directly (no rubric-scale conversion
  needed here, unlike cultural appropriateness — `METHODOLOGY_V1.md` already
  specifies "each scored 0.0–1.0 by an LLM-judge" for this dimension, so there's
  no clamping-corruption risk to design around).
- Approved scoring guides (verbatim, embedded in each prompt):
  - **Register match:** 1.0 = matches input register exactly; 0.7 = minor
    slippage, tone intact; 0.4 = noticeable mismatch (e.g. formal reply to an
    informal/mixed prompt); 0.0 = ignores the input's code-switched style
    entirely.
  - **Switch naturalness:** 1.0 = switches are grammatically/pragmatically
    natural, as a fluent bilingual speaker would switch; 0.7 = understandable
    but slightly forced; 0.4 = jarring or breaks mid-phrase; 0.0 = no attempt at
    switching when clearly required, or incoherent.
  - **Language preservation:** 1.0 = fully preserves the expected mix, never
    drops to monolingual English; 0.7 = mostly preserves it, one or two
    unnecessary English drops; 0.4 = frequently defaults to English; 0.0 =
    responds entirely in English when a code-switched response was clearly
    expected.
- Each prompt embeds `prompt`, `model_response`, `context["language"]`, and the
  documented primary varieties (Sheng, Nigerian Pidgin, Kinyarwanda-French,
  Darija) as grounding examples of what "code-switching" means in this
  evaluation. `expected_behavior` is passed through as light supporting
  context (these sub-metrics judge the response's own register/switching/
  language-mix qualities, not similarity to a reference text).
- `passed = score >= 0.6` for all three, matching the documented dimension-level
  "Pass threshold: ≥ 0.60," applied per sub-metric consistent with how
  `FluencyEvaluator`/`SemanticSimilarityEvaluator` each have their own pass
  threshold today.
- No-judge fallback identical to every other judge-backed evaluator (non-empty
  response → 0.5, empty → 0.0, reason states the judge wasn't configured).
- `scoring/engine.py`'s `DEFAULT_METRIC_WEIGHTS` gains a new entry:
  ```python
  "code_switching_quality": {
      "register_match": 0.35,
      "switch_naturalness": 0.35,
      "language_preservation": 0.30,
  },
  ```
  No other change to `scoring/engine.py` — `_weighted_dimension_average()` is
  already generic and consumes this automatically.
- `orchestration/dispatcher.py`: the import line changes from
  `from ail.code_switching import CodeSwitchingEvaluator` to import the three
  new classes, and the single `CodeSwitchingEvaluator(),` call site becomes
  three lines, each passed `judge=judge` (the same `judge` instance already
  passed to `FluencyEvaluator` and `CulturalAppropriatenessEvaluator`).
- `scripts/hitl_export_tasks.py`: remove `"code_switching_score"` from
  `_STUB_METRIC_NAMES` — the three new metric names never need adding to that
  set since they're real from creation.
- **No `METHODOLOGY_V1.md` fix needed.** This dimension's documented 35/35/30
  three-sub-metric design has no contradiction; it's exactly what's being
  implemented.

## Error handling

No new error handling needed. `LLMJudge.score()` already handles rate limits,
non-retryable errors, and generic failures, returning a fallback score and
reason rather than raising — inherited for free by all three new evaluators.

**Cost/latency note:** this dimension now makes 3 judge calls per item instead
of 1 (one per sub-metric). The existing `asyncio.Semaphore(10)` in
`orchestration/dispatcher.py` already bounds concurrent judge calls across the
whole run, so this doesn't introduce a new rate-limit risk — it does mean
somewhat more latency/API cost per run than before, which is an accepted
tradeoff of the 3-separate-evaluators shape (chosen for transparency over the
1-call alternative considered and rejected during brainstorming).

## Testing

Unit tests with a fake `LLMJudge` (no real Azure calls), per evaluator class:

1. No-judge stub path returns the same fallback behavior as `FluencyEvaluator`'s
   equivalent path.
2. A high score (e.g. 1.0) from the fake judge passes through unconverted and
   `passed` is `True`.
3. A low score (e.g. 0.4) passes through unconverted and `passed` is `False`
   (boundary: exactly 0.6 passes, just below fails).
4. The prompt sent to the judge contains that evaluator's specific scoring
   guide anchors and the primary-varieties grounding examples.

Plus one new test in `tests/test_scoring.py`, mirroring the existing
`test_weighted_dimension_average_matches_documented_weights` pattern (verified
directly in the codebase at `tests/test_scoring.py:122`) — confirming
`_weighted_dimension_average()` combines the three new sub-metrics at exactly
0.35/0.35/0.30 against `DEFAULT_METRIC_WEIGHTS["code_switching_quality"]`.

A live Azure verification (same approach used for the cultural evaluator) is
recommended once implemented, though no single documented worked example exists
for this dimension the way `CULTURAL_RUBRIC_V1.md` had one — the controller will
construct a clear Sheng or Nigerian Pidgin example by hand for this check.

## Out of scope (separate sub-projects, per the priority order already agreed)

- `hallucination_risk`'s African probe set expansion
  (`AfricanHallucinationProbeEvaluator`, currently only 2 of 6 documented topics)
- `bias_fairness` (`CohortDisparityEvaluator` / the unused, also-stub
  `InformalEconomyCohortEvaluator`)
- `safety_robustness`'s missing refusal-calibration and adversarial-robustness
  sub-metrics
