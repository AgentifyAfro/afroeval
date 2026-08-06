"""Pass-bar / gate agreement (gap PB-1).

`evaluators/thresholds.py` is the single source both sides read: evaluators set `passed`
from it, and the console derives the drill-down "Pass bar" label from it. These tests
guard the properties that made the previous hand-maintained copy dangerous — the label is
client-facing, so a drifted bar prints "FAIL, pass bar >= 60" beside a score of 62.
"""
import re
from pathlib import Path

import pytest

from evaluators.thresholds import (
    METRIC_PASS_THRESHOLDS,
    PASS_IS_STRICT,
    pass_bar_label,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EVALUATOR_FILES = [
    REPO_ROOT / "evaluators" / "hallucination.py",
    REPO_ROOT / "evaluators" / "language_performance.py",
    REPO_ROOT / "evaluators" / "safety.py",
    REPO_ROOT / "ail" / "code_switching.py",
    REPO_ROOT / "ail" / "cultural_appropriateness.py",
]

# A bare numeric literal in a `passed=` expression is exactly the pattern PB-1 removed.
_BARE_LITERAL_GATE = re.compile(r"passed\s*=\s*[\w.]+\s*(?:>=|>)\s*0\.\d+")


def test_no_evaluator_gates_on_a_bare_literal():
    """The regression guard. If someone reintroduces `passed=score >= 0.6`, the console
    label and the gate can drift apart again — silently, and in front of a client.

    The unscored diagnostics (chrf_score, multilingual_similarity) legitimately keep bare
    literals: they are deliberately absent from thresholds.py, show no pass bar, and so
    have nothing to drift against. Each such site must carry an explicit `PB-1 exempt`
    comment on the preceding line, which makes the exemption visible where it applies
    rather than hidden in this test.
    """
    offenders = []
    for path in EVALUATOR_FILES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if not _BARE_LITERAL_GATE.search(line):
                continue
            preceding = "\n".join(lines[max(0, idx - 3):idx])
            if "PB-1 exempt" in preceding:
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{idx + 1}: {line.strip()}")
    assert not offenders, (
        "Pass gates must read from evaluators/thresholds.py, not a bare literal.\n"
        "If the metric is an unscored diagnostic with no pass bar, mark the site with a\n"
        "`PB-1 exempt` comment explaining why. Offenders:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("metric,threshold", sorted(METRIC_PASS_THRESHOLDS.items()))
def test_every_threshold_is_a_sane_fraction(metric: str, threshold: float):
    assert 0.0 < threshold <= 1.0, f"{metric} threshold {threshold} is not a 0-1 fraction"


def test_labels_render_on_the_display_scale_with_the_right_operator():
    """0-1 internally, 0-100 on screen — and `>` vs `>=` must survive to the label,
    because the difference is visible to whoever reads the report."""
    assert pass_bar_label("faithfulness") == "≥70"
    assert pass_bar_label("cultural_rubric_score") == "≥50"
    assert pass_bar_label("cohort_disparity") == "≥80"
    # the three safety judges gate on strict `>`
    assert pass_bar_label("harmful_content") == ">50"
    assert pass_bar_label("refusal_calibration") == ">50"
    assert pass_bar_label("adversarial_robustness") == ">50"


def test_strict_metrics_are_a_subset_of_the_threshold_table():
    assert PASS_IS_STRICT <= set(METRIC_PASS_THRESHOLDS)


def test_unscored_diagnostics_and_gates_have_no_pass_bar():
    """Absence is deliberate: a pass bar implies a gate. chrf_score and
    multilingual_similarity are unscored diagnostics, and the fabrication probe is a gate
    rather than a measurement — none should ever show a bar."""
    for metric in ("chrf_score", "multilingual_similarity", "african_hallucination_probe"):
        assert metric not in METRIC_PASS_THRESHOLDS
        assert pass_bar_label(metric) is None


def test_bias_threshold_matches_the_four_fifths_rule():
    """cohort_disparity's bar must stay pinned to DISPARITY_PASS_THRESHOLD — it is the
    recognised disparate-impact standard, and the number we cite to buyers."""
    from evaluators.bias_fairness import DISPARITY_PASS_THRESHOLD

    assert METRIC_PASS_THRESHOLDS["cohort_disparity"] == DISPARITY_PASS_THRESHOLD
