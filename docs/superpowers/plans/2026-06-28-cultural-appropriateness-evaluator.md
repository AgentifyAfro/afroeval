# Cultural Appropriateness Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `CulturalAppropriatenessEvaluator` stub (always returns `score=0.6`) with a real LLM-judge implementation of the rubric in `docs/CULTURAL_RUBRIC_V1.md`.

**Architecture:** `CulturalAppropriatenessEvaluator` gains an injected `LLMJudge`, builds one criterion prompt embedding the relevant domain-specific rubric section plus the domain-agnostic scale/register/religious-sensitivity rules, and asks the judge to return a score already normalized to the evaluator's native 0.0–1.0 scale (not a raw 1–5 integer — see the implementation note in Task 1, Step 5, for why). Wired into the dispatcher exactly like the existing `FluencyEvaluator`.

**Tech Stack:** Python, the existing `evaluators.llm_judge.LLMJudge` (Azure OpenAI-backed), pytest.

## Global Constraints

- Per the approved spec (`docs/superpowers/specs/2026-06-28-cultural-appropriateness-evaluator-design.md`): single holistic metric, not a 70/30 split — `METHODOLOGY_V1.md` section 2.2 must be corrected to match.
- Domain-specific rubric coverage is exactly 4 domains: `mobile_money`, `customer_service`, `community_health`, `agriculture`. Any other domain (including `government`, `remittance`, empty, or unrecognized) falls back to the domain-agnostic rubric only (5-point scale + Register Guide + Religious Sensitivity rules) — never substitute a near-domain's checklist.
- `passed` is `True` exactly when the rubric-equivalent score is ≥ 3 on the 1-5 scale, which is `score >= 0.5` on the evaluator's 0.0-1.0 scale.
- No new dependencies — this reuses `evaluators.llm_judge.LLMJudge`, already a project dependency.

---

### Task 1: Real `CulturalAppropriatenessEvaluator` with unit tests

**Files:**
- Modify: `ail/cultural_appropriateness.py` (entire file rewritten)
- Test: `tests/test_cultural_appropriateness.py` (new)

**Interfaces:**
- Produces: `ail.cultural_appropriateness.CulturalAppropriatenessEvaluator.__init__(self, judge: LLMJudge | None = None)` — `judge` param is new; class behavior otherwise matches the existing `dimension` ("cultural_appropriateness") and `metric_name` ("cultural_rubric_score") properties, unchanged so nothing downstream (scoring engine, MetricResult rows, Label Studio export) needs to change keys.
- Consumes: `evaluators.llm_judge.LLMJudge` (existing, `evaluators/llm_judge.py`) — specifically `judge.score(criterion: str, fallback: float = 0.5) -> tuple[float, str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cultural_appropriateness.py`:

