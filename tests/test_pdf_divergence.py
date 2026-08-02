"""The persisted judge_divergence_count appears in the generated PDF report."""
from reporting.generator import _divergence_line


def test_divergence_line_present_when_flagged():
    assert "2" in _divergence_line(2)
    assert "judge" in _divergence_line(2).lower()


def test_divergence_line_empty_when_zero():
    assert _divergence_line(0) == ""
