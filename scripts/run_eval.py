"""
AfroEval CLI - run a full evaluation pipeline from the terminal.

No server required. Creates the Assessment + Run rows, dispatches directly
to the orchestration layer, then prints the scorecard.

Usage:
    .venv/Scripts/python.exe scripts/run_eval.py
    .venv/Scripts/python.exe scripts/run_eval.py --name "My run"
    .venv/Scripts/python.exe scripts/run_eval.py --packs mobile_money_sw_v1.0.0,customer_service_yo_v1.0.0
    .venv/Scripts/python.exe scripts/run_eval.py --provider openai --model gpt-4o
"""

import argparse
import asyncio
import logging
import sys
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.insert(0, str(Path(__file__).parent.parent))

DEFAULT_PACKS = [
    "mobile_money_sw_v1.0.0",
    "remittance_so_v1.0.0",
    "cross_border_trade_ha_v1.0.0",
    "community_health_am_v1.0.0",
    "agriculture_om_v1.0.0",
    "public_services_zu_v1.0.0",
    "customer_service_yo_v1.0.0",
    "urban_digital_sheng_v1.0.0",
]

SECTOR_MAP = {
    "mobile_money_sw_v1.0.0":       "Financial Inclusion",
    "remittance_so_v1.0.0":         "Financial Inclusion",
    "cross_border_trade_ha_v1.0.0": "Financial Inclusion",
    "community_health_am_v1.0.0":   "Essential Services",
    "agriculture_om_v1.0.0":        "Essential Services",
    "public_services_zu_v1.0.0":    "Essential Services",
    "customer_service_yo_v1.0.0":   "Digital Consumer Economy",
    "urban_digital_sheng_v1.0.0":   "Digital Consumer Economy",
}


def _bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def _print_scorecard(scorecard, pack_ids: list[str], elapsed: float) -> None:
    W = 62
    sep = "-" * W

    print()
    print(sep)
    print("  AfroEval Scorecard")
    print(sep)
    print(f"  Composite Score  {scorecard.composite_score:>6.2f} / 100")
    print(f"  Verdict          {scorecard.verdict}")
    print(f"  Confidence       {scorecard.confidence_flag}")
    if scorecard.safety_unverified:
        print(f"  Safety           NOT VERIFIED (no applicable safety items)")
    print(f"  Packs            {len(pack_ids)}   Items ~{len(pack_ids) * 10}")
    print(f"  Runtime          {elapsed:.0f}s")
    print(sep)
    print(f"  {'Dimension':<28}  {'Score':>5}  {'Wt':>4}  {'':20}")
    print(sep)

    for dim, score in sorted(scorecard.dimension_scores.items(), key=lambda x: x[1]):
        weight = scorecard.dimension_weights.get(dim, 0)
        flag = " (!)" if score < 60 else ""
        print(f"  {dim:<28}  {score:5.1f}  {weight:3.0%}  {_bar(score)}{flag}")

    print(sep)

    high_prio = [r for r in (scorecard.remediation_roadmap or []) if r.get("priority") == "high"]
    if high_prio:
        print("  Top Remediation Actions")
        print(sep)
        for item in high_prio[:3]:
            rec = item.get("recommendation", "")
            rec_short = rec[:55] + "..." if len(rec) > 55 else rec
            print(f"  [{item.get('priority','?').upper()}] {item.get('dimension','')}")
            print(f"       {rec_short}")
            print(f"       Effort: {item.get('estimated_effort','?')}")
    print(sep)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a full AfroEval pipeline from the terminal — no server required."
    )
    parser.add_argument(
        "--name",
        default=f"CLI run {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M')} UTC",
        help="Assessment name",
    )
    parser.add_argument(
        "--packs",
        default=None,
        help="Comma-separated pack IDs (default: all 8 strategic packs)",
    )
    parser.add_argument("--provider", default="azure_openai", help="Model provider")
    parser.add_argument("--model", default="gpt-4.1-mini", help="Model identifier")
    args = parser.parse_args()

    pack_ids: list[str] = args.packs.split(",") if args.packs else DEFAULT_PACKS

    from db.models import Assessment, Run, RunStatus, Scorecard
    from db.session import get_engine
    from sqlmodel import Session, select

    engine = get_engine()

    # Suppress SQLAlchemy echo=True noise.
    # echo=True adds a StreamHandler directly to sqlalchemy.engine.Engine —
    # must clear handlers AND set level after engine creation.
    for _name in ("sqlalchemy.engine.Engine", "sqlalchemy.engine", "sqlalchemy.pool"):
        _log = logging.getLogger(_name)
        _log.handlers.clear()
        _log.setLevel(logging.WARNING)
        _log.propagate = False

    # ── Create Assessment + Run rows ──────────────────────────────────────────
    assessment_id = uuid.uuid4()
    run_id_uuid = uuid.uuid4()

    with Session(engine) as session:
        session.add(Assessment(
            id=assessment_id,
            name=args.name,
            model_provider=args.provider,
            model_identifier=args.model,
            benchmark_pack_ids=pack_ids,
            config={},
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        session.add(Run(
            id=run_id_uuid,
            assessment_id=assessment_id,
            status=RunStatus.PENDING,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        session.commit()

    run_id = str(run_id_uuid)

    print(f"\nAssessment : {args.name}")
    print(f"Run ID     : {run_id}")
    print(f"Packs      : {len(pack_ids)}")
    for p in pack_ids:
        sector = SECTOR_MAP.get(p, "")
        print(f"             {p:<38}  {sector}")
    print(f"\nDispatching… (Ctrl+C to abort)\n")

    # ── Dispatch directly — no HTTP server needed ─────────────────────────────
    from orchestration.dispatcher import dispatch_run

    start = datetime.now(timezone.utc).replace(tzinfo=None)
    asyncio.run(dispatch_run(run_id))
    elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - start).total_seconds()

    # ── Fetch and print scorecard ─────────────────────────────────────────────
    with Session(engine) as session:
        scorecard = session.exec(
            select(Scorecard).where(Scorecard.run_id == uuid.UUID(run_id))
        ).first()

        if not scorecard:
            run_row = session.get(Run, uuid.UUID(run_id))
            status = run_row.status if run_row else "unknown"
            error = run_row.error_message if run_row else "no run row found"
            print(f"Run finished with status: {status}")
            print(f"Error: {error}")
            sys.exit(1)

        _print_scorecard(scorecard, pack_ids, elapsed)


if __name__ == "__main__":
    main()
