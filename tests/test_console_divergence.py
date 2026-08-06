"""Divergence count has exactly one implementation (gaps G6 / DEAD-1).

This file used to test `console/app.py::_divergence_item_count`, a second implementation
of the per-run divergence count that recomputed it from each row's `extra` JSON. G6
switched the console to read the persisted `Scorecard.judge_divergence_count` — the value
the dispatcher computed under the correct error filter — leaving that function defined,
uncalled, and free to drift from the number the PDF reports. DEAD-1 removed it.

The test now guards the property rather than the function: one source of truth, computed
once by the dispatcher, read by both the console and the report. The counting logic itself
is covered in tests/test_divergence.py and tests/test_dispatcher_divergence.py.
"""
from pathlib import Path

CONSOLE_APP = Path(__file__).resolve().parent.parent / "console" / "app.py"


def test_console_has_no_second_divergence_count_implementation():
    """If this fails, a recompute-from-rows helper has been reintroduced alongside the
    persisted column — the exact pattern G6 removed. The console and the PDF would then
    derive the same client-facing number two different ways, under different filters: the
    dispatcher counts only items where BOTH sides are non-error, while a naive recompute
    counts any row carrying a truthy flag."""
    source = CONSOLE_APP.read_text(encoding="utf-8")
    assert "_divergence_item_count" not in source, (
        "console/app.py must read Scorecard.judge_divergence_count, not recompute the "
        "divergence count from metric rows (gap G6)."
    )


def test_console_reads_the_persisted_divergence_column():
    """The stored value must remain the one the console renders, so console and PDF can
    never disagree on a client-facing number."""
    source = CONSOLE_APP.read_text(encoding="utf-8")
    assert "judge_divergence_count" in source, (
        "console/app.py no longer references the persisted divergence count column"
    )
