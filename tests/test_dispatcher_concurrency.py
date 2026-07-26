"""Azure judge / DeepEval concurrency is env-tunable.

Operators with Azure TPM headroom can raise it to speed up runs; the defaults
preserve the safe, hard-won values (judge 3-wide, DeepEval 1-wide) that avoid the
429 storms higher concurrency previously caused.
"""

from types import SimpleNamespace

from api.settings import Settings


def test_concurrency_defaults_match_previous_hardcoded_values():
    assert Settings.model_fields["judge_max_concurrency"].default == 3
    assert Settings.model_fields["deepeval_max_concurrency"].default == 1


def test_concurrency_is_overridable():
    s = Settings(judge_max_concurrency=8, deepeval_max_concurrency=2)
    assert (s.judge_max_concurrency, s.deepeval_max_concurrency) == (8, 2)


def test_dispatcher_reads_limits_from_settings():
    from orchestration.dispatcher import _concurrency_limits
    cfg = SimpleNamespace(judge_max_concurrency=5, deepeval_max_concurrency=2)
    assert _concurrency_limits(cfg) == (5, 2)