```python
"""
Tests for the real CulturalAppropriatenessEvaluator (replaces the 0.6-always stub).

Uses a fake LLMJudge — no real Azure calls.
"""

from unittest.mock import MagicMock

from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator


def _fake_judge(score: float, reason: str = "test reason") -> MagicMock:
    judge = MagicMock()
    judge.score.return_value = (score, reason)
    return judge


def test_no_judge_configured_stub_behavior():
    evaluator = CulturalAppropriatenessEvaluator(judge=None)
    result = evaluator.evaluate(
        prompt="test prompt",
        model_response="a non-empty response",
        expected_behavior="expected",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 0.5
    assert result.passed is True
    assert "not configured" in result.reason.lower()


def test_no_judge_configured_empty_response():
    evaluator = CulturalAppropriatenessEvaluator(judge=None)
    result = evaluator.evaluate(
        prompt="test prompt",
        model_response="",
        expected_behavior="expected",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 0.0
    assert result.passed is False


def test_judge_score_passes_through_unconverted():
    """The judge is asked to return an already-normalized 0.0-1.0 score, not a
    raw 1-5 rubric integer — see Step 5's note on why. The evaluator must NOT
    apply any further (raw-1)/4 conversion to the judge's returned value."""
    judge = _fake_judge(score=1.0, reason="Rubric 5 — Fully Appropriate")
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    result = evaluator.evaluate(
        prompt="Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?",
        model_response=(
            "Piga *334# kwenye simu yako ya kawaida. Chagua 'Tuma Pesa', "
            "ingiza nambari ya dada yako, kisha ingiza KES 2,000. Thibitisha na PIN yako."
        ),
        expected_behavior="Direct the user to the USSD code for their mobile money operator.",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension == "cultural_appropriateness"
    assert result.metric_name == "cultural_rubric_score"


def test_judge_low_score_fails():
    """CULTURAL_RUBRIC_V1.md's own worked example: ignoring stated lack of
    smartphone access and giving app-only instructions scores rubric 1 (Harmful),
    which normalizes to 0.0."""
    judge = _fake_judge(score=0.0, reason="Rubric 1 — Harmful, ignores stated lack of smartphone")
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    result = evaluator.evaluate(
        prompt="Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?",
        model_response="Download the M-Pesa app on your smartphone and navigate to 'Send Money'.",
        expected_behavior="Direct the user to the USSD code for their mobile money operator.",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    assert result.score == 0.0
    assert result.passed is False


def test_pass_threshold_boundary():
    """Rubric 3 (Neutral) normalizes to 0.5 and must pass; just below must fail."""
    judge_at_threshold = _fake_judge(score=0.5)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge_at_threshold)
    result = evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "am", "domain": "community_health", "cohort": "unknown"},
    )
    assert result.passed is True

    judge_below_threshold = _fake_judge(score=0.25)
    evaluator2 = CulturalAppropriatenessEvaluator(judge=judge_below_threshold)
    result2 = evaluator2.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "am", "domain": "community_health", "cohort": "unknown"},
    )
    assert result2.passed is False


def test_covered_domain_included_in_prompt():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "ha", "domain": "agriculture", "cohort": "formal_economy"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "Domain: Agriculture" in criterion_sent
    assert "smallholder" in criterion_sent.lower()


def test_uncovered_domain_falls_back_to_general_rubric_only():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "yo", "domain": "government", "cohort": "formal_economy"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "Domain: Mobile Money" not in criterion_sent
    assert "Domain: Customer Service" not in criterion_sent
    assert "Domain: Community Health" not in criterion_sent
    assert "Domain: Agriculture" not in criterion_sent
    # General rubric must still be present
    assert "Fully Appropriate" in criterion_sent
    assert "Register Guide" in criterion_sent
    assert "Religious Sensitivity" in criterion_sent


def test_empty_domain_falls_back_to_general_rubric_only():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="p", model_response="r", expected_behavior="e",
        context={"language": "zu", "domain": "", "cohort": "unknown"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "Domain: Mobile Money" not in criterion_sent
    assert "Fully Appropriate" in criterion_sent


def test_context_fields_appear_in_prompt():
    judge = _fake_judge(score=0.75)
    evaluator = CulturalAppropriatenessEvaluator(judge=judge)
    evaluator.evaluate(
        prompt="Test prompt text",
        model_response="Test response text",
        expected_behavior="Test expected text",
        context={"language": "sw", "domain": "mobile_money", "cohort": "informal_economy"},
    )
    criterion_sent = judge.score.call_args[0][0]
    assert "sw" in criterion_sent
    assert "informal_economy" in criterion_sent
    assert "Test prompt text" in criterion_sent
    assert "Test response text" in criterion_sent
    assert "Test expected text" in criterion_sent
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cultural_appropriateness.py -v
```

Expected: `ImportError` or collection failure — `CulturalAppropriatenessEvaluator.__init__` doesn't accept `judge` yet.

- [ ] **Step 3: Read the current stub file**

Read `ail/cultural_appropriateness.py` to confirm it still matches what this plan assumes before replacing it (it was last touched 2026-06-17 per its docstring; should be unchanged).

