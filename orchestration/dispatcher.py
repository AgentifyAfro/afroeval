"""
Evaluation orchestration — run scheduling and evaluator dispatch.

The dispatcher is the only place that knows about both the ingestion layer
and the evaluators. It wires them together without either module knowing
about the other (module contract).

Sprint 1: Full implementation with job queue.
Phase 0 stub: marks run as failed with a clear stub message.
"""

import structlog

logger = structlog.get_logger(__name__)


async def dispatch_run(run_id: str) -> None:
    """
    Orchestrate a full evaluation run:
      1. Load the Assessment and Run from DB.
      2. Ingest model responses via the appropriate connector.
      3. Load benchmark items from the versioned pack.
      4. Dispatch evaluators (base metrics + AIL) per item.
      5. Collect MetricResults, persist to DB.
      6. Pass results to the scoring engine.
      7. Persist the Scorecard and trigger report generation.

    Sprint 1 implementation replaces this stub.
    """
    logger.info("dispatch_run called", run_id=run_id)

    # Stub: update run status to show the scaffold is wired
    try:
        from db.session import get_engine
        from sqlmodel import Session, select
        from db.models import Run, RunStatus
        from datetime import datetime

        engine = get_engine()
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run:
                run.status = RunStatus.FAILED
                run.error_message = (
                    "Orchestration dispatcher is a Phase 0 stub. "
                    "Full implementation delivered in Sprint 1 (Weeks 5–6)."
                )
                run.completed_at = datetime.utcnow()
                session.add(run)
                session.commit()
                logger.info("Run marked as stub-failed", run_id=run_id)
    except Exception as e:
        logger.error("dispatch_run stub error", run_id=run_id, error=str(e))
