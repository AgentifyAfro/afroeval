"""
Promote SME-authored, staged items into a pack's working vNext file.

Idempotent and per-pack: run it whenever a language finishes authoring more items.
It APPENDS staged candidates to a not-yet-released working version, keyed on item id, so
re-runs never duplicate and partial batches simply accumulate. Released pack versions are
never touched. Validation is a separate step — promoted items start pending
(validation_count = 0, irr_score = null) until validation_writeback stamps them.

Reads staged items from output/authored_candidates/ (produced by import_authored_items.py).

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/promote_pack.py --pack agriculture_ha
    .\\.venv\\Scripts\\python.exe scripts/promote_pack.py --pack agriculture_ha --apply
    .\\.venv\\Scripts\\python.exe scripts/promote_pack.py --pack safety_mixed --ids dr-1,dr-2 --apply
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"
_STAGING_DIR = Path(__file__).parent.parent / "output" / "authored_candidates"
_APP_PY = Path(__file__).parent.parent / "console" / "app.py"
_VERSION_RE = re.compile(r"^(?P<base>.+)_v(?P<ver>\d+\.\d+\.\d+)$")


def bump_minor(ver: tuple[int, int, int]) -> tuple[int, int, int]:
    return (ver[0], ver[1] + 1, ver[2])


def format_version(ver: tuple[int, int, int]) -> str:
    return f"v{ver[0]}.{ver[1]}.{ver[2]}"


def _parse_version(s: str) -> tuple[int, int, int]:
    return tuple(int(p) for p in s.lstrip("v").split("."))  # type: ignore[return-value]


def clean_for_pack(staged: dict) -> dict:
    """Strip staging-only underscore fields; reset validation fields to pending."""
    item = {k: v for k, v in staged.items() if not k.startswith("_")}
    item["validation_count"] = 0
    item["irr_score"] = None
    item.setdefault("tags", [])
    return item


def select_staged(staged: list[dict], pack_items: list[dict], ids: list[str] | None) -> list[dict]:
    """Pick staged items destined for this pack.

    ids given -> exactly those (order preserved from `ids`). Otherwise -> staged items
    whose language matches any language already in the pack (handles mixed-language packs;
    an empty pack falls back to all staged items).
    """
    if ids:
        by_id = {s.get("id"): s for s in staged}
        return [by_id[i] for i in ids if i in by_id]
    langs = {i.get("language") for i in pack_items}
    if not langs:
        return list(staged)
    return [s for s in staged if s.get("language") in langs]


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _versions_of(base: str, packs_dir: Path) -> dict[tuple[int, int, int], Path]:
    out: dict[tuple[int, int, int], Path] = {}
    for path in sorted(packs_dir.glob(f"{base}_v*.jsonl")):
        m = _VERSION_RE.match(path.stem)
        if m and m.group("base") == base:
            out[_parse_version(m.group("ver"))] = path
    return out


def build_next_pack(
    base: str,
    packs_dir: Path,
    staged: list[dict],
    released_ids: set[str],
    ids: list[str] | None = None,
    to_version: str | None = None,
) -> tuple[Path, list[dict], list[str], int]:
    versions = _versions_of(base, packs_dir)
    if not versions:
        raise ValueError(f"No existing versions for pack '{base}' in {packs_dir}")

    released_vers = [v for v in versions if f"{base}_{format_version(v)}" in released_ids]
    base_ver = max(released_vers) if released_vers else max(versions)
    target_ver = _parse_version(to_version) if to_version else bump_minor(base_ver)
    target_id = f"{base}_{format_version(target_ver)}"
    if target_id in released_ids:
        raise ValueError(f"Target {target_id} is already released — pick a higher --to-version.")

    target_path = packs_dir / f"{target_id}.jsonl"
    # Append to the working file if it already exists, else seed from the released base version.
    seed_path = target_path if target_path.exists() else versions[base_ver]
    rows = _load_jsonl(seed_path)
    existing_ids = {r["id"] for r in rows}

    picked = select_staged(staged, _load_jsonl(versions[base_ver]), ids)
    added: list[str] = []
    for s in picked:
        if s.get("id") in existing_ids:
            continue
        rows.append(clean_for_pack(s))
        existing_ids.add(s["id"])
        added.append(s["id"])

    scored = sum(1 for r in rows if not r.get("is_gold") and not r.get("is_held_out"))
    return target_path, rows, added, scored


def _newest_staging_file() -> Path | None:
    files = sorted(_STAGING_DIR.glob("authored_*.jsonl"))
    return files[-1] if files else None


def _write_pack(path: Path, rows: list[dict]) -> None:
    newline = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    path.write_bytes("".join(json.dumps(r, ensure_ascii=False) + newline for r in rows).encode("utf-8"))


def main() -> None:
    from coverage_report import released_pack_ids  # reuse the single catalog reader

    parser = argparse.ArgumentParser(description="Promote staged authored items into a pack's vNext.")
    parser.add_argument("--pack", required=True, help="Pack base name, e.g. agriculture_ha")
    parser.add_argument("--staging", type=Path, default=None,
                        help="Staging JSONL (default: newest in output/authored_candidates/).")
    parser.add_argument("--ids", default=None, help="Comma-separated staged ids to promote (default: by language).")
    parser.add_argument("--to-version", default=None, help="Override target version, e.g. v1.2.0.")
    parser.add_argument("--apply", action="store_true", help="Write the vNext file (default: dry-run).")
    args = parser.parse_args()

    staging = args.staging or _newest_staging_file()
    if staging is None:
        print("No staging file found in output/authored_candidates/. Run import_authored_items.py first.")
        return
    staged = _load_jsonl(staging)
    ids = args.ids.split(",") if args.ids else None

    target, rows, added, scored = build_next_pack(
        args.pack, _PACKS_DIR, staged, released_pack_ids(_APP_PY), ids=ids, to_version=args.to_version)

    print(f"Pack     : {args.pack}")
    print(f"Staging  : {staging}")
    print(f"Target   : {target.name}")
    print(f"Adding   : {len(added)} item(s) -> {added}")
    print(f"Projected scored items: {scored} (floor 10 -> {'CLEARED' if scored >= 10 else f'need {10 - scored} more'})")
    if not args.apply:
        print("\nDry-run. Re-run with --apply to write the vNext file, then git diff it.")
        return
    _write_pack(target, rows)
    print(f"\nWrote {target}. Review with `git diff` (should touch only this file), then seed + validate.")


if __name__ == "__main__":
    main()
