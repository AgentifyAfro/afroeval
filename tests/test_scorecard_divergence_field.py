from db.models import Scorecard


def test_scorecard_has_judge_divergence_count_default_zero():
    sc = Scorecard(run_id=__import__("uuid").uuid4(), composite_score=80.0, verdict="Pass")
    assert sc.judge_divergence_count == 0
