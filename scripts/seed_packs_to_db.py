"""
Sync benchmark JSONL packs → BenchmarkPack + BenchmarkItem rows in the DB.

Idempotent: re-running skips rows that already exist (check-then-insert).
Safe to run multiple times — existing rows are never modified or deleted.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/seed_packs_to_db.py
"""

import sys
from pathlib import Path

# Allow running from scripts/ or from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session

from benchmarks.ids import stable_item_uuid, stable_pack_uuid
from benchmarks.loader import PACKS_DIR
from db.models import BenchmarkItem, BenchmarkPack
from db.session import get_engine


def _parse_pack_filename(filename: str) -> tuple[str, str]:
    """'mobile_money_sw_v1.0.0.jsonl' → ('mobile_money_sw', 'v1.0.0')"""
    stem = filename.removesuffix(".jsonl")
    idx = stem.rfind("_v")
    if idx == -1:
        raise ValueError(f"Cannot parse pack filename '{filename}' — expected <name>_v<version>.jsonl")
    return stem[:idx], stem[idx + 1:]


def _load_all_items(pack_path: Path) -> list[dict]:
    """Load every line from a JSONL pack, including held-out items."""
    import json
    items = []
    with pack_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def seed() -> None:
    pack_files = sorted(PACKS_DIR.glob("*.jsonl"))
    if not pack_files:
        print("No JSONL packs found in benchmarks/packs/.")
        print("Run: .venv\\Scripts\\python.exe scripts/seed_benchmarks.py")
        return

    engine = get_engine()
    new_packs = 0
    new_items = 0

    with Session(engine) as session:
        for pack_path in pack_files:
            name, version = _parse_pack_filename(pack_path.name)
            pack_uuid = stable_pack_uuid(name, version)
            items = _load_all_items(pack_path)

            if not items:
                print(f"  ! {pack_path.name} — empty, skipping")
                continue

            # Infer language + domain from the first non-held-out item.
            active = [i for i in items if not i.get("is_held_out")]
            first = active[0] if active else items[0]

            # ── Upsert BenchmarkPack ───────────────────────────────────────
            if session.get(BenchmarkPack, pack_uuid) is None:
                session.add(BenchmarkPack(
                    id=pack_uuid,
                    name=name,
                    version=version,
                    language=first.get("language", ""),
                    domain=first.get("domain", ""),
                    item_count=len(active),
                ))
                new_packs += 1
                print(f"  + {name} {version}  ({len(active)} active + {len(items)-len(active)} held-out)")
            else:
                print(f"  ~ {name} {version}  already in DB — skipping pack row")

            # ── Upsert BenchmarkItems ──────────────────────────────────────
            for item in items:
                item_uuid = stable_item_uuid(item["id"])
                if session.get(BenchmarkItem, item_uuid) is None:
                    session.add(BenchmarkItem(
                        id=item_uuid,
                        pack_id=pack_uuid,
                        prompt=item["prompt"],
                        expected_behavior=item.get("expected_behavior", ""),
                        language=item.get("language", ""),
                        domain=item.get("domain", ""),
                        cohort=item.get("cohort", ""),
                        provenance=item.get("provenance", ""),
                        is_gold=item.get("is_gold", False),
                        tags=item.get("tags", []),
                    ))
                    new_items += 1

            session.commit()

    print(f"\nDone. Inserted {new_packs} pack(s), {new_items} item(s).")
    if new_packs == 0 and new_items == 0:
        print("Everything was already seeded — no changes made.")


if __name__ == "__main__":
    seed()
