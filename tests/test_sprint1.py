"""
Sprint 1 test coverage — LLM judge, evaluator injection, connector routing, auth.

All LLM/API calls are mocked; no network required.
"""

import importlib.util
from unittest.mock import MagicMock, patch

import pytest

from evaluators.base import MetricOutput
from evaluators.hallucination import FaithfulnessEvaluator
from evaluators.language_performance import (
    AnswerCompletenessEvaluator,
    FluencyEvaluator,
    SemanticSimilarityEvaluator,
)
from evaluators.llm_judge import LLMJudge

# DeepEval is an optional [eval] extra, intentionally absent from the default
# install (see pyproject). When it is missing the evaluators use their stub
# fallback, so tests asserting a DeepEval-path score only apply when it is present.
_needs_deepeval = pytest.mark.skipif(
    importlib.util.find_spec("deepeval") is None,
    reason="deepeval not installed (optional [eval] extra); evaluator uses stub fallback",
)

# ── LLMJudge ──────────────────────────────────────────────────────────────────

class TestLLMJudge:

    def _make_judge(self, score: float, reason: str) -> LLMJudge:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f'{{"score": {score}, "reason": "{reason}"}}'  ))]
        )
        return LLMJudge(client=mock_client, model="mock")

    def test_score_returns_float_and_reason(self):
        judge = self._make_judge(0.85, "Good semantic match")
        score, reason = judge.score("some criterion")
        assert score == pytest.approx(0.85)
        assert "Good semantic match" in reason

    def test_score_clamps_above_1(self):
        judge = self._make_judge(1.5, "Too high")
        score, _ = judge.score("criterion")
        assert score == 1.0

    def test_score_clamps_below_0(self):
        judge = self._make_judge(-0.3, "Negative")
        score, _ = judge.score("criterion")
        assert score == 0.0

    def test_score_returns_fallback_on_api_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API down")
        judge = LLMJudge(client=mock_client, model="mock")
        score, reason = judge.score("criterion", fallback=0.5)
        assert score == 0.5
        assert "Judge unavailable" in reason

    def test_score_returns_fallback_on_bad_json(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json at all"))]
        )
        judge = LLMJudge(client=mock_client, model="mock")
        score, reason = judge.score("criterion", fallback=0.42)
        assert score == pytest.approx(0.42)


# ── SemanticSimilarityEvaluator ───────────────────────────────────────────────

class TestSemanticSimilarityEvaluator:

    def test_stub_fallback_when_no_judge(self):
        ev = SemanticSimilarityEvaluator()
        out = ev.evaluate(
            prompt="Test prompt",
            model_response="send money m-pesa",
            expected_behavior="send money using m-pesa steps",
        )
        assert isinstance(out, MetricOutput)
        assert out.dimension == "language_performance"
        assert out.metric_name == "semantic_similarity"
        assert 0.0 <= out.score <= 1.0

    def test_stub_perfect_overlap(self):
        ev = SemanticSimilarityEvaluator()
        expected = "the cat sat on the mat"
        out = ev.evaluate("p", expected, expected)
        assert out.score == pytest.approx(1.0)

    def test_stub_zero_overlap(self):
        ev = SemanticSimilarityEvaluator()
        out = ev.evaluate("p", "banana orange apple", "cat dog fish")
        assert out.score == pytest.approx(0.0)

    @_needs_deepeval
    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_with_model_uses_deepeval_score(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.9, reason="Strong match")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("prompt", "response", "expected", context={"language": "sw"})
        assert out.score == pytest.approx(0.9)
        assert out.passed is True

    @_needs_deepeval
    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_with_model_passes_at_0_6(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.6, reason="Adequate")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e")
        assert out.passed is True

    @_needs_deepeval
    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_with_model_fails_below_0_6(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.4, reason="Weak")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e")
        assert out.passed is False

    @_needs_deepeval
    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_metric_error_falls_back_gracefully(self, mock_metric_cls):
        mock_metric_cls.return_value.measure.side_effect = Exception("rate limited")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e")
        assert out.score == pytest.approx(0.5)
        assert "unavailable" in out.reason.lower()


# ── AnswerCompletenessEvaluator ───────────────────────────────────────────────

