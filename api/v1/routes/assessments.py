"""
/v1/assessments — configure and submit evaluation assessments.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from db.models import Assessment, ModelProvider
from db.session import get_session

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class AssessmentCreate(BaseModel):
    name: str
    model_provider: ModelProvider
    model_identifier: str                   # e.g. "gpt-4o" or Azure deployment name
    benchmark_pack_ids: list[str]           # UUIDs of packs to use
    config: dict = {}                       # Optional overrides (weights, judge model, etc.)


class AssessmentRead(BaseModel):
    id: str
    name: str
    model_provider: str
    model_identifier: str
    benchmark_pack_ids: list[str]
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/assessments", response_model=AssessmentRead, status_code=201)
def create_assessment(
    payload: AssessmentCreate,
    session: Session = Depends(get_session),
) -> AssessmentRead:
    """Configure a new assessment. Does not start execution — use /runs to trigger."""
    assessment = Assessment(
        id=uuid.uuid4(),
        name=payload.name,
        model_provider=payload.model_provider.value,
        model_identifier=payload.model_identifier,
        benchmark_pack_ids=payload.benchmark_pack_ids,
        config=payload.config,
        created_at=datetime.utcnow(),
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return _to_read(assessment)


@router.get("/assessments", response_model=list[AssessmentRead])
def list_assessments(session: Session = Depends(get_session)) -> list[AssessmentRead]:
    assessments = session.exec(select(Assessment)).all()
    return [_to_read(a) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=AssessmentRead)
def get_assessment(
    assessment_id: str,
    session: Session = Depends(get_session),
) -> AssessmentRead:
    assessment = session.get(Assessment, uuid.UUID(assessment_id))
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return _to_read(assessment)


def _to_read(a: Assessment) -> AssessmentRead:
    return AssessmentRead(
        id=str(a.id),
        name=a.name,
        model_provider=a.model_provider,
        model_identifier=a.model_identifier,
        benchmark_pack_ids=a.benchmark_pack_ids,
        created_at=a.created_at.isoformat(),
    )
