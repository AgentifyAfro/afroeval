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

# Bookkeeping this tool attaches to loaded rows. Stripped before anything is rendered
# back to disk so it can never land in a pack file.
_INTERNAL_KEYS = ("_source_path",)


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

    # Every item the DB has ANY row for, stale or not. This is what distinguishes "the DB
    # has nothing to say about this item" from "this item's ratings have all gone stale" -
    # only the latter may demote a published validation_count back to 0.
    has_rows = {v["item_id"] for v in validations}

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
            # True when the DB holds at least one row for this item, fresh or stale.
            "has_validation_history": item_id in has_rows,
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


def _load_validations(items: list[dict]) -> tuple[list[dict], int]:
    """
    Read item_validations from the DB and key each row by its pack string id.

    Returns (rows, skipped) where skipped counts validations whose item_id maps to no
    item in any pack. A non-zero skipped count is a red flag - it usually means the
    uuid map and the packs have drifted apart, not that the work is done.
    """
    from sqlmodel import Session, select

    from db.models import ItemValidation
    from db.session import get_engine

    string_id = _string_id_by_uuid(items)

    with Session(get_engine()) as session:
        out = []
        skipped = 0
        for r in session.exec(select(ItemValidation)).all():
            item_id = string_id.get(str(r.item_id))
            if item_id is None:
                # A validation for an item that is no longer in any pack.
                skipped += 1
                continue
            out.append({
                "item_id": item_id,
                "validator_id": r.validator_id,
                "cultural_score": r.cultural_score,
                "factual_accuracy": r.factual_accuracy,
                "item_content_hash": r.item_content_hash,
                "justification": r.justification,
            })
        return out, skipped


def load_packs(packs_dir: Path) -> tuple[list[dict], dict[Path, list[dict]], dict[Path, str]]:
    """
    Load every pack, remembering which file each row came from.

    An item id is NOT unique across packs - a superseding pack version carries the same
    ids as the version it replaces (ch-am-001..011 live in both community_health_am
    v1.0.0 and v1.1.0). Grouping rows by a flat id -> path map therefore collapses both
    copies onto one file and duplicates them there, so rows are grouped by their own
    source file instead.

    Returns (all_items, rows_by_path, newline_by_path).
    """
    all_items: list[dict] = []
    rows_by_path: dict[Path, list[dict]] = {}
    newline_by_path: dict[Path, str] = {}

    for path in sorted(packs_dir.glob("*.jsonl")):
        raw = path.read_bytes()
        # Preserve whatever this file already uses; some packs are stored CRLF and some
        # LF, and rewriting one into the other churns every line of the file.
        newline_by_path[path] = "\r\n" if b"\r\n" in raw else "\n"
        rows = []
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                d["_source_path"] = path
                rows.append(d)
                all_items.append(d)
        rows_by_path[path] = rows
    return all_items, rows_by_path, newline_by_path


def _render(rows: list[dict], newline: str) -> bytes:
    """Render rows back to JSONL bytes, minus this tool's internal bookkeeping keys."""
    out = []
    for row in rows:
        clean = {k: v for k, v in row.items() if k not in _INTERNAL_KEYS}
        out.append(json.dumps(clean, ensure_ascii=False) + newline)
    return "".join(out).encode("utf-8")


def apply_results(
    results: dict[str, dict],
    rows_by_path: dict[Path, list[dict]],
    newline_by_path: dict[Path, str],
) -> tuple[list[Path], int]:
    """
    Write validation_count / irr_score into the packs.

    Two rules keep this from touching data it has no business touching:

    1. A pack is only rewritten when a field actually changed AND the rendered bytes
       differ from what is already on disk. No no-op rewrites.
    2. Fields are only written for items the DB holds validation rows for. If every row
       for an item has gone stale the count is written as 0 and irr_score as null -
       that demotion is the whole point of the content hash. But an item the DB has
       never heard of keeps whatever the pack already published; a missing row is not
       evidence of a missing validation.

    Returns (paths_written, items_changed).
    """
    written: list[Path] = []
    changed = 0

    for path, rows in rows_by_path.items():
        for d in rows:
            r = results.get(d["id"])
            if r is None or not r["has_validation_history"]:
                continue
            count = r["validation_count"]
            irr = r["irr_score"] if count else None
            if d.get("validation_count") == count and d.get("irr_score") == irr:
                continue
            d["validation_count"] = count
            d["irr_score"] = irr
            changed += 1

        rendered = _render(rows, newline_by_path[path])
        if rendered != path.read_bytes():
            path.write_bytes(rendered)
            written.append(path)

    return written, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="Write validation_count / irr_score into the pack files.")
    mode.add_argument("--dry-run", action="store_true", help="Report only (default).")
    parser.add_argument("--packs-dir", type=Path, default=_PACKS_DIR,
                        help="Pack directory to read/write (default: benchmarks/packs).")
    args = parser.parse_args()

    items, rows_by_path, newline_by_path = load_packs(args.packs_dir)

    validations, skipped = _load_validations(items)
    results = compute_item_results(validations, items)
    tier1 = sum(1 for r in results.values()
                if r["validation_count"] >= 2 and (r["irr_score"] or 0) >= IRR_FLOOR)
    adj = [i for i, r in results.items() if r["needs_adjudication"]]
    print(f"Items: {len(items)} | Tier 1 eligible: {tier1} | needing adjudication: {len(adj)}")
    if skipped:
        print(f"WARNING: {skipped} validation row(s) skipped - item_id matches no item in "
              f"any pack. The uuid map and the packs have drifted.")
    for item_id in adj[:20]:
        print(f"   {item_id}: {results[item_id]['reason']}")

    if not args.apply:
        print("\nReport only. Pass --apply to write validation_count / irr_score into the packs.")
        return

    written, changed = apply_results(results, rows_by_path, newline_by_path)
    if not written:
        print("\nNo pack file changed - the packs already match the validation record.")
        return
    print(f"\nUpdated {changed} item(s) across {len(written)} pack file(s). "
          f"Review with `git diff` before committing.")
    for path in written:
        print(f"   {path.name}")


if __name__ == "__main__":
    main()
