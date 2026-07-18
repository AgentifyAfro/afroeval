"""
Scorecard reporting module tests.

These tests create stub Scorecard/Run/Assessment objects — no DB access required.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from reporting.generator import generate_scorecard_json, generate_scorecard_pdf

# ── Stub factories ─────────────────────────────────────────────────────────────

def _stub_assessment():
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Test Assessment",
        model_provider="azure_openai",
        model_identifier="gpt-4.1-mini",
        benchmark_pack_ids=["customer_service_yo_v1.0.0"],
    )


def _stub_run(assessment):
    return SimpleNamespace(
        id=uuid.uuid4(),
        assessment_id=assessment.id,
        started_at=datetime(2026, 6, 16, 10, 0, 0),
        completed_at=datetime(2026, 6, 16, 10, 5, 30),
    )


def _stub_scorecard(run):
    return SimpleNamespace(
        id=uuid.uuid4(),
        run_id=run.id,
        composite_score=74.50,
        verdict="Conditional",
        confidence_flag="standard",
        safety_unverified=False,
        african_fabrication_detected=False,
        benchmark_pack_version="customer_service_yo_v1.0.0",
        methodology_version="v1.0",
        created_at=datetime(2026, 6, 16, 10, 5, 30),
        dimension_scores={
            "language_performance": 84.0,
            "cultural_appropriateness": 60.0,
            "hallucination_risk": 90.0,
            "bias_fairness": 75.0,
            "code_switching_quality": 60.0,
            "safety_robustness": 100.0,
        },
        dimension_weights={
            "language_performance": 0.25,
            "cultural_appropriateness": 0.20,
            "hallucination_risk": 0.20,
            "bias_fairness": 0.15,
            "code_switching_quality": 0.10,
            "safety_robustness": 0.10,
        },
        failing_examples=[],
        remediation_roadmap=[
            {
                "priority": "medium",
                "dimension": "cultural_appropriateness",
                "current_score": 60.0,
                "recommendation": "Review failing items for cultural alignment.",
                "estimated_effort": "2–4 weeks",
            },
        ],
        pdf_path=None,
        json_path=None,
    )


# ── PDF tests ──────────────────────────────────────────────────────────────────

class TestGenerateScorecardPDF:

    def test_creates_file_at_expected_path(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        pdf_path = generate_scorecard_pdf(scorecard, run, assessment, output_dir=tmp_path)

        assert Path(pdf_path).exists()
        assert pdf_path.endswith(".pdf")
        assert str(run.id) in pdf_path

    def test_output_is_valid_pdf(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        pdf_path = generate_scorecard_pdf(scorecard, run, assessment, output_dir=tmp_path)

        content = Path(pdf_path).read_bytes()
        assert len(content) > 1024, "PDF should be larger than 1 KB"
        assert content[:4] == b"%PDF", "File must start with PDF magic bytes"

    def test_returns_string_path(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        result = generate_scorecard_pdf(scorecard, run, assessment, output_dir=tmp_path)
        assert isinstance(result, str)

    def test_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        assert not nested.exists()

        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        generate_scorecard_pdf(scorecard, run, assessment, output_dir=nested)
        assert nested.exists()

    def test_handles_safety_veto_verdict(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)
        scorecard.verdict = "High-Risk"
        scorecard.composite_score = 25.0

        pdf_path = generate_scorecard_pdf(scorecard, run, assessment, output_dir=tmp_path)
        assert Path(pdf_path).read_bytes()[:4] == b"%PDF"

    def test_handles_no_remediation_roadmap(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)
        scorecard.remediation_roadmap = []

        pdf_path = generate_scorecard_pdf(scorecard, run, assessment, output_dir=tmp_path)
        assert Path(pdf_path).exists()

    def test_handles_null_completed_at(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        run.completed_at = None
        scorecard = _stub_scorecard(run)

        pdf_path = generate_scorecard_pdf(scorecard, run, assessment, output_dir=tmp_path)
        assert Path(pdf_path).exists()


# ── JSON tests ─────────────────────────────────────────────────────────────────

class TestGenerateScorecardJSON:

    def test_creates_valid_json_file(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)

        content = Path(json_path).read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_json_contains_expected_top_level_keys(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert "afroeval_version" in data
        assert "generated_at" in data
        assert "run" in data
        assert "assessment" in data
        assert "scorecard" in data

    def test_json_scorecard_section_has_composite_score(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["scorecard"]["composite_score"] == pytest.approx(74.5)
        assert data["scorecard"]["verdict"] == "Conditional"
        assert len(data["scorecard"]["dimension_scores"]) == 6

    def test_json_scorecard_section_discloses_safety_unverified(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)
        scorecard.safety_unverified = True

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["scorecard"]["safety_unverified"] is True

    def test_json_safety_unverified_defaults_false(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)   # stub default

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["scorecard"]["safety_unverified"] is False

    def test_json_discloses_single_expert_validated_items(self, tmp_path):
        """Methodology v1.3 rule 10 — Tier 2 items are never reported as dual-validated."""
        assessment = _stub_assessment()
        assessment.benchmark_pack_ids = ["community_health_am_v1.1.0"]
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        disclosure = json.loads(Path(json_path).read_text(encoding="utf-8"))["scorecard"][
            "single_expert_validated_items"
        ]

        assert disclosure["present"] is True
        assert disclosure["count"] == 4
        # Denominator is the scored set (gold + held-out excluded), matching the rule 9 cap.
        assert disclosure["scored_items"] == 11
        assert disclosure["by_pack"]["community_health_am_v1.1.0"]["single_expert_items"] == 4

    def test_json_single_expert_disclosure_absent_for_dual_validated_pack(self, tmp_path):
        """A pack with no Tier 2 items must report clean, not merely omit the field."""
        assessment = _stub_assessment()
        assessment.benchmark_pack_ids = ["community_health_am_v1.0.0"]
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        disclosure = json.loads(Path(json_path).read_text(encoding="utf-8"))["scorecard"][
            "single_expert_validated_items"
        ]

        assert disclosure["present"] is False
        assert disclosure["count"] == 0
        assert disclosure["by_pack"] == {}

    def test_json_single_expert_disclosure_survives_unloadable_pack(self, tmp_path):
        """An unresolvable pack id must not fail the report — the dispatcher already warns."""
        assessment = _stub_assessment()
        assessment.benchmark_pack_ids = ["does_not_exist_v9.9.9", "nonsense"]
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        disclosure = json.loads(Path(json_path).read_text(encoding="utf-8"))["scorecard"][
            "single_expert_validated_items"
        ]

        assert disclosure["present"] is False

    def test_json_scorecard_section_discloses_african_fabrication_detected(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)
        scorecard.african_fabrication_detected = True

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["scorecard"]["african_fabrication_detected"] is True

    def test_json_african_fabrication_detected_defaults_false(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)   # stub default

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["scorecard"]["african_fabrication_detected"] is False

    def test_json_assessment_section_has_model_info(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["assessment"]["model_identifier"] == "gpt-4.1-mini"
        assert data["assessment"]["model_provider"] == "azure_openai"

    def test_json_file_placed_at_run_id_path(self, tmp_path):
        assessment = _stub_assessment()
        run = _stub_run(assessment)
        scorecard = _stub_scorecard(run)

        json_path = generate_scorecard_json(scorecard, run, assessment, output_dir=tmp_path)

        assert str(run.id) in json_path
        assert json_path.endswith(".json")
