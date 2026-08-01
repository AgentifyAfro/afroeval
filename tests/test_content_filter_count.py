"""A per-run content-filter count feeds the fairness disclosure."""
from console.app import _content_filter_count


def test_counts_only_content_filter_error_rows():
    metrics_by_resp = {
        "r1": [{"error": True, "error_cause": "content_filter"},
               {"error": True, "error_cause": "rate_limit"},
               {"error": False, "error_cause": None}],
        "r2": [{"error": True, "error_cause": "content_filter"}],
    }
    assert _content_filter_count(metrics_by_resp) == 2
