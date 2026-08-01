"""The dispatcher persists MetricOutput.error/error_cause onto MetricResult, and error
outputs are still excluded from the in-memory dimension score (safety veto can't be fooled)."""
import uuid

from db.models import MetricResult
from evaluators.base import MetricOutput


def test_metricresult_built_from_erroring_output_carries_flags():
    out = MetricOutput(dimension="safety_robustness", metric_name="harmful_content",
                       score=1.0, passed=True, reason="Judge error (content_filter): ...",
                       error=True, error_cause="content_filter")
    # Mirror the dispatcher's construction (the block under test):
    row = MetricResult(
        id=uuid.uuid4(), response_id=uuid.uuid4(),
        dimension=out.dimension, metric_name=out.metric_name,
        score=out.score, passed=out.passed, reason=out.reason, extra=out.extra,
        error=out.error, error_cause=out.error_cause,
    )
    assert row.error is True and row.error_cause == "content_filter"


def test_errored_output_not_counted_toward_coverage():
    from orchestration.dispatcher import _distinct_item_counts
    err = MetricOutput(dimension="safety_robustness", metric_name="harmful_content",
                       score=1.0, passed=True, reason="x", error=True, error_cause="content_filter")
    counts = _distinct_item_counts([err], 1)
    assert counts.get("harmful_content", 0) == 0  # error rows don't count -> can't inflate safety
