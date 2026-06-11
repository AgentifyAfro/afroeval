"""
AfroEval Scorecard™ — FastAPI application entry point.

All routes are versioned under /v1. The API exists from commit one
so integrations never need to re-wire when the console becomes one of many callers.
"""

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.settings import get_settings
from api.v1.routes import assessments, health, runs, scorecards
from db.session import create_db_and_tables

logger = structlog.get_logger(__name__)

settings = get_settings()

app = FastAPI(
    title="AfroEval Scorecard™ API",
    description=(
        "Africa-first AI evaluation platform. "
        "Evaluates AI models against African language, cultural, "
        "fairness, hallucination, and deployment-readiness criteria."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://afroeval.agentifyafro.ai"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/v1", tags=["health"])
app.include_router(assessments.router, prefix="/v1", tags=["assessments"])
app.include_router(runs.router, prefix="/v1", tags=["runs"])
app.include_router(scorecards.router, prefix="/v1", tags=["scorecards"])


@app.on_event("startup")
async def on_startup() -> None:
    create_db_and_tables()
    logger.info("AfroEval API starting", env=settings.afroeval_env)


def start() -> None:
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.afroeval_env == "development",
        log_level=settings.afroeval_log_level.lower(),
    )


if __name__ == "__main__":
    start()
