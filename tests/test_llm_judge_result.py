"""LLMJudge.score() returns a JudgeResult with a failure channel (G3)."""
import json
from unittest.mock import MagicMock

from openai import BadRequestError, RateLimitError

from evaluators.llm_judge import JudgeResult, LLMJudge


def _judge_with(side_effect):
    client = MagicMock()
    client.chat.completions.create.side_effect = side_effect
    return LLMJudge(client, "test-deploy")


def _ok_completion(payload: dict):
    c = MagicMock()
    c.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return c


def test_success_returns_clean_judgeresult():
    j = _judge_with([_ok_completion({"score": 0.83, "reason": "good"})])
    r = j.score("crit")
    assert isinstance(r, JudgeResult)
    assert r.score == 0.83 and r.reason == "good"
    assert r.error is False and r.error_cause is None


def test_ratelimit_exhausted_is_error_rate_limit(monkeypatch):
    monkeypatch.setattr("evaluators.llm_judge.time.sleep", lambda *_: None)
    err = RateLimitError("429", response=MagicMock(status_code=429), body=None)
    r = _judge_with(err).score("crit", fallback=0.5)
    assert r.error is True and r.error_cause == "rate_limit" and r.score == 0.5


def test_content_filter_400_is_error_content_filter():
    err = BadRequestError("content_filter triggered", response=MagicMock(status_code=400), body=None)
    r = _judge_with(err).score("crit", fallback=1.0)
    assert r.error is True and r.error_cause == "content_filter" and r.score == 1.0


def test_malformed_json_is_error_parse_error(monkeypatch):
    monkeypatch.setattr("evaluators.llm_judge.time.sleep", lambda *_: None)
    bad = MagicMock()
    bad.choices = [MagicMock(message=MagicMock(content="not json"))]
    r = _judge_with(bad).score("crit")
    assert r.error is True and r.error_cause == "parse_error"


def test_unknown_exception_is_error_unavailable():
    r = _judge_with(ValueError("boom")).score("crit")
    assert r.error is True and r.error_cause == "unavailable"
