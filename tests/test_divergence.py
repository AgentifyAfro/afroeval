from scoring.divergence import _load_threshold, count_divergences, run_divergences


def test_all_none_when_no_comparable_pairs():
    # either score None -> uncomparable -> None (key preserved)
    out = run_divergences({"x": (None, 0.8), "y": (0.8, None)})
    assert out == {"x": None, "y": None}


def test_centering_flags_only_the_outlier():
    # Four items sit on a ~0.29 scale offset; one item's gap is far larger.
    # median signed gap = 0.29 -> residuals remove the offset; only the outlier flags.
    pairs = {
        "a": (0.60, 0.88),  # gap 0.28
        "b": (0.55, 0.83),  # gap 0.28
        "c": (0.60, 0.90),  # gap 0.30
        "d": (0.20, 0.90),  # gap 0.70  <- genuine outlier
        "e": (0.40, None),  # uncomparable
    }
    out = run_divergences(pairs)  # default residual threshold 20
    assert out["e"] is None
    assert out["a"]["judge_divergence"] is False
    assert out["c"]["judge_divergence"] is False
    assert out["d"]["judge_divergence"] is True
    # baseline (median signed gap) reported on 0-100 scale
    assert out["a"]["run_baseline_offset"] == 29.0
    # residual drives the flag; raw delta kept for reference
    assert out["d"]["divergence_residual"] == 41.0
    assert out["d"]["divergence_delta"] == 70.0
    assert out["d"]["compared_to"] == "semantic_similarity"
    assert count_divergences(out.values()) == 1


def test_residual_threshold_boundary_is_exclusive():
    # gaps 0.10 and 0.50 -> median 0.30 -> both residuals exactly 20.0.
    # default threshold 20 is STRICT >, so neither flags.
    pairs = {"lo": (0.40, 0.50), "hi": (0.30, 0.80)}
    out = run_divergences(pairs)
    assert out["lo"]["divergence_residual"] == 20.0
    assert out["hi"]["divergence_residual"] == 20.0
    assert out["lo"]["judge_divergence"] is False
    assert out["hi"]["judge_divergence"] is False
    assert count_divergences(out.values()) == 0


def test_threshold_param_override():
    # same pair set, explicit lower threshold flips both to flagged
    pairs = {"lo": (0.40, 0.50), "hi": (0.30, 0.80)}
    out = run_divergences(pairs, threshold=15)
    assert out["lo"]["judge_divergence"] is True
    assert out["hi"]["judge_divergence"] is True
    assert count_divergences(out.values()) == 2


def test_count_divergences_ignores_none_and_false():
    flags = [None, {"judge_divergence": False}, {"judge_divergence": True}, {"judge_divergence": True}]
    assert count_divergences(flags) == 2


def test_bad_env_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AFROEVAL_DIVERGENCE_THRESHOLD", "not-a-number")
    assert _load_threshold() == 20.0


def test_valid_env_override(monkeypatch):
    monkeypatch.setenv("AFROEVAL_DIVERGENCE_THRESHOLD", "15")
    assert _load_threshold() == 15.0
