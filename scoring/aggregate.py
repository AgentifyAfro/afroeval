"""Post-hoc composite aggregation from persisted metric means.

The live scoring path (scoring/engine.py) computes the certified composite per RUN, per item.
This helper applies the SAME weighting rules (DEFAULT_WEIGHTS + DEFAULT_METRIC_WEIGHTS) to
already-aggregated per-metric means, so re-aggregations — e.g. the console's per-LANGUAGE
Language Comparison table — stay methodologically consistent with the scorecard instead of
inventing an unweighted formula. The engine constants below are the single source of truth.
"""
from scoring.engine import DEFAULT_METRIC_WEIGHTS, DEFAULT_WEIGHTS


def _dimension_score(dimension: str, metric_means: dict[str, float]) -> float | None:
    """One dimension's 0-100 score from its {metric_name: mean_0-1}.

    Dimensions in DEFAULT_METRIC_WEIGHTS: weighted mean over the NAMED sub-metrics present
    (renormalized over their weights); unnamed metrics (chrf_score, multilingual_similarity,
    african_hallucination_probe) are ignored. Other dimensions (cultural_appropriateness,
    bias_fairness): flat mean of all their metric means. None if nothing usable.
    """
    if not metric_means:
        return None
    weights = DEFAULT_METRIC_WEIGHTS.get(dimension)
    if weights:
        present = {m: metric_means[m] for m in weights if m in metric_means}
        total = sum(weights[m] for m in present)
        if not present or total == 0:
            return None
        return sum(metric_means[m] * weights[m] for m in present) / total * 100.0
    vals = list(metric_means.values())
    return sum(vals) / len(vals) * 100.0


def composite_from_metric_means(
    metric_means: dict[str, dict[str, float]],
) -> tuple[dict[str, float | None], float | None]:
    """Return (dimension_scores_0-100, composite_0-100) from {dimension: {metric_name: mean_0-1}},
    applying scoring.engine.DEFAULT_WEIGHTS + DEFAULT_METRIC_WEIGHTS. The composite is a weighted
    mean over the dimensions present, renormalized over their weights (mirrors engine.py). Composite
    is None when no weighted dimension is present."""
    dim_scores: dict[str, float | None] = {
        dim: _dimension_score(dim, mm) for dim, mm in metric_means.items()
    }
    present = {d: s for d, s in dim_scores.items() if s is not None and d in DEFAULT_WEIGHTS}
    if not present:
        return dim_scores, None
    total_w = sum(DEFAULT_WEIGHTS[d] for d in present)
    composite = sum(present[d] * DEFAULT_WEIGHTS[d] for d in present) / total_w
    return dim_scores, composite
