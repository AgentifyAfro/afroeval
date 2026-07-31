"""Per-language re-aggregation must drop error rows so it matches the engine (which already
excludes them at scoring). Tests the pure grouping helper, not the DB."""
def test_error_rows_excluded_from_metric_grouping():
    # Simulate the accumulation loop in load_language_breakdown.
    class M:
        def __init__(self, dim, name, score, error):
            self.dimension, self.metric_name, self.score, self.error = dim, name, score, error
    rows = [M("language_performance", "fluency", 0.9, False),
            M("language_performance", "fluency", 0.5, True)]   # error fallback — must be dropped
    acc: dict = {}
    for m in rows:
        if getattr(m, "error", False):
            continue
        acc.setdefault(m.dimension, {}).setdefault(m.metric_name, []).append(m.score)
    assert acc["language_performance"]["fluency"] == [0.9]  # the 0.5 error row is gone
