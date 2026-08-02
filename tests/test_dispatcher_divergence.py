# tests/test_dispatcher_divergence.py
"""The dispatcher builds per-item (LaBSE, semantic_similarity) pairs and calls
run_divergences (per-run centered): only genuine outliers flag after the scale
offset is removed, and the count lands on the scorecard."""
from scoring.divergence import count_divergences, run_divergences


def test_dispatcher_pairs_centered_flagging():
    # mirrors the dispatcher's `_div_pairs`: {item_idx: (labse, semantic)}.
    # None on either side (metric errored/absent) -> uncomparable.
    pairs = {
        0: (0.60, 0.88),   # gap 0.28  (on the scale offset)
        1: (0.55, 0.83),   # gap 0.28
        2: (0.60, 0.90),   # gap 0.30
        3: (0.20, 0.90),   # gap 0.70  <- genuine outlier
        4: (0.40, None),   # semantic absent -> uncomparable
    }
    flags = run_divergences(pairs)
    assert flags[4] is None
    assert flags[3]["judge_divergence"] is True
    assert flags[0]["judge_divergence"] is False
    assert count_divergences(flags.values()) == 1
    # the record the dispatcher copy-merges into the multilingual row's `extra`
    assert set(flags[3]) >= {
        "judge_divergence", "divergence_residual", "run_baseline_offset", "compared_to",
    }
