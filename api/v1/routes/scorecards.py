"""
/v1/scorecards — retrieve scored results and trigger PDF/JSON export.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from db.models import Scorecard
from db.session import get_session

router = APIRouter()


class ScorecardRead(BaseModel):
    id: str
    run_id: str
    composite_score: float
    verdict: str
    confidence_flag: str
    safety_unverified: bool
    dimension_scores: dict[str, float]
    dimension_weights: dict[str, float]
    failing_examples: list[dict]
    remediation_roadmap: list[dict]
    benchmark_pack_version: str
    methodology_version: str
    created_at: str
    pdf_path: str | None
    json_path: str | None


@router.get("/scorecards/{run_id}", response_model=ScorecardRead)
def get_scorecard(run_id: str, session: Session = Depends(get_session)) -> ScorecardRead:
    result = session.exec(
        select(Scorecard).where(Scorecard.run_id == uuid.UUID(run_id))
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Scorecard not found for this run")
    return _to_read(result)


@router.get("/scorecards/{run_id}/pdf")
def download_pdf(run_id: str, session: Session = Depends(get_session)) -> FileResponse:
    result = session.exec(
        select(Scorecard).where(Scorecard.run_id == uuid.UUID(run_id))
    ).first()
    if not result or not result.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not yet generated for this run")
    return FileResponse(result.pdf_path, media_type="application/pdf", filename="afroeval_scorecard.pdf")


@router.get("/scorecards/{run_id}/json")
def download_json(run_id: str, session: Session = Depends(get_session)) -> ScorecardRead:
    """JSON export — same payload as the GET, consumable as a structured artefact."""
    return get_scorecard(run_id, session)


def _to_read(s: Scorecard) -> ScorecardRead:
    return ScorecardRead(
        id=str(s.id),
        run_id=str(s.run_id),
        composite_score=s.composite_score,
        verdict=s.verdict,
        confidence_flag=s.confidence_flag,
        safety_unverified=s.safety_unverified,
        dimension_scores=s.dimension_scores,
        dimension_weights=s.dimension_weights,
        failing_examples=s.failing_examples,
        remediation_roadmap=s.remediation_roadmap,
        benchmark_pack_version=s.benchmark_pack_version,
        methodology_version=s.methodology_version,
        created_at=s.created_at.isoformat(),
        pdf_path=s.pdf_path,
        json_path=s.json_path,
    )
