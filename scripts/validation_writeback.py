"""
Turn item_validations rows into validation_count / irr_score on the pack files.

The pack JSONL is the source of truth (the DB is a mirror re-seeded from it), so this writes
there - and ONLY to validation_count and irr_score. Item content is never touched.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_writeback.py --dry-run
    .\\.venv\\Scripts\\python.exe scripts/validation_writeback.py --apply
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.ids import stable_item_uuid
from validation.hashing import item_content_hash
from validation.irr import IRR_FLOOR, batch_key, pair_kappa

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"


def compute_item_results(validations: list[dict], items: list[dict]) -> dict[str, dict]:
    """
    Per item: how many DISTINCT non-stale validators rated it, the kappa of the pair that
    rated it (computed over their whole shared batch), and whether it needs adjudication.

    validations: dicts with item_id, validator_id, cultural_score, factual_accuracy,
                 item_content_hash.
    items:       dicts with id, prompt, expected_behavior.
    """
    live_hash = {i["id"]: item_content_hash(i["prompt"], i["expected_behavior"])
                 for i in items}

    # Drop stale rows first: a rating attached to content that has since changed is not a
    # rating of this item.
    fresh = [v for v in validations
             if v.get("item_content_hash") == live_hash.get(v["item_id"])]

    by_item: dict[str, dict[str, dict]] = defaultdict(dict)
    for v in fresh:
        # dict keyed by validator_id: one person rating twice counts once
        by_item[v["item_id"]][v["validator_id"]] = v

    # Group ratings by pair so kappa is computed over the pair's whole shared batch.
    pair_scores: dict[str, tuple[list[int], list[int]]] = {}
    for _item_id, raters in by_item.items():
        if len(raters) != 2:
            continue
        a, b = sorted(raters)
        key = batch_key(a, b)
        sa, sb = pair_scores.setdefault(key, ([], []))
        sa.append(int(raters[a]["cultural_score"]))
        sb.append(int(raters[b]["cultural_score"]))

    pair_kappa_by_key = {k: pair_kappa(a, b) for k, (a, b) in pair_scores.items()}

    results: dict[str, dict] = {}
    for item in items:
        item_id = item["id"]
        raters = by_item.get(item_id, {})
        count = len(raters)
        kappa = None
        adjudicate = False
        reason = ""

        if count == 2:
            a, b = sorted(raters)
            kappa = pair_kappa_by_key.get(batch_key(a, b))
            if raters[a]["factual_accuracy"] != raters[b]["factual_accuracy"]:
                adjudicate = True
                reason = (f"factual accuracy disputed: {raters[a]['factual_accuracy']} "
                          f"vs {raters[b]['factual_accuracy']}")
            elif kappa is not None and kappa < IRR_FLOOR:
                adjudicate = True
                reason = f"pair kappa {kappa:.3f} below floor {IRR_FLOOR}"
            elif abs(int(raters[a]["cultural_score"]) - int(raters[b]["cultural_score"])) > 1:
                adjudicate = True
                reason = "cultural scores differ by more than 1 rubric point"

        results[item_id] = {
            "validation_count": count,
            "irr_score": kappa,
            "needs_adjudication": adjudicate,
            "reason": reason,
        }
    return results


def _string_id_by_uuid(items: list[dict]) -> dict[str, str]:
    """
    Exact item-uuid -> pack string id map.

    Item UUIDs are uuid5 of the string id (benchmarks/ids.py), so this is a direct
    inversion rather than a content search. Keyed on str() because the UUID may come
    back from the driver as either uuid.UUID or str depending on the backend.
    """
    return {str(stable_item_uuid(i["id"])): i["id"] for i in items}


def _load_validations(items: list[dict]) -> list[dict]:
    """Read item_validations from the DB and key each row by its pack string id."""
    from sqlmodel import Session, select

    from db.models import ItemValidation
    from db.session import get_engine

    string_id = _string_id_by_uuid(items)

    with Session(get_engine()) as session:
        out = []
        for r in session.exec(select(ItemValidation)).all():
            item_id = string_id.get(str(r.item_id))
            if item_id is None:
                # A validation for an item that is no longer in any pack.
                continue
            out.append({
                "item_id": item_id,
                "validator_id": r.validator_id,
                "cultural_score": r.cultural_score,
                "factual_accuracy": r.factual_accuracy,
                "item_content_hash": r.item_content_hash,
            })
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Write validation_count / irr_score into the pack files.")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default).")
    args = parser.parse_args()

    items, path_of = [], {}
    for path in sorted(_PACKS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                items.append(d)
                path_of[d["id"]] = path

    results = compute_item_results(_load_validations(items), items)
    tier1 = sum(1 for r in results.values()
                if r["validation_count"] >= 2 and (r["irr_score"] or 0) >= IRR_FLOOR)
    adj = [i for i, r in results.items() if r["needs_adjudication"]]
    print(f"Items: {len(items)} | Tier 1 eligible: {tier1} | needing adjudication: {len(adj)}")
    for item_id in adj[:20]:
        print(f"   {item_id}: {results[item_id]['reason']}")

    if not args.apply:
        print("\nReport only. Pass --apply to write validation_count / irr_score into the packs.")
        return

    by_path: dict[Path, list[dict]] = defaultdict(list)
    for d in items:
        r = results.get(d["id"], {})
        if r.get("validation_count"):
            d["validation_count"] = r["validation_count"]
            d["irr_score"] = r["irr_score"]
        by_path[path_of[d["id"]]].append(d)

    for path, rows in by_path.items():
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    print(f"\nUpdated {len(by_path)} pack file(s). Review with `git diff` before committing.")


if __name__ == "__main__":
    main()
