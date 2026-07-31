"""
Shared LLM-judge utility for AfroEval evaluators.

Wraps an Azure OpenAI (or OpenAI) client and returns structured scores.
Evaluators import this and pass a configured instance at construction time.
The stub fallback in each evaluator activates when no judge is provided,
keeping unit tests independent of API calls.
"""

import json
import logging
import random
import time
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APITimeoutError,
    AzureOpenAI,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BASE_DELAY_S = 1.0

_SYSTEM_PROMPT = (
    "You are an expert evaluation judge for AI systems deployed in African markets. "
    "You evaluate model responses objectively against expected behaviors. "
    "Respond ONLY with a valid JSON object — no markdown, no prose."
)


@dataclass
class JudgeResult:
    """Result of one judge call. error=True marks an infra failure, not a measurement."""
    score: float
    reason: str
    error: bool = False
    error_cause: str | None = None   # rate_limit | content_filter | parse_error | timeout | unavailable


class LLMJudge:
    """
    Calls an LLM to score a model response against a rubric criterion.

    Usage:
        judge = LLMJudge.from_azure(api_key, endpoint, deployment, api_version)
        result = judge.score(criterion_prompt)
    """

    def __init__(self, client: AzureOpenAI | OpenAI, model: str):
        self._client = client
        self._model = model

    @classmethod
    def from_azure(
        cls,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str,
    ) -> "LLMJudge":
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        return cls(client, deployment)

    @classmethod
    def from_openai(cls, api_key: str, model: str = "gpt-4o") -> "LLMJudge":
        return cls(OpenAI(api_key=api_key), model)

    def score(self, criterion: str, fallback: float = 0.5) -> JudgeResult:
        """Ask the judge to evaluate against a criterion prompt.

        The criterion must instruct the model to return {"score": <0.0-1.0>, "reason": "<str>"}.
        On success returns JudgeResult(score, reason). On failure returns a JudgeResult whose
        score is `fallback` (cosmetic — the dispatcher excludes error rows from scoring) with
        error=True and a categorized error_cause. Retries rate-limit / timeout / connection /
        parse errors with exponential backoff; content-filter 400s are non-retryable.
        """
        for attempt in range(_MAX_RETRIES + 1):
            last = attempt == _MAX_RETRIES

            # 1) The API call itself. Kept separate from response parsing below so a
            # client-side exception (rate limit, timeout, content filter, or anything
            # unexpected) is never miscategorized as a malformed-response parse error.
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": criterion},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=256,
                )
            except RateLimitError as exc:
                if last:
                    logger.warning("LLMJudge rate limit — exhausted retries: %s", exc)
                    return JudgeResult(fallback, f"Rate limit after {_MAX_RETRIES} retries: {exc}",
                                       error=True, error_cause="rate_limit")
                self._backoff(attempt)
                continue

            except (APITimeoutError, APIConnectionError) as exc:
                if last:
                    logger.warning("LLMJudge timeout/connection — exhausted retries: %s", exc)
                    return JudgeResult(fallback, f"Timeout/connection after {_MAX_RETRIES} retries: {exc}",
                                       error=True, error_cause="timeout")
                self._backoff(attempt)
                continue

            except BadRequestError as exc:
                cause = "content_filter" if "content_filter" in str(exc).lower() else "unavailable"
                logger.warning("LLMJudge non-retryable (%s): %s", cause, exc)
                return JudgeResult(fallback, f"Judge error ({cause}): {exc}",
                                   error=True, error_cause=cause)

            except Exception as exc:
                logger.warning("LLMJudge call failed: %s", exc)
                return JudgeResult(fallback, f"Judge unavailable: {exc}",
                                   error=True, error_cause="unavailable")

            # 2) Parse the response. Malformed judge output (bad JSON / non-numeric
            # score / unexpected shape) is retried — often transient.
            try:
                raw = completion.choices[0].message.content or "{}"
                data = json.loads(raw)
                score = max(0.0, min(1.0, float(data.get("score", fallback))))
                reason = str(data.get("reason", "No reason provided."))
                return JudgeResult(score, reason)

            except (json.JSONDecodeError, ValueError, TypeError, IndexError, KeyError, AttributeError) as exc:
                if last:
                    logger.warning("LLMJudge parse error — exhausted retries: %s", exc)
                    return JudgeResult(fallback, f"Parse error after {_MAX_RETRIES} retries: {exc}",
                                       error=True, error_cause="parse_error")
                self._backoff(attempt)

        return JudgeResult(fallback, "Judge unavailable: retry loop exhausted",
                           error=True, error_cause="unavailable")

    def _backoff(self, attempt: int) -> None:
        delay = _BASE_DELAY_S * (2 ** attempt) + random.uniform(0, 0.5)
        logger.info("LLMJudge retry %d/%d in %.1fs", attempt + 1, _MAX_RETRIES, delay)
        time.sleep(delay)
