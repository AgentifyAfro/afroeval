"""
Create a fresh evaluation run and export responses to a Label Studio project.

Runs entirely local against the production DB — no server required.
Useful for generating a corrected SME calibration task list after evaluator
rebuilds (all stub scores have been replaced with real LLM-judge evaluators).

Usage (from afroeval/):
    .\.venv\Scripts\python.exe scripts/run_and_export.py

Options:
    --assessment-name    Name shown in the console (default: "SME Calibration v2 — all packs")
    --model-provider     azure_openai | anthropic (default: azure_openai)
    --model-id           Model deployment name (default: gpt-4.1-mini)
    --packs              Space-separated pack names (default: all 12 packs)
    --project-title      Label Studio project title (default: "AfroEval — SME Calibration v2 (2026-06-29)")
    --skip-export        Run evaluation only; skip Label Studio export
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from sqlmodel import Session

from db.models import Assessment, Run, RunStatus
from db.session import get_engine

logger = structlog.get_logger(__name__)

_DEFAULT_PACKS = [
    "mobile_money_sw_v1.0.0",
    "remittance_so_v1.0.0",
    "cross_border_trade_ha_v1.0.0",
    "community_health_am_v1.0.0",
    "agriculture_om_v1.0.0",
    "agriculture_ha_v1.0.0",
    "public_services_zu_v1.0.0",
    "customer_service_yo_v1.0.0",
    "urban_digital_sheng_v1.0.0",
    "code_switching_mixed_v1.0.0",
    "safety_mixed_v1.0.0",
    "customer_service_en_v1.0.0",
]

_DEFAULT_PROJECT_TITLE = "AfroEval — SME Calibration v2 (2026-06-29)"


def _create_assessment_and_run(
    engine,
    assessment_name: str,
    model_provider: str,
    model_id: str,
    pack_ids: list[str],
) -> str:
    with Session(engine) as session:
        assessment = Assessment(
            id=uuid.uuid4(),
            name=assessment_name,
            model_provider=model_provider,
            model_identifier=model_id,
            benchmark_pack_ids=pack_ids,
            config={},
            created_at=datetime.utcnow(),
        )
        session.add(assessment)
        session.flush()

        run = Run(
            id=uuid.uuid4(),
            assessment_id=assessment.id,
            status=RunStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        session.add(run)
        session.commit()

        run_id = str(run.id)
        assessment_id = str(assessment.id)

    logger.info(
        "Assessment and run created",
        assessment_id=assessment_id,
        assessment_name=assessment_name,
        run_id=run_id,
        packs=pack_ids,
    )
    return run_id


async def _run(run_id: str) -> None:
    from orchestration.dispatcher import dispatch_run
    await dispatch_run(run_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assessment-name", default="SME Calibration v2 — all packs")
    parser.add_argument("--model-provider", default="azure_openai", choices=["azure_openai", "anthropic", "openai"])
    parser.add_argument("--model-id", default="gpt-4.1-mini")
    parser.add_argument("--packs", nargs="+", default=_DEFAULT_PACKS)
    parser.add_argument("--project-title", default=_DEFAULT_PROJECT_TITLE)
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args()

    engine = get_engine()

    print(f"\n=== AfroEval — Run & Export ===")
    print(f"Model:    {args.model_provider} / {args.model_id}")
    print(f"Packs:    {len(args.packs)} packs")
    for p in args.packs:
        print(f"          · {p}")
    print(f"Project:  {args.project_title}")
    print()

    print("Step 1/3 — Creating assessment and run in DB...")
    run_id = _create_assessment_and_run(
        engine=engine,
        assessment_name=args.assessment_name,
        model_provider=args.model_provider,
        model_id=args.model_id,
        pack_ids=args.packs,
    )
    print(f"          Run ID: {run_id}")

    print("\nStep 2/3 — Dispatching evaluation run (this may take 20-40 minutes)...")
    print("          Progress is logged above as items complete.")
    asyncio.run(_run(run_id))
    print(f"\n          Run {run_id} complete.")

    if args.skip_export:
        print("\n--skip-export set. To export later:")
        print(f'  .venv\\Scripts\\python.exe scripts/hitl_export_tasks.py --run-id {run_id} --project-title "{args.project_title}"')
        return

    print(f'\nStep 3/3 — Exporting to Label Studio project "{args.project_title}"...')
    # Import relative to this file so no package __init__.py is needed
    sys.path.insert(0, str(Path(__file__).parent))
    from hitl_export_tasks import export
    export(run_id=uuid.UUID(run_id), project_title=args.project_title)
    print("\nDone. Open Label Studio to see the new tasks:")
    print("  https://afroeval-label-studio.azurewebsites.net")


if __name__ == "__main__":
    main()
