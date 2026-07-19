"""
Inter-rater reliability for item validation (Methodology v1.4).

irr_score is a property of a RATER PAIR over a BATCH, not of an item. Cohen's kappa is
undefined for a single item, so it is computed once across every item a pair both rated and
that value is written onto each item in the batch. See
docs/superpowers/specs/2026-07-19-item-validation-path-design.md.
"""

from sklearn.metrics import cohen_kappa_score

# Below this many shared items a kappa is noise wearing a number. irr_score stays null and
# the item is not Tier 1 - never estimated, extrapolated, or borrowed from another pair.
MIN_SHARED_BATCH = 10

# Methodology v1.4. Three docs said 0.70 and one said 0.60; 0.70 governs. Also the
# conventional "substantial agreement" bar for Cohen's kappa.
IRR_FLOOR = 0.70


def batch_key(validator_a: str, validator_b: str) -> str:
    """Order-independent identifier for a rater pair. (A,B) and (B,A) are one pair."""
    lo, hi = sorted([validator_a, validator_b])
    return f"{lo}|{hi}"


def pair_kappa(a_scores: list[int], b_scores: list[int]) -> float | None:
    """
    Quadratic-weighted Cohen's kappa over one pair's shared items.

    Computed on cultural_score (1-5) only. Factual accuracy is a separate hard gate and is
    never averaged in - two validators disagreeing on whether an item is factually correct
    is a blocking defect, not a reliability statistic.

    Returns None when the shared batch is under MIN_SHARED_BATCH.
    """
    if len(a_scores) != len(b_scores):
        raise ValueError(
            f"rating lists must be the same length: {len(a_scores)} vs {len(b_scores)}"
        )
    if len(a_scores) < MIN_SHARED_BATCH:
        return None
    if a_scores == b_scores:
        # cohen_kappa_score returns nan when both raters use a single identical label
        # (zero variance). Perfect agreement is 1.0 by definition.
        return 1.0
    return float(cohen_kappa_score(a_scores, b_scores, weights="quadratic"))
