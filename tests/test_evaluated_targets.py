"""
Guards the judge-neutrality change (2026-07): Azure OpenAI is removed from the
list of models being EVALUATED, but MUST remain the LLM judge. Today the Azure
judge grades the identical Azure target (a model judging itself); dropping Azure
as a target is the first step toward judge neutrality.

Two invariants:
  (a) The evaluated-target set is exactly {anthropic, openai, gemini} — no Azure.
  (b) The LLM judge is still Azure OpenAI (gpt-4.1-mini).
"""

from types import SimpleNamespace

from api.settings import Settings

# ── (a) Evaluated targets: exactly the three non-Azure providers ──────────────

def test_evaluated_targets_are_exactly_the_three_non_azure_providers():
    from db.models import EVALUATED_PROVIDERS

    assert set(EVALUATED_PROVIDERS) == {"anthropic", "openai", "gemini"}


def test_azure_is_not_an_evaluated_target():
    from db.models import EVALUATED_PROVIDERS

    # Azure stays a known provider *type* (it is the judge), but it must never be
    # one of the models we evaluate/score.
    assert "azure_openai" not in EVALUATED_PROVIDERS


# ── (b) Judge unchanged: still Azure OpenAI / gpt-4.1-mini ────────────────────

def test_azure_remains_the_llm_judge_default():
    # Class-declared defaults, independent of any local .env — the shipped judge
    # configuration is Azure OpenAI gpt-4.1-mini.
    assert Settings.model_fields["ail_judge_provider"].default == "azure_openai"
    assert Settings.model_fields["ail_judge_model"].default == "gpt-4.1-mini"


def test_build_judge_builds_an_azure_backed_judge():
    from orchestration.dispatcher import _build_judge

    cfg = SimpleNamespace(
        ail_judge_provider="azure_openai",
        ail_judge_model="gpt-4.1-mini",
        azure_openai_api_key="test-key",
        azure_openai_endpoint="https://test.openai.azure.com/",
        azure_openai_deployment_name="gpt-4.1-mini",
        azure_openai_api_version="2025-01-01-preview",
        openai_api_key="",
    )

    judge = _build_judge(cfg)

    assert judge is not None
    # The judge scores through the Azure gpt-4.1-mini deployment.
    assert judge._model == "gpt-4.1-mini"
