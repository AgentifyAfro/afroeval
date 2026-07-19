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
from validation.hashing import item_content_hash

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"


def build_adjudication_tasks(
    flagged: dict[str, dict],
    ratings_by_item: dict[str, list[dict]],
    items_by_id: dict[str, dict],
) -> tuple[list[dict], list[str]]:
    """
    Build one adjudication task per flagged item, pairing only FRESH validator ratings.

    ratings_by_item may still hold stale rows (a rating attached to content that has since
    changed) alongside fresh ones - compute_item_results filters those out before flagging,
    but flagging happens on item_id alone, so ratings_by_item must be filtered again here
    with the same freshness test: a row is fresh when its item_content_hash matches the live
    item's current hash. Without this, an item re-validated after a content edit carries 3+
    rows (stale old raters + fresh new raters) into this function, `len(pair) != 2` fires,
    and a genuinely-flagged item silently drops out of the queue.

    Returns (tasks, warnings). warnings names every flagged item that did not yield exactly
    two fresh ratings, so a dropped item is never silent.
    """
    tasks: list[dict] = []
    warnings: list[str] = []

    for item_id, r in flagged.items():
        item = items_by_id[item_id]
        live_hash = item_content_hash(item["prompt"], item["expected_behavior"])
        fresh = [v for v in ratings_by_item.get(item_id, [])
                 if v.get("item_content_hash") == live_hash]
        pair = sorted(fresh, key=lambda x: x["validator_id"])
        if len(pair) != 2:
            warnings.append(
                f"WARNING: {item_id} is flagged for adjudication ({r['reason']}) but has "
                f"{len(pair)} fresh validation(s), not 2 - dropped from the queue instead "
                f"of exported. Check for stale ratings left by a content edit."
            )
            continue
        tasks.append({
            "item_id": item_id,
            "prompt": item["prompt"],
            "expected_behavior": item["expected_behavior"],
            "reason": r["reason"],
            "rating_a": (f"{pair[0]['validator_id']}: cultural "
                         f"{pair[0]['cultural_score']}, factual "
                         f"{pair[0]['factual_accuracy']}\n"
                         f"Justification: {pair[0].get('justification', '')}"),
            "rating_b": (f"{pair[1]['validator_id']}: cultural "
                         f"{pair[1]['cultural_score']}, factual "
                         f"{pair[1]['factual_accuracy']}\n"
                         f"Justification: {pair[1].get('justification', '')}"),
        })

    return tasks, warnings


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

    tasks, warnings = build_adjudication_tasks(flagged, ratings_by_item, by_id)

    print(f"Items needing adjudication: {len(flagged)} flagged, {len(tasks)} exported")
    for t in tasks[:20]:
        print(f"   {t['item_id']}: {t['reason']}")
    for w in warnings:
        print(w)
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
