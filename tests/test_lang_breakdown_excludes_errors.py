"""Per-language and per-item re-aggregation must drop error rows so they match the engine
(which already excludes them at scoring). Tests the pure grouping/composite helpers, not the DB."""
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


def test_item_dimension_composite_excludes_error_rows():
    # Simulate the per-item dim_scores composite in load_run_items: a real score mixed
    # with an error-fallback score=0.0 row must not drag the composite toward 0.
    dim = "language_performance"
    resp_metrics = [
        {"dimension": dim, "score": 0.8, "error": False},
        {"dimension": dim, "score": 0.0, "error": True},
    ]
    dim_scores = [m["score"] for m in resp_metrics if m["dimension"] == dim and not m["error"]]
    composite = round(sum(dim_scores) / len(dim_scores) * 100, 1) if dim_scores else None
    assert dim_scores == [0.8]
    assert composite == 80.0  # not dragged toward 0.0 by the error row


def test_item_dimension_composite_none_when_only_error_rows():
    # If every metric in a dimension for an item errored, there's no measured value —
    # the composite must be None (blank), not an average that includes the error fallback.
    dim = "language_performance"
    resp_metrics = [{"dimension": dim, "score": 0.0, "error": True}]
    dim_scores = [m["score"] for m in resp_metrics if m["dimension"] == dim and not m["error"]]
    composite = round(sum(dim_scores) / len(dim_scores) * 100, 1) if dim_scores else None
    assert dim_scores == []
    assert composite is None


def test_calibration_automated_by_resp_dim_excludes_error_rows():
    # Simulate the accumulation loop in load_calibration_data: automated MetricResult
    # scores are grouped per (response_id, dimension) for comparison against SME review
    # scores. An error-fallback row (e.g. score=0.0 from a missing-dependency evaluator
    # branch) must not be folded into that automated mean, or it drags the calibration
    # comparison down and produces a false SME<->auto delta.
    class M:
        def __init__(self, response_id, dim, score, error):
            self.response_id, self.dimension, self.score, self.error = response_id, dim, score, error

    resp_id = "resp-1"
    metrics = [
        M(resp_id, "language_performance", 0.9, False),
        M(resp_id, "language_performance", 0.0, True),  # error fallback — must be dropped
    ]
    automated_by_resp_dim: dict = {}
    for m in metrics:
        if getattr(m, "error", False):
            continue
        automated_by_resp_dim.setdefault((m.response_id, m.dimension), []).append(m.score)
    assert automated_by_resp_dim[(resp_id, "language_performance")] == [0.9]
