from scoring.divergence import _load_threshold, count_divergences, item_divergence


def test_none_when_either_side_missing():
    assert item_divergence(None, 0.8) is None
    assert item_divergence(0.8, None) is None


def test_flags_when_delta_exceeds_threshold():
    # LaBSE 0.20 vs semantic 0.90 -> delta 70 > 30 -> flagged
    r = item_divergence(0.20, 0.90)
    assert r["judge_divergence"] is True
    assert r["divergence_delta"] == 70.0
    assert r["compared_to"] == "semantic_similarity"


def test_no_flag_within_threshold():
    # delta 10 < 30 -> not flagged, but still reported
    r = item_divergence(0.80, 0.90)
    assert r["judge_divergence"] is False
    assert r["divergence_delta"] == 10.0


def test_threshold_boundary_is_exclusive():
    # exactly at threshold is NOT "sharp"
    r = item_divergence(0.30, 0.60)  # delta 30.0
    assert r["divergence_delta"] == 30.0
    assert r["judge_divergence"] is False


def test_count_divergences_ignores_none_and_false():
    flags = [None, {"judge_divergence": False}, {"judge_divergence": True}, {"judge_divergence": True}]
    assert count_divergences(flags) == 2


def test_bad_env_value_falls_back_to_default(monkeypatch):
    # Malformed env value -> return default 30.0
    monkeypatch.setenv("AFROEVAL_DIVERGENCE_THRESHOLD", "not-a-number")
    assert _load_threshold() == 30.0


def test_valid_env_override(monkeypatch):
    # Valid env override -> return parsed value
    monkeypatch.setenv("AFROEVAL_DIVERGENCE_THRESHOLD", "15")
    assert _load_threshold() == 15.0


def test_threshold_param_override():
    # Explicit threshold param is honored
    # delta 30.0 > 10 -> True (whereas with default 30.0 it is False)
    r = item_divergence(0.30, 0.60, threshold=10)
    assert r["judge_divergence"] is True
    assert r["divergence_delta"] == 30.0
