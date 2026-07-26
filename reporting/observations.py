"""Auto-generated 'Key Observations' notes for a scorecard.

A single pure function consumed by both the PDF report and the console, so the
two surfaces always show the same observations. Everything is derived from fields
already present on the Scorecard — no new data plumbing.
"""

from scoring.engine import FAILING_THRESHOLD, SAFETY_VETO_THRESHOLD

# Full dimension names for reader-facing prose (distinct from the radar's short labels).
_DIMENSION_FULL: dict[str, str] = {
    "language_performance":     "Language Performance",
    "cultural_appropriateness": "Cultural Appropriateness",
    "hallucination_risk":       "Hallucination Risk",
    "bias_fairness":            "Bias & Fairness",
    "code_switching_quality":   "Code-Switching",
    "safety_robustness":        "Safety & Robustness",
}

_HIGH_RISK = "High-Risk"  # VerdictBand.HIGH_RISK.value


def _name(dim: str) -> str:
    return _DIMENSION_FULL.get(dim, dim)


def build_key_observations(scorecard) -> list[str]:
    """Return ordered, human-readable observation bullets for a scorecard.

    Order: strongest dimension, weakest dimension, each dimension below the pass
    threshold (worst first), then active run flags (fabrication, unverified
    safety, low coverage, safety veto). Returns [] when there is nothing to say.
    """
    scores: dict[str, float] = getattr(scorecard, "dimension_scores", None) or {}
    obs: list[str] = []

    if scores:
        strongest = max(scores, key=lambda d: scores[d])
        weakest = min(scores, key=lambda d: scores[d])
        obs.append(f"Strongest dimension: {_name(strongest)} ({scores[strongest]:.1f}).")
        if weakest != strongest:
            obs.append(f"Weakest dimension: {_name(weakest)} ({scores[weakest]:.1f}).")
        below = sorted((d for d, s in scores.items() if s < FAILING_THRESHOLD), key=lambda d: scores[d])
        for d in below:
            obs.append(
                f"{_name(d)} is below the pass threshold "
                f"({scores[d]:.1f} < {FAILING_THRESHOLD:.0f})."
            )

    if getattr(scorecard, "african_fabrication_detected", False):
        obs.append("African fabrication was detected on at least one item — the hallucination gate fired.")
    if getattr(scorecard, "safety_unverified", False):
        obs.append("Safety was not verified this run — no applicable safety items were evaluated.")
    if getattr(scorecard, "confidence_flag", "standard") == "low_coverage":
        obs.append("Low coverage — one or more dimensions were evaluated on few items; interpret with caution.")

    safety = scores.get("safety_robustness")
    if (
        safety is not None
        and safety < SAFETY_VETO_THRESHOLD
        and getattr(scorecard, "verdict", "") == _HIGH_RISK
    ):
        obs.append(
            f"Safety veto applied — verdict forced to High-Risk "
            f"(Safety {safety:.1f} < {SAFETY_VETO_THRESHOLD:.0f})."
        )

    return obs
