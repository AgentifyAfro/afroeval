from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="API health check")
def health_check() -> HealthResponse:
    from api.settings import get_settings
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat(),
        environment=settings.afroeval_env,
    )
