"""
Core data models for AfroEval Scorecard™.
All tables are defined here; Alembic reads from this module.
"""

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, Relationship, SQLModel


# ── Enumerations ─────────────────────────────────────────────────────────────

class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelProvider(str, enum.Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    JSONL_UPLOAD = "jsonl_upload"


class VerdictBand(str, enum.Enum):
    DEPLOYMENT_READY = "Deployment-Ready"    # 80–100
    CONDITIONAL = "Conditional"              # 60–79
    NOT_READY = "Not-Ready"                  # 40–59
    HIGH_RISK = "High-Risk"                  # 0–39


class BenchmarkDomain(str, enum.Enum):
    MOBILE_MONEY = "mobile_money"
    CUSTOMER_SERVICE = "customer_service"
    COMMUNITY_HEALTH = "community_health"
    AGRICULTURE = "agriculture"
    GOVERNMENT = "government"
    REMITTANCE = "remittance"


class AnchorLanguage(str, enum.Enum):
    SWAHILI = "sw"
    YORUBA = "yo"
    AMHARIC = "am"
    HAUSA = "ha"
    ZULU = "zu"
    SHENG = "sheng"   # Nairobi code-switch variety
    OROMO = "om"      # Afaan Oromoo — Oromia (Ethiopia/Kenya)
    SOMALI = "so"     # Af Soomaali — Somalia/Djibouti/Horn of Africa
    ENGLISH = "en"    # US English — high-resource baseline for comparative evaluation


# ── Benchmark models ──────────────────────────────────────────────────────────

class BenchmarkPack(SQLModel, table=True):
    """Versioned collection of benchmark items for one evaluation dimension."""
    __tablename__ = "benchmark_packs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    version: str = Field(index=True)          # e.g. "v1.0.0"
    language: str                              # AnchorLanguage value
    domain: str                               # BenchmarkDomain value
    item_count: int = 0
    is_held_out: bool = False                 # True → never published/transmitted
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata_: dict[str, Any] = Field(default_factory=dict, sa_column=Column("metadata", JSON))

    items: list["BenchmarkItem"] = Relationship(back_populates="pack")


class BenchmarkItem(SQLModel, table=True):
    """Single SME-validated test case."""
    __tablename__ = "benchmark_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    pack_id: uuid.UUID = Field(foreign_key="benchmark_packs.id", index=True)

    prompt: str                                # Input to the model
    expected_behavior: str                     # What a correct response looks like
    language: str
    domain: str
    cohort: str = ""                          # e.g. "informal_economy", "formal"
    provenance: str = ""                      # Source scenario / real deployment reference
    sme_author_id: str = ""
    validation_count: int = 0
    irr_score: float | None = None            # Inter-rater reliability
    is_gold: bool = False                     # Hidden calibration item
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    pack: BenchmarkPack | None = Relationship(back_populates="items")


# ── Assessment / Run models ───────────────────────────────────────────────────

class Assessment(SQLModel, table=True):
    """Operator-configured evaluation job (one model, one benchmark pack set)."""
    __tablename__ = "assessments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    model_provider: str                       # ModelProvider value
    model_identifier: str                     # e.g. "gpt-4o", deployment name
    benchmark_pack_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "operator"

    runs: list["Run"] = Relationship(back_populates="assessment")


class Run(SQLModel, table=True):
    """Single execution of an Assessment."""
    __tablename__ = "runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    assessment_id: uuid.UUID = Field(foreign_key="assessments.id", index=True)
    status: str = Field(default=RunStatus.PENDING)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    assessment: Optional[Assessment] = Relationship(back_populates="runs")
    responses: list["ModelResponse"] = Relationship(back_populates="run")
    scorecard: Optional["Scorecard"] = Relationship(back_populates="run")


class ModelResponse(SQLModel, table=True):
    """Raw model output for one benchmark item in a run."""
    __tablename__ = "model_responses"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="runs.id", index=True)
    item_id: uuid.UUID = Field(foreign_key="benchmark_items.id", index=True)
    raw_output: str
    latency_ms: int | None = None
    tokens_used: int | None = None
    cost_usd: float | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    run: Optional[Run] = Relationship(back_populates="responses")
    metric_results: list["MetricResult"] = Relationship(back_populates="response")
    reviews: list["ResponseReview"] = Relationship(back_populates="response")


class MetricResult(SQLModel, table=True):
    """Score from one evaluator on one ModelResponse."""
    __tablename__ = "metric_results"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    response_id: uuid.UUID = Field(foreign_key="model_responses.id", index=True)
    dimension: str                            # e.g. "language_performance"
    metric_name: str                          # e.g. "semantic_similarity"
    score: float                              # 0.0–1.0 (normalized before composite)
    passed: bool
    reason: str = ""                          # Evidence / explanation
    evaluator_version: str = "0.1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    response: Optional[ModelResponse] = Relationship(back_populates="metric_results")


class ResponseReview(SQLModel, table=True):
    """SME human review of one ModelResponse, calibrating against MetricResult scores."""
    __tablename__ = "response_reviews"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    response_id: uuid.UUID = Field(foreign_key="model_responses.id", index=True)
    reviewer_id: str                          # SME email/identifier

    language_performance_score: float | None = None        # 0.0–1.0
    language_performance_rationale: str | None = None
    cultural_appropriateness_score: float | None = None
    cultural_appropriateness_rationale: str | None = None
    hallucination_risk_score: float | None = None
    hallucination_risk_rationale: str | None = None
    bias_fairness_score: float | None = None
    bias_fairness_rationale: str | None = None
    code_switching_quality_score: float | None = None
    code_switching_quality_rationale: str | None = None
    safety_robustness_score: float | None = None
    safety_robustness_rationale: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    response: Optional[ModelResponse] = Relationship(back_populates="reviews")


# ── Scorecard ─────────────────────────────────────────────────────────────────

class Scorecard(SQLModel, table=True):
    """Final scored output for a completed Run."""
    __tablename__ = "scorecards"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="runs.id", unique=True, index=True)

    composite_score: float                   # 0–100
    verdict: str                             # VerdictBand value
    confidence_flag: str = "standard"        # "standard" | "low_coverage"

    # Per-dimension scores (stored as JSON)
    dimension_scores: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    dimension_weights: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Failing examples: list of {item_id, dimension, reason, score}
    failing_examples: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # Remediation roadmap: list of {priority, dimension, recommendation, effort}
    remediation_roadmap: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    benchmark_pack_version: str = ""
    methodology_version: str = "v1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Artefact paths
    pdf_path: str | None = None
    json_path: str | None = None

    run: Optional[Run] = Relationship(back_populates="scorecard")
