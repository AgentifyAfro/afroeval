"""
Read SME item-validation ratings out of Label Studio into item_validations.

Re-checks the author-exclusion rule that assignment already enforced: an assignment bug
must never silently produce a self-validated item.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_import_ratings.py
"""

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.ids import stable_item_uuid
from db.models import BenchmarkItem, ItemValidation
from db.session import get_engine
from hitl.client import LabelStudioClient
from hitl.label_config import VALIDATION_PROJECT_TITLE
from validation.identity import pseudonymise

_CHOICE_FIELDS = ("factual_accuracy", "language_quality", "cultural_score",
                  "schema_compliant", "verdict")


def _parse(annotation: dict) -> dict:
    """Flatten one Label Studio annotation into the instrument's fields."""
    out: dict = {}
    for r in annotation.get("result", []):
        name = r.get("from_name")
        val = r.get("value", {})
        if name in _CHOICE_FIELDS:
            choices = val.get("choices") or []
            if choices:
                out[name] = choices[0]
        elif name == "justification":
            texts = val.get("text") or []
            if texts:
                out["justification"] = texts[0]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-title", default=VALIDATION_PROJECT_TITLE)
    args = parser.parse_args()

    client = LabelStudioClient()
    project = client.find_project_by_title(args.project_title)
    if project is None:
        print(f"No Label Studio project titled {args.project_title!r}.")
        return

    users = {u["id"]: (u.get("email") or f"user_{u['id']}") for u in client.list_users()}
    engine = get_engine()
    written = skipped_self = skipped_incomplete = skipped_dupe = skipped_missing_item_id = 0

    with Session(engine) as session:
        for task in client.export_annotated_tasks(project["id"]):
            data = task.get("data", {})
            raw_item_id = data.get("item_id")
            if not raw_item_id:
                skipped_missing_item_id += 1
                continue
            item_uuid = stable_item_uuid(raw_item_id)
            item = session.get(BenchmarkItem, item_uuid)
            if item is None:
                continue

            for ann in task.get("annotations", []):
                parsed = _parse(ann)
                if not all(k in parsed for k in _CHOICE_FIELDS):
                    skipped_incomplete += 1
                    continue

                completed_by = ann.get("completed_by")
                validator = pseudonymise(users.get(completed_by) or f"user_{completed_by}")
                # Re-check author exclusion. Assignment enforces it; if an assignment bug
                # ever lets one through, it must die here rather than become a Tier 1 item.
                # Both sides must be pseudonymised the same way (validation.identity) —
                # item.sme_author_id is already a hash, validator was still a raw email.
                if validator and validator == (item.sme_author_id or ""):
                    skipped_self += 1
                    continue

                existing = session.exec(
                    select(ItemValidation).where(
                        ItemValidation.item_id == item_uuid,
                        ItemValidation.validator_id == validator,
                    )
                ).first()
                if existing is not None:
                    skipped_dupe += 1
                    continue

                session.add(ItemValidation(
                    item_id=item_uuid,
                    item_content_hash=data.get("item_content_hash", ""),
                    validator_id=validator,
                    batch_id=data.get("batch_id", ""),
                    factual_accuracy=parsed["factual_accuracy"],
                    language_quality=int(parsed["language_quality"]),
                    cultural_score=int(parsed["cultural_score"]),
                    schema_compliant=parsed["schema_compliant"] == "yes",
                    justification=parsed.get("justification", ""),
                    verdict=parsed["verdict"],
                ))
                written += 1
        session.commit()

    print(f"Wrote {written} validation row(s).")
    print(f"  skipped — already recorded for this validator: {skipped_dupe}")
    print(f"  skipped — incomplete instrument:                {skipped_incomplete}")
    print(f"  skipped — validator authored the item:          {skipped_self}")
    print(f"  skipped — task missing item_id:                 {skipped_missing_item_id}")


if __name__ == "__main__":
    main()