class TestAnswerCompletenessEvaluator:

    def test_stub_nonempty_response_scores_0_5(self):
        ev = AnswerCompletenessEvaluator()
        out = ev.evaluate("p", "some answer", "expected")
        assert out.score == pytest.approx(0.5)
        assert out.passed is True

    def test_stub_empty_response_scores_0(self):
        ev = AnswerCompletenessEvaluator()
        out = ev.evaluate("p", "   ", "expected")
        assert out.score == pytest.approx(0.0)
        assert out.passed is False

    @_needs_deepeval
    @patch("evaluators.language_performance.GEval")
    def test_with_model_uses_deepeval_score(self, mock_geval_cls):
        mock_geval_cls.return_value = MagicMock(score=0.75, reason="Most elements present")
        ev = AnswerCompletenessEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e")
        assert out.score == pytest.approx(0.75)


# ── FluencyEvaluator ───────────────────────────────────────────────────────────

class TestFluencyEvaluator:

    def test_stub_nonempty_response_scores_0_5(self):
        ev = FluencyEvaluator()
        out = ev.evaluate("p", "some answer", "expected")
        assert out.score == pytest.approx(0.5)
        assert out.passed is False  # 0.5 < 0.6 pass bar

    def test_with_judge_uses_llm_score(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"score": 0.9, "reason": "Fluent and natural"}'))]
        )
        judge = LLMJudge(client=mock_client, model="mock")
        ev = FluencyEvaluator(judge=judge)
        out = ev.evaluate("p", "r", "e", context={"language": "yo"})
        assert out.score == pytest.approx(0.9)
        assert out.passed is True

    def test_with_judge_fails_below_0_6(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"score": 0.4, "reason": "Awkward phrasing"}'))]
        )
        judge = LLMJudge(client=mock_client, model="mock")
        ev = FluencyEvaluator(judge=judge)
        out = ev.evaluate("p", "r", "e")
        assert out.passed is False


# ── FaithfulnessEvaluator ─────────────────────────────────────────────────────

class TestFaithfulnessEvaluator:

    def test_stub_no_fabrication_signals_scores_0_8(self):
        ev = FaithfulnessEvaluator()
        out = ev.evaluate("p", "M-Pesa charges KES 11 for KES 500.", "KES 11 fee for KES 500")
        assert out.score == pytest.approx(0.8)
        assert out.passed is True

    def test_stub_fabrication_signal_scores_0_4(self):
        ev = FaithfulnessEvaluator()
        out = ev.evaluate("p", "As of my knowledge cutoff, the fee is KES 11.", "expected")
        assert out.score == pytest.approx(0.4)
        assert out.passed is False

    @_needs_deepeval
    @patch("evaluators.hallucination.FaithfulnessMetric")
    def test_with_model_uses_deepeval_score(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.95, reason="Fully faithful")
        ev = FaithfulnessEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e", context={"domain": "mobile_money"})
        assert out.score == pytest.approx(0.95)
        assert out.passed is True


# ── Connector routing ─────────────────────────────────────────────────────────

class TestConnectorRouting:

    def test_azure_provider_returns_azure_connector(self):
        from orchestration.dispatcher import _build_connector

        cfg = MagicMock()
        cfg.azure_openai_api_key = "test-key"
        cfg.azure_openai_endpoint = "https://test.openai.azure.com/"
        cfg.azure_openai_deployment_name = "gpt-4.1-mini"
        cfg.azure_openai_api_version = "2025-01-01-preview"

        with patch("ingestion.azure_openai_connector.AzureOpenAI"):
            connector = _build_connector("azure_openai", cfg)
            from ingestion.azure_openai_connector import AzureOpenAIConnector
            assert isinstance(connector, AzureOpenAIConnector)

    def test_openai_provider_returns_openai_connector(self):
        from orchestration.dispatcher import _build_connector

        cfg = MagicMock()
        cfg.openai_api_key = "sk-test"
        cfg.openai_default_model = "gpt-4o"

        with patch("ingestion.openai_connector.OpenAI"):
            connector = _build_connector("openai", cfg)
            from ingestion.openai_connector import OpenAIConnector
            assert isinstance(connector, OpenAIConnector)

    def test_anthropic_provider_returns_anthropic_connector(self):
        from orchestration.dispatcher import _build_connector

        cfg = MagicMock()
        cfg.anthropic_api_key = "sk-ant-test"
        cfg.anthropic_default_model = "claude-haiku-4-5-20251001"

        with patch("ingestion.anthropic_connector.Anthropic"):
            connector = _build_connector("anthropic", cfg)
            from ingestion.anthropic_connector import AnthropicConnector
            assert isinstance(connector, AnthropicConnector)

    def test_unknown_provider_raises(self):
        from orchestration.dispatcher import _build_connector
        # "gemini" is now a supported provider (added Sprint: Gemini connector),
        # so use a genuinely unknown provider to exercise the error path.
        with pytest.raises(ValueError, match="Unsupported model_provider"):
            _build_connector("nonexistent_provider", MagicMock())

    def test_jsonl_provider_raises_with_clear_message(self):
        from orchestration.dispatcher import _build_connector
        with pytest.raises(ValueError, match="JSONL upload"):
            _build_connector("jsonl_upload", MagicMock())


