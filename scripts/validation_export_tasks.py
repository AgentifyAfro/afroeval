"""
Push benchmark items into the SME item-VALIDATION Label Studio project.

Distinct from scripts/hitl_export_tasks.py, which exports model RESPONSES for calibration.
This exports ITEMS for Tier 1 validation: each item is assigned to exactly two eligible
validators who did not author it (validation/assignment.py).

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_export_tasks.py --packs mobile_money_sw_v1.0.0
    .\\.venv\\Scripts\\python.exe scripts/validation_export_tasks.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.loader import load_pack
from hitl.client import LabelStudioClient
from hitl.label_config import VALIDATION_PROJECT_TITLE, build_validation_label_config
from validation.assignment import assign_validators
from validation.hashing import item_content_hash
from validation.irr import batch_key

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"
_ROSTER = Path(__file__).parent / "data" / "validator_roster.json"


def _load_roster() -> list[dict]:
    with _ROSTER.open(encoding="utf-8") as f:
        return json.load(f)


def _select_validators(roster: list[dict], ids: list[str] | None) -> list[dict]:
    """Restrict the roster to `ids` (roster order preserved); falsy `ids` = full roster.

    Lets a round concentrate on a chosen pool — e.g. one non-author pair — so the pair
    accumulates the MIN_SHARED_BATCH (10) shared items a defensible kappa needs, instead
    of the load-balancer fragmenting a small pack across many sub-10-item pairs.
    """
    if not ids:
        return roster
    keep = set(ids)
    return [r for r in roster if r["validator_id"] in keep]


def _already_exported_item_ids(client: LabelStudioClient, project_id: int) -> set[str]:
    """Mirrors scripts/hitl_export_tasks.py's _already_exported_response_ids — without this,
    re-running the export re-imports every item as a duplicate task, corrupting the per-pair
    batch counts the 10-item kappa minimum depends on.

    Assumption: this keys on the item's string id alone, which is NOT globally unique
    across pack versions (e.g. ch-am-001..011 exist in both community_health_am v1.0.0
    and v1.1.0 — see load_packs() in scripts/validation_writeback.py, which groups by
    source file for exactly this reason). Only reachable under the normal workflow of
    one active pack version at a time; a future multi-version export would need to key
    on (pack, id) instead."""
    return {
        t["data"]["item_id"]
        for t in client.list_tasks(project_id)
        if "item_id" in t.get("data", {})
    }


def _load_pack_by_id(pack_id: str) -> list[dict]:
    """'mobile_money_sw_v1.0.0' -> load_pack('mobile_money_sw', 'v1.0.0')

    Packs on disk are named <name>_<version>.jsonl, but load_pack takes name and
    version separately. Same split convention as scripts/seed_packs_to_db.py and
    reporting/generator.py: name may itself contain underscores, so split on the
    last "_v" rather than the first "_".
    """
    idx = pack_id.rfind("_v")
    if idx == -1:
        raise ValueError(f"Cannot parse pack id '{pack_id}' — expected <name>_v<version>")
    # include_gold=True: gold items are excluded from SCORING (they're calibration
    # anchors, never scored — Methodology v1.1), not from human validation. Tier 1
    # requires two independent validations for every item including gold, and gold
    # is barred from Tier 2 (docs/BENCHMARK_ITEM_SCHEMA.md:131), so this is the only
    # path that can ever validate them.
    return load_pack(pack_id[:idx], pack_id[idx + 1:], include_gold=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packs", nargs="+", default=None,
                        help="Pack ids to export. Default: every pack file.")
    parser.add_argument("--project-title", default=VALIDATION_PROJECT_TITLE)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report assignments without touching Label Studio.")
    parser.add_argument("--validators", type=lambda s: [v.strip() for v in s.split(",") if v.strip()],
                        default=None,
                        help="Comma-separated validator_ids to restrict this round's pool "
                             "(e.g. one non-author pair so it clears the 10-item kappa floor). "
                             "Default: the whole roster.")
    args = parser.parse_args()

    roster = _select_validators(_load_roster(), args.validators)
    pack_ids = args.packs or [p.stem for p in sorted(_PACKS_DIR.glob("*.jsonl"))]

    tasks: list[dict] = []
    load: dict[str, list[str]] = {}
    unassignable: list[tuple[str, str]] = []

    for pack_id in pack_ids:
        for item in _load_pack_by_id(pack_id):
            pair = assign_validators(item, roster, existing=load)
            if not pair:
                unassignable.append((item["id"], item.get("language", "?")))
                continue
            for v in pair:
                load.setdefault(v, []).append(item["id"])
            # SECURITY — do NOT add `is_gold` or the item's known rubric score to this
            # payload. Gold items are loaded here on purpose (include_gold=True above) because
            # they still need two human validators, but the payload deliberately carries only
            # neutral content — no gold flag, no expected score. That omission is what keeps
            # the calibration set secret: anyone with access to this Label Studio validation
            # project sees item content but cannot tell which items are gold or what their
            # known scores are, so the drift-detection anchors can't be gamed. Adding a gold
            # indicator "to help reviewers" would silently defeat that. Keep it out.
            tasks.append({
                "item_id": item["id"],
                "prompt": item["prompt"],
                "expected_behavior": item["expected_behavior"],
                "provenance": item.get("provenance", ""),
                "language": item.get("language", ""),
                "domain": item.get("domain", ""),
                "assigned_validators": ",".join(pair),
                "batch_id": batch_key(pair[0], pair[1]),
                "item_content_hash": item_content_hash(
                    item["prompt"], item["expected_behavior"]
                ),
            })

    print(f"Assignable items: {len(tasks)}")
    for v, items in sorted(load.items()):
        print(f"   {v}: {len(items)} items")
    if unassignable:
        print(f"\nUNASSIGNABLE ({len(unassignable)}) — fewer than 2 eligible validators:")
        for iid, lang in unassignable[:20]:
            print(f"   {iid} ({lang})")
        print("   Add a second validator for these languages to scripts/data/validator_roster.json.")

    if args.dry_run:
        print("\n--dry-run: nothing sent to Label Studio.")
        return

    client = LabelStudioClient()
    project = client.get_or_create_project(
        args.project_title, build_validation_label_config(), maximum_annotations=2
    )
    already_exported = _already_exported_item_ids(client, project["id"])
    # Same assumption as _already_exported_item_ids: keyed on string id alone, not
    # unique across pack versions. Fine only because one pack version is active at a
    # time in the normal workflow.
    new_tasks = [t for t in tasks if t["item_id"] not in already_exported]
    skipped = len(tasks) - len(new_tasks)
    if skipped:
        print(f"\nSkipping {skipped} item(s) already exported to project '{args.project_title}'.")

    if not new_tasks:
        print("Nothing new to import.")
        return

    result = client.import_tasks(project["id"], new_tasks)
    print(f"\nProject '{args.project_title}' (id={project['id']}): imported {len(new_tasks)} task(s)")
    print(f"   {result}")


if __name__ == "__main__":
    main()
