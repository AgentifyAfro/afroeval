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


def test_deepeval_async_mode_defaults_off():
    # Off preserves the safe serial behavior; enable only with Azure TPM headroom.
    assert Settings.model_fields["deepeval_async_mode"].default is False


def test_deepeval_async_mode_is_overridable():
    assert Settings(deepeval_async_mode=True).deepeval_async_mode is True


def test_dispatcher_reads_limits_from_settings():
    from orchestration.dispatcher import _concurrency_limits
    cfg = SimpleNamespace(judge_max_concurrency=5, deepeval_max_concurrency=2)
    assert _concurrency_limits(cfg) == (5, 2)


def test_eval_pool_is_at_least_the_semaphore_totals():
    # The eval thread pool must never be smaller than judge + deepeval concurrency, or the
    # pool (not the Azure-TPM-bounded semaphores) becomes the real throttle — the exact
    # trap the CPU-sized default asyncio.to_thread pool caused on low-vCPU Cloud hosts.
    from orchestration.dispatcher import _eval_pool_size
    for judge_n, deepeval_n in [(3, 1), (10, 8), (16, 12)]:
        assert _eval_pool_size(judge_n, deepeval_n) >= judge_n + deepeval_n
