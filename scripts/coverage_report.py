"""
Read-only coverage tracker for the benchmark packs.

For each pack base name it reports the newest version's scored-item count, the gap to
the 10-item coverage floor (scoring.engine.MIN_ITEMS_PER_DIMENSION), how many scored
items are validated (Tier 1 / Tier 2) versus pending, and whether the pack is
"ready to flip" — clears the floor AND every scored item is validated AND the version
is not yet the one wired into the console PACK_CATALOG.

Pure read. No DB, no writes. `--live` optionally queries Label Studio project 9 for the
upstream authored-vs-pending count per language.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/coverage_report.py
    .\\.venv\\Scripts\\python.exe scripts/coverage_report.py --live
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.loader import SINGLE_EXPERT_VALIDATED_TAG
from scoring.engine import MIN_ITEMS_PER_DIMENSION
from validation.irr import IRR_FLOOR

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"
_APP_PY = Path(__file__).parent.parent / "console" / "app.py"
_VERSION_RE = re.compile(r"^(?P<base>.+)_v(?P<ver>\d+\.\d+\.\d+)$")


def parse_pack_filename(stem: str) -> tuple[str, tuple[int, int, int]] | None:
    m = _VERSION_RE.match(stem)
    if not m:
        return None
    ver = tuple(int(p) for p in m.group("ver").split("."))
    return m.group("base"), ver


def newest_versions(packs_dir: Path) -> dict[str, Path]:
    best: dict[str, tuple[tuple[int, int, int], Path]] = {}
    for path in sorted(packs_dir.glob("*.jsonl")):
        parsed = parse_pack_filename(path.stem)
        if parsed is None:
            continue
        base, ver = parsed
        if base not in best or ver > best[base][0]:
            best[base] = (ver, path)
    return {base: path for base, (_ver, path) in best.items()}


def _load_items(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def item_tier(item: dict) -> str | None:
    """Tier of a *published* pack item from its stamped fields. None = pending validation."""
    if item.get("validation_count", 0) >= 2 and (item.get("irr_score") or 0) >= IRR_FLOOR:
        return "tier1"
    if SINGLE_EXPERT_VALIDATED_TAG in (item.get("tags") or []):
        return "tier2"
    return None


def pack_status(items: list[dict]) -> dict:
    scored = [i for i in items if not i.get("is_gold") and not i.get("is_held_out")]
    tiers = [item_tier(i) for i in scored]
    tier1 = sum(1 for t in tiers if t == "tier1")
    tier2 = sum(1 for t in tiers if t == "tier2")
    pending = sum(1 for t in tiers if t is None)
    n = len(scored)
    return {
        "scored": n,
        "floor_gap": max(0, MIN_ITEMS_PER_DIMENSION - n),
        "tier1": tier1,
        "tier2": tier2,
        "pending": pending,
        "clears_floor": n >= MIN_ITEMS_PER_DIMENSION,
        "all_validated": n > 0 and pending == 0,
    }


def released_pack_ids(app_py: Path) -> set[str]:
    """Pack ids wired into the console PACK_CATALOG (the source of truth for 'released').

    Extracted by a text scan rather than importing console/app.py, which runs Streamlit
    module-level code that fails outside a Streamlit runtime.
    """
    if not app_py.exists():
        return set()
    m = re.search(r"PACK_CATALOG\s*=\s*\[(.*?)\]", app_py.read_text(encoding="utf-8"), re.DOTALL)
    if not m:
        return set()
    return set(re.findall(r'"id":\s*"([^"]+)"', m.group(1)))


def ready_to_flip(pack_id: str, status: dict, released_ids: set[str]) -> bool:
    return status["clears_floor"] and status["all_validated"] and pack_id not in released_ids


def _live_authoring_counts() -> dict[str, tuple[int, int]]:
    """(staged, authored) per language from Label Studio project 9. Best-effort."""
    from collections import defaultdict

    from hitl.client import LabelStudioClient

    client = LabelStudioClient()
    project = client.find_project_by_title("AfroEval — SME Item Authoring v2 (2026-07-19)")
    if project is None:
        return {}
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for task in client.list_tasks(project["id"]):
        lang = task.get("data", {}).get("target_language", "?")
        out[lang][0] += 1
        if task.get("total_annotations", 0) > 0 or task.get("is_labeled"):
            out[lang][1] += 1
    return {k: (v[0], v[1]) for k, v in out.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only benchmark coverage tracker.")
    parser.add_argument("--packs-dir", type=Path, default=_PACKS_DIR)
    parser.add_argument("--live", action="store_true",
                        help="Also query Label Studio project 9 for authored/pending per language.")
    args = parser.parse_args()

    released = released_pack_ids(_APP_PY)
    newest = newest_versions(args.packs_dir)

    rows = []
    for base, path in newest.items():
        st = pack_status(_load_items(path))
        pack_id = path.stem
        rows.append((base, pack_id, st, pack_id in released, ready_to_flip(pack_id, st, released)))

    rows.sort(key=lambda r: (-r[2]["floor_gap"], r[2]["scored"]))

    print(f"{'pack':34}{'ver':9}{'scored':>7}{'gap':>5}{'T1':>4}{'T2':>4}{'pend':>6}  status")
    for base, pack_id, st, is_released, ready in rows:
        ver = "v" + pack_id[len(base) + 2:]
        tag = "READY-TO-FLIP" if ready else ("released" if is_released else "building")
        print(f"{base:34}{ver:9}{st['scored']:>7}{st['floor_gap']:>5}"
              f"{st['tier1']:>4}{st['tier2']:>4}{st['pending']:>6}  {tag}")

    if args.live:
        print("\nLabel Studio project 9 — authoring queue (staged / authored):")
        for lang, (staged, authored) in sorted(_live_authoring_counts().items()):
            print(f"  {lang:6} {authored:>3} / {staged:<3}")


if __name__ == "__main__":
    main()