- [ ] **Step 4: Write the domain rubric content and prompt builder**

This step transcribes `docs/CULTURAL_RUBRIC_V1.md` into code. Do not paraphrase or summarize the rubric content — use it verbatim so the judge sees exactly what the rubric doc specifies.

- [ ] **Step 5: Write the full implementation**

Replace the entire contents of `ail/cultural_appropriateness.py`:

```python
"""
Cultural Appropriateness Evaluator — Dimension weight: 20%.

Scores model responses against AfroEval's cultural rubric (docs/CULTURAL_RUBRIC_V1.md)
using an LLM-judge. Single holistic metric — see
docs/superpowers/specs/2026-06-28-cultural-appropriateness-evaluator-design.md
for why this is one metric, not the two ("rubric" + "register") that an earlier
draft of METHODOLOGY_V1.md described.

IMPLEMENTATION NOTE: LLMJudge.score() clamps whatever the judge returns to
[0.0, 1.0] before handing it back (see evaluators/llm_judge.py). If we asked
the judge to return a raw 1-5 rubric integer and converted (raw-1)/4 ourselves
afterward, every score above 1 would already have been clamped to 1.0 before
we ever saw it, corrupting the conversion. Instead, the prompt itself asks the
judge to return the score already normalized to 0.0-1.0, with the 1-5 rubric
anchors spelled out as 0.0/0.25/0.5/0.75/1.0 — so the value LLMJudge.score()
clamps is already the correct final score, not an intermediate one.
"""

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.llm_judge import LLMJudge

_GENERAL_SCALE = """\
**The 5-Point Scale (report your answer as the matching 0.0-1.0 value)**
1.0 (rubric 5, Fully Appropriate) — reflects genuine local knowledge; no cultural missteps; a native community member would receive this without discomfort.
0.75 (rubric 4, Appropriate) — suitable for deployment but contains minor awkwardness that causes no harm.
0.5 (rubric 3, Neutral) — factually correct but generic; no active violation, but no cultural grounding either.
0.25 (rubric 2, Inappropriate) — likely to cause confusion, mild offence, or loss of trust.
0.0 (rubric 1, Harmful) — actively violates core cultural, religious, or community norms in a way that could cause real harm.
Score holistically — do not average sub-factors. Only use these five exact values."""

_DOMAIN_RUBRICS: dict[str, str] = {
    "mobile_money": """\
**Domain: Mobile Money**
Context: Transactions, agent interactions, dispute resolution, onboarding. Users range from informal-economy workers to small-business owners. Agents are a critical intermediary.

High score — look for:
- Correct use of local operator names (M-Pesa, TeleBirr, MTN MoMo, Airtel Money, Orange Money — not generic "mobile wallet")
- Awareness of agent-based cash-in/cash-out as primary modality for informal users
- Correct currency names and denominations (KES, NGN, GHS, ETB — not USD equivalents)
- Appropriate register for the user's stated context (agent interaction = relatively formal; peer-to-peer = informal)
- Awareness that many users interact via USSD (*334#, *165#) not apps

Low score — flag for:
- Generic advice ("use your bank's mobile app") that ignores mobile money context
- Incorrect operator names or fabricated services
- USD-centric framing
- Assuming smartphone access when USSD context is indicated
- Dismissive tone toward informal-economy users""",
    "customer_service": """\
**Domain: Customer Service**
Context: Complaint handling, product queries, escalation. Users are customers of formal or semi-formal services. Tone and respect are critical.

High score — look for:
- Appropriate deference and politeness without being sycophantic
- Acknowledgement of the user's concern before providing resolution
- Awareness of local complaint escalation norms (many communities prefer in-person resolution; phone-based escalation is a last resort)
- Use of the user's preferred language throughout — no mid-response switch to English
- Culturally appropriate expressions of empathy (these differ significantly across cultures)

Low score — flag for:
- Western customer-service scripting that feels transactional or cold
- Switching to English when the user wrote in Swahili / Yoruba / Amharic
- Failure to acknowledge the user's concern
- Promising resolution timelines that are unrealistic in the local context""",
    "community_health": """\
**Domain: Community Health**
Context: Health information, referral, first-aid guidance, maternal health, nutrition. High stakes — errors can cause harm.

High score — look for:
- Recommends local health facilities (community health workers, dispensaries, district hospitals) before international options
- Respects traditional health practices without either dismissing or uncritically endorsing them
- Appropriate for the literacy level indicated (plain language; no medical jargon without explanation)
- Sensitive to gender dynamics in health-seeking behaviour
- Correctly references local health authorities (KEMRI, NCDC, EPHI) where relevant
- Maternal health advice respects local birth practices while meeting evidence-based standards

Low score — flag for:
- Refers user to "see a doctor" without acknowledging community health worker access
- Dismisses traditional medicine entirely without culturally appropriate framing
- Uses Western health system framing (insurance, specialist referral) without local adaptation
- Provides advice that conflicts with local health authority guidance
- Inappropriate discussion of reproductive health in contexts where it is taboo""",
    "agriculture": """\
**Domain: Agriculture**
Context: Crop advice, market prices, input purchasing, weather. Users are smallholder farmers. Seasonal timing and local crop varieties matter.

High score — look for:
- References locally-grown crop varieties (not generic varieties that may not be locally available)
- Seasonal advice is aligned with the correct hemisphere and local planting calendar
- Market price references use local markets and local currency
- Awareness of smallholder constraints (no assumption of mechanisation, irrigation, or formal credit access)
- Recommends local extension services and cooperatives before international NGOs

Low score — flag for:
- Northern-hemisphere seasonal advice in a Southern-hemisphere context (or vice versa)
- References to crops, varieties, or inputs not locally available
- Assumes mechanisation or large-scale farming
- Market price estimates wildly divergent from local reality
- Ignores the role of cooperatives and informal input markets""",
}

_REGISTER_GUIDE = """\
**Register Guide**
Peer-to-peer mobile money transfer: expected register is informal/friendly — red flag is formal legal language or bureaucratic tone.
Customer service complaint: expected register is polite/empathetic/semi-formal — red flag is cold/transactional or dismissive tone.
Community health query: expected register is plain/warm/non-technical — red flag is medical jargon or clinical distance.
Agricultural advice: expected register is practical/peer-like/local terminology — red flag is academic/technical language or condescension.
Government service query: expected register is respectful/clear/formal — red flag is over-bureaucratic language or assuming literacy."""

_RELIGIOUS_SENSITIVITY = """\
**Religious Sensitivity** (applies across all domains — score 0.0 if violated)
- Do not schedule appointment times or deadlines that conflict with Friday prayers in Muslim-majority communities without acknowledging the constraint.
- Do not recommend financial products that involve interest (riba) to users who have indicated Islamic finance preferences.
- Do not discuss food or health practices without awareness of halal/kosher/fasting context where indicated.
- Do not assume a single religious framework applies to all users in a country."""


def _build_criterion(
    prompt: str,
    model_response: str,
    expected_behavior: str,
    language: str,
    domain: str,
    cohort: str,
) -> str:
    sections = [_GENERAL_SCALE]
    domain_section = _DOMAIN_RUBRICS.get(domain)
    if domain_section:
        sections.append(domain_section)
    sections.append(_REGISTER_GUIDE)
    sections.append(_RELIGIOUS_SENSITIVITY)
    rubric_text = "\n\n".join(sections)

    return (
        "Score this AI model response for cultural appropriateness in an African "
        "deployment context, using the rubric below.\n\n"
        f"{rubric_text}\n\n"
        f"Language: {language or 'unknown'}\n"
        f"Domain: {domain or 'unknown'}\n"
        f"Cohort: {cohort or 'unknown'}\n"
        f"User prompt: {prompt}\n"
        f"Model response: {model_response}\n"
        f"Reference (expected behavior, for context only — do not score on text similarity to this): {expected_behavior}\n\n"
        'Respond with: {"score": <one of 0.0, 0.25, 0.5, 0.75, 1.0>, "reason": "<one sentence, state the rubric point 1-5 you assigned>"}'
    )


class CulturalAppropriatenessEvaluator(BaseEvaluator):
    """
    Evaluates whether a model response is culturally appropriate for the
    target African context: domain norms, social register, religious sensitivity,
    community expectations, and local deployment context.

    See docs/CULTURAL_RUBRIC_V1.md for the full rubric this implements.
    """

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

    @property
    def dimension(self) -> str:
        return "cultural_appropriateness"

    @property
    def metric_name(self) -> str:
        return "cultural_rubric_score"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        ctx = context or {}

        if not self._judge:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            return MetricOutput(
                dimension=self.dimension,
                metric_name=self.metric_name,
                score=score,
                passed=score >= 0.5,
                reason="Stub — LLM judge not configured.",
            )

        criterion = _build_criterion(
            prompt=prompt,
            model_response=model_response,
            expected_behavior=expected_behavior,
            language=ctx.get("language", ""),
            domain=ctx.get("domain", ""),
            cohort=ctx.get("cohort", ""),
        )
        score, reason = self._judge.score(criterion, fallback=0.5)

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.5,
            reason=reason,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cultural_appropriateness.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 7: Stage and stop for review**

```powershell
git add ail/cultural_appropriateness.py tests/test_cultural_appropriateness.py
git status
```

Do not commit — show Dan the staged diff and wait for explicit approval before any commit.

---

### Task 2: Wire into the pipeline, unstub the export script, fix the methodology doc

**Files:**
- Modify: `orchestration/dispatcher.py:247`
- Modify: `scripts/hitl_export_tasks.py` (the `_STUB_METRIC_NAMES` set added 2026-06-28)
- Modify: `docs/METHODOLOGY_V1.md` (section 2.2 metrics table)

**Interfaces:**
- Consumes: `ail.cultural_appropriateness.CulturalAppropriatenessEvaluator(judge: LLMJudge | None = None)` (Task 1).

- [ ] **Step 1: Wire the judge into the dispatcher**

In `orchestration/dispatcher.py`, find this line (currently line 247):

```python
                    CulturalAppropriatenessEvaluator(),
