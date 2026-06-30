"""
Sprint 1 test coverage — LLM judge, evaluator injection, connector routing, auth.

All LLM/API calls are mocked; no network required.
"""

from unittest.mock import MagicMock, patch

import pytest

from evaluators.base import MetricOutput
from evaluators.llm_judge import LLMJudge
from evaluators.language_performance import (
    AnswerCompletenessEvaluator,
    FluencyEvaluator,
    SemanticSimilarityEvaluator,
)
from evaluators.hallucination import FaithfulnessEvaluator


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

    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_with_model_uses_deepeval_score(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.9, reason="Strong match")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("prompt", "response", "expected", context={"language": "sw"})
        assert out.score == pytest.approx(0.9)
        assert out.passed is True

    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_with_model_passes_at_0_6(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.6, reason="Adequate")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e")
        assert out.passed is True

    @patch("evaluators.language_performance.AnswerRelevancyMetric")
    def test_with_model_fails_below_0_6(self, mock_metric_cls):
        mock_metric_cls.return_value = MagicMock(score=0.4, reason="Weak")
        ev = SemanticSimilarityEvaluator(model=MagicMock())
        out = ev.evaluate("p", "r", "e")
        assert out.passed is False

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
