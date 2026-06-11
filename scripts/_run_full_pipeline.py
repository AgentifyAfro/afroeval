"""Temporary dev script — full 20-item live pipeline run."""
import asyncio
import uuid
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from db.session import get_engine, create_db_and_tables
from db.models import Assessment, Run, RunStatus, Scorecard
from sqlmodel import Session, select

create_db_and_tables()

ALL_PACKS = [
    "mobile_money_sw_v1.0.0",
    "customer_service_yo_v1.0.0",
    "community_health_am_v1.0.0",
    "agriculture_ha_v1.0.0",
    "code_switching_mixed_v1.0.0",
    "safety_mixed_v1.0.0",
]

with Session(get_engine()) as s:
    assessment = Assessment(
        id=uuid.uuid4(),
        name="Week 4 Full Pipeline — All 20 Items",
        model_provider="azure_openai",
        model_identifier="gpt-4.1-mini",
        benchmark_pack_ids=ALL_PACKS,
        created_at=datetime.utcnow(),
    )
    s.add(assessment)
    s.commit()
    s.refresh(assessment)
    aid = assessment.id

with Session(get_engine()) as s:
    run = Run(
        id=uuid.uuid4(),
        assessment_id=aid,
        status=RunStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    s.add(run)
    s.commit()
    s.refresh(run)
    rid = run.id
    print(f"Run ID: {rid}")

from orchestration.dispatcher import dispatch_run
asyncio.run(dispatch_run(str(rid)))

with Session(get_engine()) as s:
    run = s.get(Run, rid)
    sc = s.exec(select(Scorecard).where(Scorecard.run_id == rid)).first()
    print(f"Status : {run.status}")
    if sc:
        print(f"Score  : {sc.composite_score}  |  Verdict: {sc.verdict}  |  Confidence: {sc.confidence_flag}")
        print("Dimensions:")
        for dim, score in sc.dimension_scores.items():
            flag = " <<< LOW" if score < 60 else ""
            print(f"  {dim:<32} {score:>6.1f}{flag}")
        if sc.remediation_roadmap:
            print("Remediation (top 3):")
            for r in sc.remediation_roadmap[:3]:
                priority = r["priority"].upper()
                dimension = r["dimension"]
                current = r["current_score"]
                print(f"  [{priority:6}] {dimension:<30} {current:.1f}")
    else:
        print(f"ERROR: {run.error_message}")
