"""Judge-divergence signal (LaBSE Phase 1) — pure, unscored.

Compares the local LaBSE multilingual_similarity against the judge's
semantic_similarity for one item. Both are answer-vs-reference similarity, so a
large gap means an un-biasable model disputes the judge on exactly that question.
Weight-0: this NEVER enters the composite — it is a QA/trust signal only.
"""
from __future__ import annotations

import os
from collections.abc import Iterable

_DEFAULT_THRESHOLD = 30.0  # on the 0-100 scale; provisional, tune on data


def _load_threshold() -> float:
    raw = os.getenv("AFROEVAL_DIVERGENCE_THRESHOLD")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_THRESHOLD


DIVERGENCE_THRESHOLD: float = _load_threshold()


def item_divergence(
    labse: float | None,
    semantic: float | None,
    threshold: float | None = None,
) -> dict | None:
    """Return the divergence record for one item, or None if uncomparable.

    labse / semantic are 0.0-1.0 metric scores. delta is on the 0-100 scale.
    "Sharp" divergence is delta STRICTLY greater than the threshold.
    """
    if labse is None or semantic is None:
        return None
    thr = DIVERGENCE_THRESHOLD if threshold is None else threshold
    delta = round(abs(labse - semantic) * 100.0, 1)
    return {
        "judge_divergence": delta > thr,
        "divergence_delta": delta,
        "compared_to": "semantic_similarity",
    }


def count_divergences(flags: Iterable[dict | None]) -> int:
    return sum(1 for f in flags if f and f.get("judge_divergence"))
