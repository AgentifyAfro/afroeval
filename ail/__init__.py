"""
Africa Intelligence Layer (AIL) — AgentifyAfro.ai proprietary.

This module is the moat. Its evaluators implement the AfroEval module
contract but contain Africa-specific logic that no generic benchmark replicates:

  - cultural_appropriateness.py  — rubric-based LLM-judge, calibrated to SME judgment
  - code_switching.py            — Sheng / Pidgin / mixed-language quality scoring
  - hallucination_probes.py      — African-specific fabrication detection
  - informal_economy.py          — cohort logic for informal-sector users

Sprint 2 implements these evaluators. This __init__ exports stubs so the
orchestration layer can import them throughout Sprint 1 without error.
"""

from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator
from ail.code_switching import CodeSwitchingEvaluator
from ail.hallucination_probes import AfricanHallucinationProbeEvaluator
from ail.informal_economy import InformalEconomyCohortEvaluator

__all__ = [
    "CulturalAppropriatenessEvaluator",
    "CodeSwitchingEvaluator",
    "AfricanHallucinationProbeEvaluator",
    "InformalEconomyCohortEvaluator",
]

AIL_EVALUATOR_REGISTRY = [
    CulturalAppropriatenessEvaluator(),
    CodeSwitchingEvaluator(),
    AfricanHallucinationProbeEvaluator(),
    InformalEconomyCohortEvaluator(),
]