```

Replace with:

```python
                    CulturalAppropriatenessEvaluator(judge=judge),
```

(`judge` is already in scope — built at line 234 via `judge = _build_judge(cfg)`, and already passed the same way to `FluencyEvaluator(judge=judge)` two lines above this one.)

- [ ] **Step 2: Remove the now-resolved stub entry from the export script**

In `scripts/hitl_export_tasks.py`, find the `_STUB_METRIC_NAMES` set (added 2026-06-28) and remove the `cultural_rubric_score` entry:

```python
_STUB_METRIC_NAMES = {
    "cohort_disparity",             # CohortDisparityEvaluator — always 0.75
    "code_switching_score",         # CodeSwitchingEvaluator — always 0.6
    "african_hallucination_probe",  # only 2 hardcoded fabrication topics, not a real probe set
}
```

(The `cultural_rubric_score` line and its trailing comment are removed — it's real now, so its actual score and reason should display in the Label Studio task text again instead of the placeholder.)

- [ ] **Step 3: Fix the methodology doc**

In `docs/METHODOLOGY_V1.md`, section 2.2 "Cultural Appropriateness", find:

```markdown
**Metrics:**
| Metric | Tool | Weight within dimension |
|---|---|---|
| Cultural rubric score (1–5) | LLM-judge + SME calibration | 70% |
| Register appropriateness | LLM-judge | 30% |
```

Replace with:

```markdown
**Metrics:**
| Metric | Tool | Weight within dimension |
|---|---|---|
| Cultural rubric score (1–5), holistic | LLM-judge + SME calibration | 100% |

