# tests/test_dispatcher_divergence.py
"""Divergence is computed per item from the LaBSE + semantic_similarity rows,
written to the multilingual row's extra, and counted onto the scorecard."""
from scoring.divergence import count_divergences, item_divergence


def test_per_item_divergence_and_count():
    # item A: LaBSE 0.2 vs semantic 0.9 -> flagged; item B: 0.85 vs 0.9 -> not
    per_item = {
        "A": {"multilingual_similarity": 0.2, "semantic_similarity": 0.9},
        "B": {"multilingual_similarity": 0.85, "semantic_similarity": 0.9},
        "C": {"semantic_similarity": 0.7},  # no LaBSE -> uncomparable
    }
    flags = {
        k: item_divergence(v.get("multilingual_similarity"), v.get("semantic_similarity"))
        for k, v in per_item.items()
    }
    assert flags["A"]["judge_divergence"] is True
    assert flags["B"]["judge_divergence"] is False
    assert flags["C"] is None
    assert count_divergences(flags.values()) == 1
