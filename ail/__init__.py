"""
Africa Intelligence Layer (AIL) — AgentifyAfro.ai proprietary.

This module is the moat. Its evaluators implement the AfroEval module
contract but contain Africa-specific logic that no generic benchmark replicates:

  - cultural_appropriateness.py  — rubric-based LLM-judge, calibrated to SME judgment
  - code_switching.py            — Sheng / Pidgin / mixed-language quality scoring
  - hallucination_probes.py      — African-specific fabrication detection

Sprint 2 implements these evaluators. This __init__ exports stubs so the
orchestration layer can import them throughout Sprint 1 without error.

Note: informal_economy.py (cohort logic for informal-sector users) was
archived 2026-06-29 — see ail/informal_economy.archive.py. Its real logic
was rebuilt into evaluators/bias_fairness.py::CohortDisparityEvaluator
instead, since it was never wired into orchestration/dispatcher.py and
would have competed with that implementation of the same dimension.
"""

from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator
from ail.code_switching import (
    LanguagePreservationEvaluator,
    RegisterMatchEvaluator,
    SwitchNaturalnessEvaluator,
)
from ail.hallucination_probes import AfricanHallucinationProbeEvaluator

__all__ = [
    "CulturalAppropriatenessEvaluator",
    "RegisterMatchEvaluator",
    "SwitchNaturalnessEvaluator",
    "LanguagePreservationEvaluator",
    "AfricanHallucinationProbeEvaluator",
]

AIL_EVALUATOR_REGISTRY = [
    CulturalAppropriatenessEvaluator(),
    RegisterMatchEvaluator(),
    SwitchNaturalnessEvaluator(),
    LanguagePreservationEvaluator(),
    AfricanHallucinationProbeEvaluator(),
]
