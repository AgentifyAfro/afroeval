"""
Pull SME annotations from Label Studio back into the response_reviews table.

For each annotated task, parses the latest annotation's `result` entries into
per-dimension scores (Rating, normalized 0.0-1.0) and rationales (TextArea),
resolves the annotator's numeric `completed_by` id to a reviewer_id via
/api/users/, and inserts one ResponseReview row per (response_id, reviewer_id)
pair not already imported — re-running is safe, it just skips pairs that
already have a stored review.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/hitl_import_reviews.py
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from db.models import ResponseReview
from db.session import get_engine
from hitl.client import LabelStudioClient
from hitl.label_config import PROJECT_TITLE, RATING_MAX
from scoring.engine import DEFAULT_WEIGHTS


def _build_user_lookup(client: LabelStudioClient) -> dict[int, str]:
    try:
        users = client.list_users()
    except Exception:
        return {}
    return {u["id"]: u.get("email") or u.get("username") or f"user_{u['id']}" for u in users}


def _parse_annotation(result: list[dict]) -> dict:
    """Maps a Label Studio annotation `result` list onto ResponseReview field names."""
    fields: dict[str, float | str] = {}
    for entry in result:
        from_name = entry.get("from_name", "")
        value = entry.get("value", {})

        for dimension in DEFAULT_WEIGHTS:
            if from_name == f"{dimension}_score" and "rating" in value:
                fields[f"{dimension}_score"] = value["rating"] / RATING_MAX
            elif from_name == f"{dimension}_rationale" and value.get("text"):
                fields[f"{dimension}_rationale"] = value["text"][0]
    return fields


def import_reviews() -> None:
    engine = get_engine()
    client = LabelStudioClient()

    project = client.find_project_by_title(PROJECT_TITLE)
    if project is None:
        print(f"No Label Studio project named '{PROJECT_TITLE}' found — nothing to import.")
        return

    tasks = client.export_annotated_tasks(project["id"])
    user_lookup = _build_user_lookup(client)

    with Session(engine) as session:
        existing_pairs = set(
            session.exec(select(ResponseReview.response_id, ResponseReview.reviewer_id)).all()
        )

        imported = 0
        skipped = 0
        for task in tasks:
            annotations = task.get("annotations", [])
            if not annotations:
                continue

            response_id_raw = task.get("data", {}).get("response_id")
            if not response_id_raw:
                continue
            response_id = uuid.UUID(response_id_raw)

            annotation = annotations[-1]
            reviewer_id = user_lookup.get(annotation.get("completed_by"), f"user_{annotation.get('completed_by')}")

            if (response_id, reviewer_id) in existing_pairs:
                skipped += 1
                continue

            fields = _parse_annotation(annotation.get("result", []))
            if not fields:
                continue

            review = ResponseReview(response_id=response_id, reviewer_id=reviewer_id, **fields)
            session.add(review)
            existing_pairs.add((response_id, reviewer_id))
            imported += 1

        session.commit()

    print(f"Imported {imported} new review(s), skipped {skipped} already-imported pair(s).")


if __name__ == "__main__":
    import_reviews()
