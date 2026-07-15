"""
Push ModelResponse rows into Label Studio as calibration tasks for SME review.

Only exports responses that don't already have a ResponseReview AND don't
already have a task in the Label Studio project (idempotent — safe to re-run
after new eval runs complete).

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/hitl_export_tasks.py [--run-id <uuid>]
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from db.models import BenchmarkItem, MetricResult, ModelResponse, ResponseReview
from db.session import get_engine
from hitl.client import LabelStudioClient
from hitl.label_config import PROJECT_TITLE, build_calibration_label_config

# Metric names whose current implementation is a placeholder stub — the score
# is a fixed constant that ignores the actual model response, not a real
# measurement. Shown as "not yet implemented" instead of a misleadingly
# specific number until the real evaluator (see docs/METHODOLOGY_V1.md) lands.
_STUB_METRIC_NAMES: set[str] = set()

# Reason-string prefixes that indicate a transient infrastructure error (rate
# limits, auth failures, network timeouts). SMEs should never see raw exception
# text — replace with a clean "unavailable" message instead.
_ERROR_REASON_PREFIXES = (
    "AnswerRelevancyMetric unavailable:",
    "GEval unavailable:",
    "FaithfulnessMetric unavailable:",
    "Multilingual similarity unavailable:",
    "chrF unavailable:",
)


def _format_automated_scores(metric_results: list[MetricResult]) -> str:
    if not metric_results:
        return "(no automated scores recorded for this response)"
    lines = []
    for m in metric_results:
        if m.metric_name in _STUB_METRIC_NAMES:
            lines.append(
                f"{m.dimension} ({m.metric_name}): automated scoring not yet implemented — "
                "rely on your own independent judgment for this dimension."
            )
        elif any(m.reason.startswith(prefix) for prefix in _ERROR_REASON_PREFIXES):
            lines.append(
                f"{m.dimension} ({m.metric_name}): automated scoring unavailable — "
                "rely on your own independent judgment for this dimension."
            )
        else:
            lines.append(
                f"{m.dimension} ({m.metric_name}): {m.score:.2f} "
                f"({'pass' if m.passed else 'fail'}) — {m.reason}"
            )
    return "\n".join(lines)


def _responses_without_review(session: Session, run_id: uuid.UUID | None) -> list[ModelResponse]:
    reviewed_ids = set(session.exec(select(ResponseReview.response_id)).all())

    query = select(ModelResponse)
    if run_id is not None:
        query = query.where(ModelResponse.run_id == run_id)
    all_responses = session.exec(query).all()

    return [r for r in all_responses if r.id not in reviewed_ids]


def _already_exported_response_ids(client: LabelStudioClient, project_id: int) -> set[str]:
    return {
        t["data"]["response_id"]
        for t in client.list_tasks(project_id)
        if "response_id" in t.get("data", {})
    }


def export(run_id: uuid.UUID | None = None, project_title: str = PROJECT_TITLE) -> None:
    engine = get_engine()
    client = LabelStudioClient()
    project = client.get_or_create_project(project_title, build_calibration_label_config())
    already_exported = _already_exported_response_ids(client, project["id"])

    with Session(engine) as session:
        pending = [
            r for r in _responses_without_review(session, run_id)
            if str(r.id) not in already_exported
        ]
        if not pending:
            print("No unreviewed, not-yet-exported ModelResponse rows found — nothing to export.")
            return

        tasks = []
        for response in pending:
            item = session.get(BenchmarkItem, response.item_id)
            metric_results = session.exec(
                select(MetricResult).where(MetricResult.response_id == response.id)
            ).all()
            tasks.append({
                "response_id": str(response.id),
                "prompt": item.prompt if item else "(benchmark item not found)",
                "response": response.raw_output,
                "automated_scores": _format_automated_scores(list(metric_results)),
                "language": item.language if item else "unknown",
            })

    result = client.import_tasks(project["id"], tasks)
    print(f"Exported {len(tasks)} task(s) to project '{project_title}' (id={project['id']}): {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=str, default=None, help="Only export responses from this Run UUID")
    parser.add_argument("--project-title", type=str, default=PROJECT_TITLE, help="Label Studio project name (creates new project if it doesn't exist)")
    args = parser.parse_args()
    export(run_id=uuid.UUID(args.run_id) if args.run_id else None, project_title=args.project_title)
