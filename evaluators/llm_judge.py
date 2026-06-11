"""
Shared LLM-judge utility for AfroEval evaluators.

Wraps an Azure OpenAI (or OpenAI) client and returns structured scores.
Evaluators import this and pass a configured instance at construction time.
The stub fallback in each evaluator activates when no judge is provided,
keeping unit tests independent of API calls.
"""

import json
import logging

from openai import AzureOpenAI, OpenAI

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert evaluation judge for AI systems deployed in African markets. "
    "You evaluate model responses objectively against expected behaviors. "
    "Respond ONLY with a valid JSON object — no markdown, no prose."
)


class LLMJudge:
    """
    Calls an LLM to score a model response against a rubric criterion.

    Usage:
        judge = LLMJudge.from_azure(api_key, endpoint, deployment, api_version)
        score, reason = judge.score(criterion_prompt)
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

    def score(self, criterion: str, fallback: float = 0.5) -> tuple[float, str]:
        """
        Ask the judge to evaluate based on a criterion prompt.

        The criterion prompt must instruct the model to return:
            {"score": <float 0.0–1.0>, "reason": "<string>"}

        Returns (score, reason). On any error returns (fallback, error_message).
        """
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
            raw = completion.choices[0].message.content or "{}"
            data = json.loads(raw)
            score = float(data.get("score", fallback))
            reason = str(data.get("reason", "No reason provided."))
            return max(0.0, min(1.0, score)), reason
        except Exception as exc:
            logger.warning("LLMJudge call failed: %s", exc)
            return fallback, f"Judge unavailable: {exc}"
