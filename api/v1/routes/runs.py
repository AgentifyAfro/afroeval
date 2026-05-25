"""
/v1/runs — trigger and monitor evaluation runs.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from db.models import Assessment, Run, RunStatus
from db.session import get_session

router = APIRouter()


class RunCreate(BaseModel):
    assessment_id: str


class RunRead(BaseModel):
    id: str
    assessment_id: str
    status: str
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    created_at: str


@router.post("/runs", response_model=RunRead, status_code=202)
def submit_run(
    payload: RunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> RunRead:
    """Submit an assessment for execution. Returns immediately; poll /runs/{id} for status."""
    assessment = session.get(Assessment, uuid.UUID(payload.assessment_id))
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    run = Run(
        id=uuid.uuid4(),
        assessment_id=assessment.id,
        status=RunStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Dispatch to orchestration layer in background
    background_tasks.add_task(_execute_run, str(run.id))

    return _to_read(run)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(Run, uuid.UUID(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _to_read(run)


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    assessment_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[RunRead]:
    query = select(Run)
    if assessment_id:
        query = query.where(Run.assessment_id == uuid.UUID(assessment_id))
    runs = session.exec(query).all()
    return [_to_read(r) for r in runs]


async def _execute_run(run_id: str) -> None:
    """Dispatches the run to the orchestration layer. Wired fully in Sprint 1."""
    from orchestration.dispatcher import dispatch_run
    await dispatch_run(run_id)


def _to_read(r: Run) -> RunRead:
    return RunRead(
        id=str(r.id),
        assessment_id=str(r.assessment_id),
        status=r.status,
        started_at=r.started_at.isoformat() if r.started_at else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        error_message=r.error_message,
        created_at=r.created_at.isoformat(),
    )
