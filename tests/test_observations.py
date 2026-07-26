"""Tests for reporting.observations.build_key_observations."""

from types import SimpleNamespace

from reporting.observations import build_key_observations


def _sc(**kw):
    base = dict(
        dimension_scores={},
        verdict="Conditional",
        confidence_flag="standard",
        safety_unverified=False,
        african_fabrication_detected=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_names_strongest_and_weakest_dimension():
    sc = _sc(dimension_scores={
        "cultural_appropriateness": 92.0,
        "code_switching_quality":           61.5,
        "safety_robustness":        88.0,
    })
    obs = build_key_observations(sc)
    assert any("Strongest" in o and "Cultural" in o and "92.0" in o for o in obs)
    assert any("Weakest" in o and "Code-Switching" in o and "61.5" in o for o in obs)


def test_flags_dimension_below_pass_threshold():
    sc = _sc(dimension_scores={"code_switching_quality": 55.0, "safety_robustness": 90.0})
    obs = build_key_observations(sc)
    assert any("Code-Switching" in o and "below the pass threshold" in o for o in obs)


def test_reports_active_flags():
    sc = _sc(
        dimension_scores={"safety_robustness": 90.0},
        african_fabrication_detected=True,
        safety_unverified=True,
        confidence_flag="low_coverage",
    )
    joined = " ".join(build_key_observations(sc)).lower()
    assert "fabrication" in joined
    assert "verif" in joined       # "not verified" / "unverified"
    assert "coverage" in joined


def test_reports_safety_veto_when_high_risk_and_safety_below_threshold():
    sc = _sc(
        dimension_scores={"safety_robustness": 12.0, "cultural_appropriateness": 80.0},
        verdict="High-Risk",
    )
    obs = build_key_observations(sc)
    assert any("veto" in o.lower() and "High-Risk" in o for o in obs)


def test_empty_scores_and_no_flags_yields_empty_list():
    assert build_key_observations(_sc()) == []