# ── Coverage counting ──────────────────────────────────────────────────────────

class TestDistinctItemCounts:
    """item_counts feeds the low_coverage confidence flag, which means 'fewer than
    MIN_ITEMS_PER_DIMENSION distinct ITEMS were assessed' — not 'fewer than N
    evaluator outputs'. With multiple sub-metrics per dimension, per-output
    counting inflates coverage by the evaluator count and hides genuine low coverage."""

    def _out(self, dimension, metric_name, applicable=True):
        return MetricOutput(
            dimension=dimension, metric_name=metric_name,
            score=0.8, passed=True, applicable=applicable,
        )

    def test_counts_distinct_items_not_outputs(self):
        from orchestration.dispatcher import _distinct_item_counts
        # 2 items, 3 evaluators per item (flattened item-major: item0 x3, item1 x3).
        evaluators = ["register_match", "switch_naturalness", "language_preservation"]
        outputs = [
            self._out("code_switching_quality", m)
            for _item in range(2) for m in evaluators
        ]
        counts = _distinct_item_counts(outputs, n_evaluators=3)
        assert counts["code_switching_quality"] == 2  # distinct items, not 6 outputs

    def test_not_applicable_outputs_do_not_count(self):
        from orchestration.dispatcher import _distinct_item_counts
        evaluators = ["register_match", "switch_naturalness", "language_preservation"]
        # item0 applicable, item1 entirely not-applicable (monolingual).
        outputs = (
            [self._out("code_switching_quality", m) for m in evaluators]
            + [self._out("code_switching_quality", m, applicable=False) for m in evaluators]
        )
        counts = _distinct_item_counts(outputs, n_evaluators=3)
        assert counts["code_switching_quality"] == 1

    def test_multiple_dimensions_counted_independently(self):
        from orchestration.dispatcher import _distinct_item_counts
        # 1 item, 2 evaluators: one language_performance, one safety_robustness.
        outputs = [
            self._out("language_performance", "semantic_similarity"),
            self._out("safety_robustness", "harmful_content"),
        ]
        counts = _distinct_item_counts(outputs, n_evaluators=2)
        assert counts["language_performance"] == 1
        assert counts["safety_robustness"] == 1


# ── Connector rate-limit retry ──────────────────────────────────────────────
# Model connectors used to return an empty response on the first 429, which
# silently wrote empty rows (the gpt-4o burst that produced 107/120 empties).
# retry_on_rate_limit adds exponential backoff so transient rate limits recover.

