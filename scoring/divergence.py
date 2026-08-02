"""Judge-divergence signal (LaBSE Phase 1) — pure, unscored.

Compares the local LaBSE ``multilingual_similarity`` against the judge's
``semantic_similarity`` per item. Both are answer-vs-reference similarity, so a
large *residual* gap means an un-biasable model disputes the judge on exactly
that question.

**Per-run offset-centering.** The judge's AnswerRelevancy sits systematically
higher than LaBSE cosine — a ~28–33pt scale offset (measured on real runs), NOT
disagreement. Differencing the raw scores would flag the majority of items on
that offset alone. So we subtract each run's MEDIAN signed gap and flag items
whose *residual* (deviation from the run's typical gap) exceeds the threshold —
isolating genuine per-item disagreement from the scale mismatch.

Weight-0: this NEVER enters the composite — a QA/trust signal only.
"""
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from statistics import median

# RESIDUAL threshold on the 0-100 scale, AFTER per-run median centering.
# Provisional (tune on data): 20 flags ~20% of items on the first real runs,
# vs 56% for a raw |LaBSE-semantic| cut that mostly measured the scale offset.
_DEFAULT_THRESHOLD = 20.0


def _load_threshold() -> float:
    raw = os.getenv("AFROEVAL_DIVERGENCE_THRESHOLD")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_THRESHOLD


DIVERGENCE_THRESHOLD: float = _load_threshold()


def run_divergences(pairs: Mapping, threshold: float | None = None) -> dict:
    """Per-run offset-centered divergence flags, keyed exactly like ``pairs``.

    ``pairs``: ``{key: (labse, semantic)}`` with 0.0-1.0 scores; either may be
    ``None`` (metric unavailable/errored). Returns ``{key: record | None}`` where
    an uncomparable item (either score ``None``) maps to ``None`` and a comparable
    item maps to::

        {"judge_divergence": bool,          # residual STRICTLY exceeds threshold
         "divergence_residual": float,       # |gap - run baseline|, 0-100 scale
         "divergence_delta": float,          # raw |LaBSE - semantic|, 0-100 (reference)
         "run_baseline_offset": float,       # the run's median signed gap, 0-100
         "compared_to": "semantic_similarity"}

    Method: signed gap ``g = semantic - labse`` per comparable item; ``baseline =
    median(g)`` across the run removes the systematic scale offset; ``residual =
    |g - baseline| * 100``; flag when residual is STRICTLY greater than threshold.
    """
    thr = DIVERGENCE_THRESHOLD if threshold is None else threshold
    signed = {
        k: (sem - lab)
        for k, (lab, sem) in pairs.items()
        if lab is not None and sem is not None
    }
    result: dict = dict.fromkeys(pairs)
    if not signed:
        return result
    baseline = median(signed.values())
    for k, g in signed.items():
        residual = round(abs(g - baseline) * 100.0, 1)
        result[k] = {
            "judge_divergence": residual > thr,
            "divergence_residual": residual,
            "divergence_delta": round(abs(g) * 100.0, 1),
            "run_baseline_offset": round(baseline * 100.0, 1),
            "compared_to": "semantic_similarity",
        }
    return result


def count_divergences(flags: Iterable[dict | None]) -> int:
    return sum(1 for f in flags if f and f.get("judge_divergence"))
