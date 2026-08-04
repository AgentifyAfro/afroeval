import uuid

from db.models import Scorecard


def test_scorecard_judge_divergence_count_defaults_to_none():
    """Nullable by design (gap G7): a fresh Scorecard has no divergence count until the
    dispatcher sets one. NULL = 'not computed' (LaBSE unavailable), distinct from 0 =
    'computed, none found' — so the field must NOT default to 0."""
    sc = Scorecard(run_id=uuid.uuid4(), composite_score=80.0, verdict="Pass")
    assert sc.judge_divergence_count is None