class TestRateLimitRetry:

    def test_is_rate_limit_error_detects_429_and_variants(self):
        from ingestion.base import is_rate_limit_error
        assert is_rate_limit_error(Exception("Error code: 429 - too many requests"))
        assert is_rate_limit_error(Exception("RESOURCE_EXHAUSTED"))
        assert is_rate_limit_error(Exception("rate limit exceeded"))

        class WithStatus(Exception):
            status_code = 429
        assert is_rate_limit_error(WithStatus())

    def test_is_rate_limit_error_excludes_hard_quota_and_generic(self):
        from ingestion.base import is_rate_limit_error
        # Hard quota exhaustion is not transient — must NOT be retried.
        assert is_rate_limit_error(Exception("429 insufficient_quota: check billing")) is False
        assert is_rate_limit_error(Exception("404 model not found")) is False
        assert is_rate_limit_error(Exception("connection reset")) is False

    def test_retry_succeeds_after_transient_rate_limits(self):
        from ingestion.base import retry_on_rate_limit
        calls = {"n": 0}
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise Exception("Error code: 429 - rate limit")
            return "ok"
        result = retry_on_rate_limit(flaky, base_delay=0, sleep=lambda _s: None)
        assert result == "ok"
        assert calls["n"] == 3

    def test_retry_reraises_after_exhausting_attempts(self):
        from ingestion.base import retry_on_rate_limit
        calls = {"n": 0}
        def always_429():
            calls["n"] += 1
            raise Exception("Error code: 429 - rate limit")
        with pytest.raises(Exception, match="429"):
            retry_on_rate_limit(always_429, max_retries=2, base_delay=0, sleep=lambda _s: None)
        assert calls["n"] == 3  # initial + 2 retries

    def test_retry_does_not_retry_non_rate_limit(self):
        from ingestion.base import retry_on_rate_limit
        calls = {"n": 0}
        def boom():
            calls["n"] += 1
            raise ValueError("404 not found")
        with pytest.raises(ValueError):
            retry_on_rate_limit(boom, base_delay=0, sleep=lambda _s: None)
        assert calls["n"] == 1  # no retries for non-rate-limit errors


# ── Auth middleware ───────────────────────────────────────────────────────────

class TestAuthMiddleware:

    def test_no_key_returns_401(self, client):
        # client fixture sends the correct key; create a bare client for this test
        from fastapi.testclient import TestClient

        from api.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        resp = bare.get("/v1/assessments")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        from fastapi.testclient import TestClient

        from api.main import app
        bad = TestClient(app, headers={"X-API-Key": "wrong-key"}, raise_server_exceptions=False)
        resp = bad.get("/v1/assessments")
        assert resp.status_code == 401

    def test_health_is_public(self, client):
        from fastapi.testclient import TestClient

        from api.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        resp = bare.get("/v1/health")
        assert resp.status_code == 200

    def test_correct_key_allows_access(self, client):
        resp = client.get("/v1/assessments")
        assert resp.status_code == 200


# ── Rate-limit error flag propagation ────────────────────────────────────────

def test_semantic_similarity_rate_limit_sets_error_flag():
    """Rate-limit fallback must set error=True, not silently write 0.5 as a real score."""
    from unittest.mock import MagicMock, patch

    from evaluators.language_performance import SemanticSimilarityEvaluator
    mock_model = MagicMock()
    ev = SemanticSimilarityEvaluator(model=mock_model)
    rate_exc = Exception("RetryError[<Future raised RateLimitError>]")
    with patch("evaluators.language_performance.AnswerRelevancyMetric") as MockMetric, \
         patch("evaluators.language_performance._time.sleep"):  # skip real waits in tests
        MockMetric.return_value.measure.side_effect = rate_exc
        result = ev.evaluate("p", "r", "e")
    assert result.error is True
    assert result.score == 0.5


def test_faithfulness_rate_limit_sets_error_flag():
    """FaithfulnessEvaluator rate-limit fallback must set error=True."""
    from unittest.mock import MagicMock, patch

    from evaluators.hallucination import FaithfulnessEvaluator
    mock_model = MagicMock()
    ev = FaithfulnessEvaluator(model=mock_model)
    rate_exc = Exception("RetryError[<Future raised RateLimitError>]")
    with patch("evaluators.hallucination.FaithfulnessMetric") as MockMetric, \
         patch("evaluators.hallucination._time.sleep"):  # skip real waits in tests
        MockMetric.return_value.measure.side_effect = rate_exc
        result = ev.evaluate("p", "r", "e")
    assert result.error is True
    assert result.score == 0.5


# ── MetricOutput.error field ──────────────────────────────────────────────────

def test_metric_output_error_field_defaults_false():
    from evaluators.base import MetricOutput
    out = MetricOutput(dimension="d", metric_name="m", score=0.5, passed=False, reason="r")
    assert out.error is False


def test_metric_output_error_field_can_be_set():
    from evaluators.base import MetricOutput
    out = MetricOutput(dimension="d", metric_name="m", score=0.5, passed=False, reason="r", error=True)
    assert out.error is True
