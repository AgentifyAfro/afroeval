"""
Push items whose validators disagreed into the adjudication project.

Triggered by scripts/validation_writeback.py flagging needs_adjudication: a factual-accuracy
dispute, a pair kappa below the 0.70 floor, or cultural scores more than one rubric point
apart.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_adjudicate.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hitl.client import LabelStudioClient
from hitl.label_config import ADJUDICATION_PROJECT_TITLE, build_adjudication_label_config
from scripts.validation_writeback import _load_validations, compute_item_results

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-title", default=ADJUDICATION_PROJECT_TITLE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    items = []
    for path in sorted(_PACKS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
    by_id = {i["id"]: i for i in items}

    validations, skipped = _load_validations(items)
    results = compute_item_results(validations, items)
    flagged = {i: r for i, r in results.items() if r["needs_adjudication"]}

    ratings_by_item: dict[str, list[dict]] = {}
    for v in validations:
        ratings_by_item.setdefault(v["item_id"], []).append(v)

    tasks = []
    for item_id, r in flagged.items():
        pair = sorted(ratings_by_item.get(item_id, []), key=lambda x: x["validator_id"])
        if len(pair) != 2:
            continue
        item = by_id[item_id]
        tasks.append({
            "item_id": item_id,
            "prompt": item["prompt"],
            "expected_behavior": item["expected_behavior"],
            "reason": r["reason"],
            "rating_a": (f"{pair[0]['validator_id']}: cultural "
                         f"{pair[0]['cultural_score']}, factual "
                         f"{pair[0]['factual_accuracy']}"),
            "rating_b": (f"{pair[1]['validator_id']}: cultural "
                         f"{pair[1]['cultural_score']}, factual "
                         f"{pair[1]['factual_accuracy']}"),
        })

    print(f"Items needing adjudication: {len(tasks)}")
    for t in tasks[:20]:
        print(f"   {t['item_id']}: {t['reason']}")
    if skipped:
        print(f"WARNING: {skipped} validation row(s) skipped - item_id matches no item in "
              f"any pack. The uuid map and the packs have drifted.")

    if args.dry_run or not tasks:
        print("\n--dry-run or nothing to send: Label Studio untouched.")
        return

    client = LabelStudioClient()
    project = client.get_or_create_project(args.project_title,
                                           build_adjudication_label_config())
    result = client.import_tasks(project["id"], tasks)
    print(f"\nProject '{args.project_title}' (id={project['id']}): {result}")


if __name__ == "__main__":
    main()