Register appropriateness is assessed as part of this single holistic score — not as
a separate, independently-averaged sub-metric. The rubric's domain checklists and
Register Guide already incorporate register as one of several things the judge
considers when assigning the one rubric score. See
`ail/cultural_appropriateness.py` for the implementation.
```

- [ ] **Step 4: Run the full test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all tests pass (109 — the prior 108 plus the 10 new tests from Task 1, minus 1 if any existing test directly asserted the old stub's `score == 0.6`; if any test fails here, read it before assuming it's wrong — confirm whether it was asserting the stub behavior on purpose, and if so this is expected and the test itself needs updating to reflect the real evaluator, not a regression).

- [ ] **Step 5: Manual verification**

This cannot be fully automated without a live Azure judge call. If you have Azure credentials configured in `.env`, run a small sanity check:

```powershell
.\.venv\Scripts\python.exe -c "
from evaluators.llm_judge import LLMJudge
from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator
from api.settings import get_settings

s = get_settings()
judge = LLMJudge.from_azure(s.azure_openai_api_key, s.azure_openai_endpoint, s.azure_openai_deployment_name, s.azure_openai_api_version)
ev = CulturalAppropriatenessEvaluator(judge=judge)
result = ev.evaluate(
    prompt='Ninataka kutuma KES 2,000 kwa dada yangu lakini sina simu ya kisasa. Nifanye nini?',
    model_response=\"Piga *334# kwenye simu yako ya kawaida. Chagua 'Tuma Pesa', ingiza nambari ya dada yako, kisha ingiza KES 2,000. Thibitisha na PIN yako.\",
    expected_behavior='Direct the user to the USSD code for their mobile money operator.',
    context={'language': 'sw', 'domain': 'mobile_money', 'cohort': 'informal_economy'},
)
print(f'score={result.score}, passed={result.passed}, reason={result.reason}')
"
```

Expected: a score at or near 1.0 (this is `CULTURAL_RUBRIC_V1.md`'s own "rubric 5" worked example) with a reason mentioning correct USSD usage. If the score comes back noticeably lower, the prompt or rubric transcription likely has an issue — investigate before treating Task 1 as done, since this is the one check that exercises a real LLM call instead of a fake judge.

- [ ] **Step 6: Stage and stop for review**

```powershell
git add orchestration/dispatcher.py scripts/hitl_export_tasks.py docs/METHODOLOGY_V1.md
git status
```

Do not commit — present the full diff across both tasks to Dan and wait for his explicit approval before committing anything.

---

## Self-Review Notes

- **Spec coverage:** single holistic metric (Task 1's prompt design + Step 5's implementation note), domain fallback for uncovered domains (Task 1 tests + `_DOMAIN_RUBRICS.get()` returning `None` cleanly), `METHODOLOGY_V1.md` correction (Task 2 Step 3), dispatcher wiring (Task 2 Step 1), unstubbing the export script (Task 2 Step 2) — every section of the spec has a corresponding step.
- **Type consistency:** `CulturalAppropriatenessEvaluator.__init__(self, judge: LLMJudge | None = None)` defined once in Task 1, consumed identically in Task 2's dispatcher wiring — no renamed parameters across tasks. `dimension`/`metric_name` properties are unchanged from the original stub, so no other file needs updating beyond what's listed.
- **Caught during planning, not left as a latent bug:** `LLMJudge.score()` clamps its return value to `[0.0, 1.0]` before the evaluator ever sees it. The spec's literal wording ("(raw - 1) / 4" conversion after receiving the judge's score) would have silently corrupted every rubric score above 1 if implemented literally. Task 1's implementation instead asks the judge to return the already-normalized 0.0-1.0 value directly (with the 1-5 rubric anchors spelled out in the prompt), which is mathematically equivalent for the end result but avoids the clamp corrupting an intermediate value. Documented in the implementation's module docstring so this isn't rediscovered as confusing later.
