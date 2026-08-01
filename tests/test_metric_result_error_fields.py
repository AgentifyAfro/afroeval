"""MetricResult carries the error plumbing columns (G2 — persist the failure flag)."""
import uuid

from db.models import MetricResult


def test_metric_result_has_error_fields_with_safe_defaults():
    m = MetricResult(response_id=uuid.uuid4(), dimension="safety_robustness",
                     metric_name="harmful_content", score=0.0, passed=False)
    assert m.error is False
    assert m.error_cause is None


def test_metric_result_accepts_error_and_cause():
    m = MetricResult(response_id=uuid.uuid4(), dimension="safety_robustness",
                     metric_name="harmful_content", score=1.0, passed=True,
                     error=True, error_cause="content_filter")
    assert m.error is True
    assert m.error_cause == "content_filter"
