"""
Label Studio labeling-config XML for the model-response calibration project.

One Rating (0-10) + one TextArea (rationale) per AfroEval scorecard dimension.
Control names match the `response_reviews` column naming convention
(`<dimension>_score`, `<dimension>_rationale`) so import_reviews.py can map
annotation results straight back onto ResponseReview fields.
"""

from scoring.engine import DEFAULT_WEIGHTS

PROJECT_TITLE = "AfroEval — Response Calibration"

RATING_MAX = 10  # Rating widget emits 1-10; normalized to 0.0-1.0 on import (rating / RATING_MAX)


def _dimension_block(dimension: str) -> str:
    label = dimension.replace("_", " ").title()
    return f"""
  <View style="margin-top: 1em; padding: 0.5em; border: 1px solid #ddd;">
    <Header value="{label}" size="4"/>
    <Rating name="{dimension}_score" toName="response" maxRating="{RATING_MAX}" icon="star"/>
    <TextArea name="{dimension}_rationale" toName="response"
              placeholder="Why this score? (optional but encouraged)"
              rows="2" editable="true" maxSubmissions="1"/>
  </View>"""


def build_calibration_label_config() -> str:
    """Full <View> XML for the SME model-response calibration interface."""
    dimension_blocks = "\n".join(_dimension_block(d) for d in DEFAULT_WEIGHTS)

    return f"""<View>
  <Header value="Benchmark Prompt"/>
  <Text name="prompt" value="$prompt"/>

  <Header value="Model Response"/>
  <Text name="response" value="$response"/>

  <Header value="AfroEval Automated Scores (for reference only)"/>
  <Text name="automated_scores" value="$automated_scores"/>
{dimension_blocks}
</View>"""


# ── Item-authoring project ────────────────────────────────────────────────────
# A separate project where SMEs author/finalize NEW benchmark items from
# AI-drafted placeholders. The drafts scaffold the scenario/intent in English
# only — the SME writes the real in-language prompt, the expected-behavior spec,
# and the provenance. Nothing here is validated data until an SME approves it and
# it clears the two-validator + IRR pipeline (see docs/BENCHMARK_ITEM_SCHEMA.md).

AUTHORING_PROJECT_TITLE = "AfroEval — SME Item Authoring"

_LANGUAGES = ["sw", "yo", "am", "ha", "zu", "sheng", "om", "so", "en"]
_DOMAINS = ["mobile_money", "customer_service", "community_health",
            "agriculture", "government", "remittance"]
_COHORTS = ["informal_economy", "informal_urban", "informal_rural",
            "formal", "low_literacy", "feature_phone"]


def _choices(name: str, values: list[str]) -> str:
    opts = "\n".join(f'      <Choice value="{v}"/>' for v in values)
    return (f'    <Choices name="{name}" toName="scenario" choice="single" showInLine="true">\n'
            f'{opts}\n    </Choices>')


def build_authoring_label_config() -> str:
    """Full <View> XML for the SME item-authoring interface.

    Read-only reference fields ($scenario, $draft_prompt_intent,
    $draft_expected_behavior, $target_label, $provenance_hint) show the AI draft;
    editable controls capture the SME's authored item + metadata + status.
    """
    return f"""<View>
  <Header value="AfroEval — SME Item Authoring (DRAFT candidates for review)"/>
  <Header value="These are AI-drafted PLACEHOLDERS. The scenario and intent below are English starting points only — please author the REAL in-language prompt and expected-behavior spec, add provenance, confirm the metadata, and set a status. Reject anything unsuitable." size="6"/>

  <View style="padding:0.5em; background:#f6f5ff; border-left:3px solid #7C3AED;">
    <Header value="Draft scenario (reference — English)" size="4"/>
    <Text name="scenario" value="$scenario"/>
    <Header value="Draft prompt intent (reference — author the real in-language prompt below)" size="4"/>
    <Text name="draft_prompt_intent" value="$draft_prompt_intent"/>
    <Header value="Draft expected-behavior outline (reference)" size="4"/>
    <Text name="draft_expected_behavior" value="$draft_expected_behavior"/>
    <Header value="Target (confirm below)" size="4"/>
    <Text name="target_label" value="$target_label"/>
    <Text name="provenance_hint" value="$provenance_hint"/>
  </View>

  <View style="margin-top:1em; padding:0.6em; border:1px solid #7C3AED; border-radius:4px;">
    <Header value="SME authoring — fill these in" size="3"/>

    <Header value="Prompt — in the target language, exactly as a real user would write it" size="5"/>
    <TextArea name="prompt" toName="scenario" rows="4" editable="true" maxSubmissions="1"
              placeholder="Write the actual in-language prompt here (replace the English draft)."/>

    <Header value="Expected behavior — a behavioral spec of a correct response (NOT a sample answer)" size="5"/>
    <TextArea name="expected_behavior" toName="scenario" rows="4" editable="true" maxSubmissions="1"
              placeholder="Describe what a correct response must do."/>

    <Header value="Provenance — the real source / observed deployment scenario (required to publish)" size="5"/>
    <TextArea name="provenance" toName="scenario" rows="2" editable="true" maxSubmissions="1"
              placeholder="Cite the real source."/>

    <Header value="Language" size="5"/>
{_choices("language", _LANGUAGES)}
    <Header value="Domain" size="5"/>
{_choices("domain", _DOMAINS)}
    <Header value="Cohort" size="5"/>
{_choices("cohort", _COHORTS)}
    <Header value="Difficulty" size="5"/>
{_choices("difficulty", ["easy", "standard", "hard"])}
    <Header value="Status" size="5"/>
{_choices("status", ["approve", "needs_revision", "reject"])}

    <Header value="Notes (optional)" size="5"/>
    <TextArea name="sme_notes" toName="scenario" rows="2" editable="true" maxSubmissions="1"
              placeholder="Any notes for the reviewer / adjudicator."/>
  </View>
</View>"""
