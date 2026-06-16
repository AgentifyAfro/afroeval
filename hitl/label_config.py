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
