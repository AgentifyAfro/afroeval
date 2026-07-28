# Benchmark Coverage-Floor Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simple, per-language, idempotent pipeline that turns project-9's already-staged draft backlog into floor-clearing validated pack items as authoring lands — with a coverage tracker, a promotion helper, a dry-run confidence harness, and a runbook.

**Architecture:** Three small CLI scripts (`coverage_report.py`, `promote_pack.py`, `dry_run_pipeline.py`) built from pure, importable helper functions, plus a runbook doc. Every tool is scoped to one pack and re-runnable anytime. All existing validation scripts (`import_authored_items`, `validation_export_tasks`, `validation_import_ratings`, `validation_writeback`, `validation_adjudicate`, `seed_packs_to_db`) are reused unchanged. No new drafts, no DB/Label-Studio changes.

**Tech Stack:** Python 3.12 (`.venv`), pytest, ruff, sqlmodel (existing), scikit-learn (existing, via `validation.irr`).

## Global Constraints

- Run everything via `.\.venv\Scripts\python.exe` (Python 3.12 venv).
- `benchmarks/packs/*.jsonl` are SME-validated data — **released versions are read-only**. New work only ever writes a not-yet-released working `vNext` file.
- Coverage floor is `scoring.engine.MIN_ITEMS_PER_DIMENSION` (== 10) — import it, never hardcode.
- IRR floor is `validation.irr.IRR_FLOOR` (== 0.70); Tier-2 tag is `benchmarks.loader.SINGLE_EXPERT_VALIDATED_TAG`. Import both; never redefine.
- Item UUIDs come from `benchmarks.ids.stable_item_uuid`; content hash from `validation.hashing.item_content_hash(prompt, expected_behavior)`.
- Underscore-prefixed item fields (`_authoring_status`, `_sme_notes`, `_sme_author_identity`) are staging-only and must be stripped before an item enters a pack file. `sme_author_id` (no underscore) is **kept** — import re-checks author exclusion against it.
- New scripts write LF (`\n`) for new files and preserve an existing file's newline style when appending.
- Per Dan's rule, commits await his explicit approval — the commit step in each task stages the change; hold for go-ahead when executing.
- After each task: `ruff check .` clean and `.\.venv\Scripts\python.exe -m pytest tests/ -q` green.

---

### Task 1: Coverage tracker (`coverage_report.py`)

**Files:**
- Create: `scripts/coverage_report.py`
- Test: `tests/test_coverage_report.py`

**Interfaces:**
- Produces:
  - `parse_pack_filename(stem: str) -> tuple[str, tuple[int,int,int]] | None`
  - `newest_versions(packs_dir: Path) -> dict[str, Path]`
  - `item_tier(item: dict) -> str | None` (`"tier1"` / `"tier2"` / `None`)
  - `pack_status(items: list[dict]) -> dict` (keys: `scored`, `floor_gap`, `tier1`, `tier2`, `pending`, `clears_floor`, `all_validated`)
  - `released_pack_ids(app_py: Path) -> set[str]`
  - `ready_to_flip(pack_id: str, status: dict, released_ids: set[str]) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage_report.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import coverage_report as cr  # noqa: E402


def _item(id_, scored=True, vc=0, irr=None, tags=None):
    it = {"id": id_, "prompt": "p", "expected_behavior": "e",
          "language": "ha", "domain": "agriculture",
          "validation_count": vc, "irr_score": irr, "tags": tags or []}
    if not scored:
        it["is_gold"] = True
    return it


def test_parse_pack_filename():
    assert cr.parse_pack_filename("agriculture_ha_v1.0.0") == ("agriculture_ha", (1, 0, 0))
    assert cr.parse_pack_filename("community_health_am_v1.2.0") == ("community_health_am", (1, 2, 0))
    assert cr.parse_pack_filename("not_a_pack") is None


def test_item_tier():
    assert cr.item_tier(_item("a", vc=2, irr=0.8)) == "tier1"
    assert cr.item_tier(_item("b", vc=2, irr=0.5)) is None          # below IRR floor
    assert cr.item_tier(_item("c", vc=1, tags=["single_expert_validated"])) == "tier2"
    assert cr.item_tier(_item("d", vc=0)) is None                    # pending


def test_pack_status_counts_and_floor():
    items = [_item(f"i{n}", vc=2, irr=0.8) for n in range(8)]        # 8 validated tier1
    items += [_item("gold", scored=False)]                          # excluded from scored
    st = cr.pack_status(items)
    assert st["scored"] == 8
    assert st["floor_gap"] == 2
    assert st["tier1"] == 8 and st["pending"] == 0
    assert st["clears_floor"] is False and st["all_validated"] is True


def test_ready_to_flip():
    st = {"clears_floor": True, "all_validated": True}
    assert cr.ready_to_flip("agriculture_ha_v1.1.0", st, {"agriculture_ha_v1.0.0"}) is True
    assert cr.ready_to_flip("agriculture_ha_v1.0.0", st, {"agriculture_ha_v1.0.0"}) is False  # already released
    assert cr.ready_to_flip("x_v1.1.0", {"clears_floor": False, "all_validated": True}, set()) is False


def test_released_pack_ids(tmp_path):
    app = tmp_path / "app.py"
    app.write_text(
        'LANGUAGE_NAMES = {}\n'
        'PACK_CATALOG = [\n'
        '    {"id": "mobile_money_sw_v1.0.0", "label": "MM", "language": "sw"},\n'
        '    {"id": "customer_service_en_v1.0.0", "label": "CS", "language": "en"},\n'
        ']\n'
        'OTHER = ["id"]\n',
        encoding="utf-8",
    )
    assert cr.released_pack_ids(app) == {"mobile_money_sw_v1.0.0", "customer_service_en_v1.0.0"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_coverage_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'coverage_report'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/coverage_report.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_coverage_report.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Smoke-test against the real packs**

Run: `.\.venv\Scripts\python.exe scripts/coverage_report.py`
Expected: a table listing every pack; the 11 `v1.0.0` packs show `gap` 1–6 as `released` (they are the current catalog versions; their pre-validation items count as `pend`), `community_health_am v1.2.0` shows `gap 0` (T1 23).

- [ ] **Step 6: Commit**

```bash
git add scripts/coverage_report.py tests/test_coverage_report.py
git commit -m "feat(coverage): read-only pack coverage-floor tracker

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Promotion helper (`promote_pack.py`)

**Files:**
- Create: `scripts/promote_pack.py`
- Test: `tests/test_promote_pack.py`

**Interfaces:**
- Consumes: staged items from `output/authored_candidates/*.jsonl` (shape from `import_authored_items._build_item`).
- Produces:
  - `bump_minor(ver: tuple[int,int,int]) -> tuple[int,int,int]`
  - `format_version(ver: tuple[int,int,int]) -> str`
  - `clean_for_pack(staged: dict) -> dict`
  - `select_staged(staged: list[dict], pack_items: list[dict], ids: list[str] | None) -> list[dict]`
  - `build_next_pack(base: str, packs_dir: Path, staged: list[dict], released_ids: set[str], ids: list[str] | None = None, to_version: str | None = None) -> tuple[Path, list[dict], list[str], int]` returning `(target_path, rows, added_ids, projected_scored)`; raises `ValueError` if the target version is already released.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_promote_pack.py
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import promote_pack as pp  # noqa: E402


def _write_pack(path, items):
    path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def _staged(id_, lang="ha"):
    return {"id": id_, "prompt": "p", "expected_behavior": "e", "language": lang,
            "domain": "agriculture", "cohort": "informal_rural", "provenance": "src 2020",
            "is_gold": False, "is_held_out": False, "tags": [], "difficulty": "standard",
            "sme_author_id": "sme-abc123", "validation_count": 1, "irr_score": None,
            "_authoring_status": "approve", "_sme_notes": "note", "_sme_author_identity": "a@b.com"}


def test_bump_minor():
    assert pp.bump_minor((1, 0, 0)) == (1, 1, 0)
    assert pp.format_version((1, 1, 0)) == "v1.1.0"


def test_clean_for_pack_strips_internal_and_resets_validation():
    out = pp.clean_for_pack(_staged("x"))
    assert not any(k.startswith("_") for k in out)     # underscore fields gone
    assert out["sme_author_id"] == "sme-abc123"        # kept for author exclusion
    assert out["validation_count"] == 0 and out["irr_score"] is None  # pending


def test_select_staged_by_ids_and_by_language():
    staged = [_staged("a", "ha"), _staged("b", "sw")]
    pack_items = [{"language": "ha"}]
    assert {i["id"] for i in pp.select_staged(staged, pack_items, None)} == {"a"}   # lang match
    assert {i["id"] for i in pp.select_staged(staged, pack_items, ["b"])} == {"b"}  # explicit ids


def test_build_next_pack_appends_and_projects_floor(tmp_path):
    cur = [dict(_staged(f"ag-ha-{n:03d}"), validation_count=2, irr_score=0.8) for n in range(8)]
    for i in cur:
        i.pop("_authoring_status", None); i.pop("_sme_notes", None); i.pop("_sme_author_identity", None)
    _write_pack(tmp_path / "agriculture_ha_v1.0.0.jsonl", cur)
    staged = [_staged(f"ag-ha-2{n:02d}") for n in range(3)]
    target, rows, added, scored = pp.build_next_pack(
        "agriculture_ha", tmp_path, staged, released_ids={"agriculture_ha_v1.0.0"})
    assert target.name == "agriculture_ha_v1.1.0.jsonl"
    assert added == ["ag-ha-200", "ag-ha-201", "ag-ha-202"]
    assert scored == 11


def test_build_next_pack_is_idempotent(tmp_path):
    _write_pack(tmp_path / "p_ha_v1.0.0.jsonl", [dict(_staged("p-1"), validation_count=2, irr_score=0.8)])
    staged = [_staged("p-2")]
    target, rows, added, scored = pp.build_next_pack("p_ha", tmp_path, staged, {"p_ha_v1.0.0"})
    _write_pack(target, rows)                     # simulate --apply
    _, rows2, added2, _ = pp.build_next_pack("p_ha", tmp_path, staged, {"p_ha_v1.0.0"})
    assert added2 == []                           # already present -> no dupes
    assert len(rows2) == len(rows)


def test_build_next_pack_refuses_released_target(tmp_path):
    _write_pack(tmp_path / "p_ha_v1.0.0.jsonl", [_staged("p-1")])
    with pytest.raises(ValueError, match="already released"):
        pp.build_next_pack("p_ha", tmp_path, [], {"p_ha_v1.0.0"}, to_version="v1.0.0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_promote_pack.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'promote_pack'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/promote_pack.py
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
    return "v%d.%d.%d" % ver


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_promote_pack.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/promote_pack.py tests/test_promote_pack.py
git commit -m "feat(promote): idempotent per-pack vNext promotion helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Parse-seam regression tests

The two Label Studio parse functions are already pure. This task pins them with fixtures — including a non-Latin-script provenance — so the Amharic citation-regex class of bug (a `\b`-vs-digit-boundary miss) can never regress. No production code changes.

**Files:**
- Test: `tests/test_parse_seams.py`

**Interfaces:**
- Consumes: `import_authored_items._parse_authored`, `import_authored_items._cites_external_source`, `validation_import_ratings._parse`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parse_seams.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import import_authored_items as iai  # noqa: E402
import validation_import_ratings as vir  # noqa: E402


def test_parse_authored_extracts_text_and_choice_fields():
    result = [
        {"from_name": "prompt", "value": {"text": ["  ናይ ጤና ጥያቄ  "]}},
        {"from_name": "expected_behavior", "value": {"text": ["Answer safely."]}},
        {"from_name": "language", "value": {"choices": ["am"]}},
        {"from_name": "status", "value": {"choices": ["approve"]}},
    ]
    parsed = iai._parse_authored(result)
    assert parsed["prompt"] == "ናይ ጤና ጥያቄ"          # trimmed
    assert parsed["language"] == "am"
    assert parsed["status"] == "approve"


def test_cites_external_source_handles_non_latin_year():
    assert iai._cites_external_source("የጤና ሚኒስቴር መመሪያ በ2021 ዓ.ም") is True   # Amharic + glued year
    assert iai._cites_external_source("WHO guidelines, 2019") is True
    assert iai._cites_external_source("https://moh.gov.et/epi") is True
    assert iai._cites_external_source("SME authored") is False               # self-referential
    assert iai._cites_external_source("") is False


def test_ratings_parse_flattens_instrument():
    annotation = {"result": [
        {"from_name": "factual_accuracy", "value": {"choices": ["yes"]}},
        {"from_name": "cultural_score", "value": {"choices": ["4"]}},
        {"from_name": "verdict", "value": {"choices": ["pass"]}},
        {"from_name": "justification", "value": {"text": ["culturally sound"]}},
    ]}
    parsed = vir._parse(annotation)
    assert parsed["factual_accuracy"] == "yes"
    assert parsed["cultural_score"] == "4"
    assert parsed["justification"] == "culturally sound"
```

- [ ] **Step 2: Run test to verify it fails (then passes)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_parse_seams.py -q`
Expected: PASS immediately (the functions exist). If the non-Latin year assertion ever fails, the citation regex has regressed — that is the guard's whole point.

- [ ] **Step 3: Commit**

```bash
git add tests/test_parse_seams.py
git commit -m "test(seams): pin LS parse seams incl. non-Latin citation regex

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Dry-run confidence harness (`dry_run_pipeline.py`)

Exercises the real promote → writeback core end-to-end on synthetic data in a temp dir — no DB, no Label Studio. Proves a pack can go from below-floor + pending to floor-cleared + Tier-1, and that a factual dispute raises adjudication.

**Files:**
- Create: `scripts/dry_run_pipeline.py`
- Test: `tests/test_dry_run_pipeline.py`

**Interfaces:**
- Consumes: `promote_pack.build_next_pack`; `validation_writeback.load_packs`, `.compute_item_results`, `.apply_results`; `validation.hashing.item_content_hash`; `coverage_report.pack_status`.
- Produces: `run(tmp: Path) -> dict` with keys `scored`, `tier1`, `adjudicate` (list of item ids needing adjudication).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dry_run_pipeline.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import dry_run_pipeline as drp  # noqa: E402


def test_dry_run_clears_floor_and_flags_dispute(tmp_path):
    result = drp.run(tmp_path)
    assert result["scored"] >= 10           # promoted past the floor
    assert result["tier1"] >= 10            # the agreeing pair reached Tier 1
    assert result["adjudicate"]             # the seeded factual dispute was caught
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dry_run_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dry_run_pipeline'`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/dry_run_pipeline.py
"""
End-to-end confidence harness for the coverage-floor pipeline.

Runs the REAL promote -> writeback code on synthetic data in a temp directory — no prod DB,
no Label Studio. Proves a pack goes from below-floor + pending to floor-cleared + Tier 1,
and that a factual-accuracy dispute raises adjudication. De-risks the pipeline before any
SME authors a live item.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/dry_run_pipeline.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # sibling scripts

from validation.hashing import item_content_hash
from validation.irr import batch_key  # noqa: F401  (kept for parity; pair math lives in writeback)

import coverage_report as cr
import promote_pack as pp
import validation_writeback as vw

_BASE = "dryrun_health_xx"
_LANG = "xx"


def _authored(n: int) -> dict:
    return {"id": f"dr-xx-{200 + n:03d}", "prompt": f"prompt {n}", "expected_behavior": f"behave {n}",
            "language": _LANG, "domain": "community_health", "cohort": "informal_rural",
            "provenance": "guideline 2020", "is_gold": False, "is_held_out": False, "tags": [],
            "difficulty": "standard", "sme_author_id": "sme-author0", "validation_count": 1,
            "irr_score": None, "_authoring_status": "approve", "_sme_notes": "", "_sme_author_identity": "a@b.com"}


def _write_pack(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def run(tmp: Path) -> dict:
    packs = tmp / "packs"
    packs.mkdir(parents=True, exist_ok=True)

    # 1. Synthetic released base pack: 2 scored, pending validation (below the floor).
    base_rows = [dict(_authored(n)) for n in (0, 1)]
    base_rows = [pp.clean_for_pack(r) for r in base_rows]
    _write_pack(packs / f"{_BASE}_v1.0.0.jsonl", base_rows)

    # 2. Promote 12 authored candidates -> vNext (append), clearing the floor.
    staged = [_authored(n) for n in range(2, 14)]
    target, rows, added, scored = pp.build_next_pack(
        _BASE, packs, staged, released_ids={f"{_BASE}_v1.0.0"})
    _write_pack(target, rows)

    # 3. Synthetic ratings from a distinct, agreeing pair over the 12 new items (kappa=1.0).
    #    One item gets a factual-accuracy dispute so adjudication must trigger.
    va, vb = "sme-alpha", "sme-beta"
    validations = []
    for i, item in enumerate(rows):
        if item["id"] in ("dr-xx-200", "dr-xx-201"):   # the two base items stay pending
            continue
        h = item_content_hash(item["prompt"], item["expected_behavior"])
        a_fact = "yes"
        b_fact = "no" if item["id"] == "dr-xx-205" else "yes"   # seeded dispute
        validations.append({"item_id": item["id"], "validator_id": va, "cultural_score": 4,
                            "factual_accuracy": a_fact, "item_content_hash": h})
        validations.append({"item_id": item["id"], "validator_id": vb, "cultural_score": 4,
                            "factual_accuracy": b_fact, "item_content_hash": h})

    # 4. Writeback: compute per-item results and stamp the vNext pack in the temp dir.
    items, rows_by_path, newline_by_path = vw.load_packs(packs)
    results = vw.compute_item_results(validations, items)
    vw.apply_results(results, rows_by_path, newline_by_path)

    # 5. Read back the stamped pack and report coverage.
    stamped = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    status = cr.pack_status(stamped)
    adjudicate = [i for i, r in results.items() if r["needs_adjudication"]]
    return {"scored": status["scored"], "tier1": status["tier1"], "adjudicate": adjudicate}


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        result = run(Path(d))
    print("Dry-run pipeline result:")
    print(f"  scored items in vNext : {result['scored']}  (floor 10)")
    print(f"  Tier-1 validated      : {result['tier1']}")
    print(f"  needs adjudication    : {result['adjudicate']}")
    ok = result["scored"] >= 10 and result["tier1"] >= 10 and bool(result["adjudicate"])
    print("\nPASS — promote+writeback core is sound." if ok else "\nFAIL — investigate before relying on the pipeline.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dry_run_pipeline.py -q`
Expected: PASS (1 test).

- [ ] **Step 5: Smoke-test the harness CLI**

Run: `.\.venv\Scripts\python.exe scripts/dry_run_pipeline.py`
Expected: prints `scored 14`, `Tier-1 11` (12 rated, minus the 1 disputed item which is correctly held for adjudication), one adjudication id (`dr-xx-205`), and `PASS`.

- [ ] **Step 6: Commit**

```bash
git add scripts/dry_run_pipeline.py tests/test_dry_run_pipeline.py
git commit -m "feat(dry-run): end-to-end promote+writeback confidence harness

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Runbook (`docs/FLOOR_RUNBOOK.md`)

A short, flexible checklist tying the tools together. Not a rigid sequence — each step runs whenever a language produces new output.

**Files:**
- Create: `docs/FLOOR_RUNBOOK.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Coverage-Floor Runbook — per language, no lockstep

Goal: get every pack to >= 10 validated scored items. Run each step **whenever that
language produces new output** — languages progress independently, in any order.

## Prerequisites (once per new hire)
- Add the hire to `scripts/data/validator_roster.json` with their `languages`, e.g.
  `{"validator_id": "sme-xxxxxxxx", "languages": ["yo"]}`. A validator can never validate
  an item they authored, and Tier 1 needs two distinct validators who speak the language.
- Pseudonymous id = `validation.identity.pseudonymise(email)`.

## Check status anytime
    .\.venv\Scripts\python.exe scripts/coverage_report.py          # floor gaps + ready-to-flip
    .\.venv\Scripts\python.exe scripts/coverage_report.py --live   # + LS authoring queue

## When a language has newly-authored items
1. Pull approved authored items from Label Studio into staging:
       .\.venv\Scripts\python.exe scripts/import_authored_items.py --project-title "AfroEval — SME Item Authoring v2 (2026-07-19)"
2. Promote them into the pack's working vNext (dry-run, then apply):
       .\.venv\Scripts\python.exe scripts/promote_pack.py --pack <base>
       .\.venv\Scripts\python.exe scripts/promote_pack.py --pack <base> --apply
   `git diff` MUST touch only `<base>_vNext.jsonl`. Re-running is safe — it never dupes.
3. Seed the new items to the DB (needed before validation can find them):
       .\.venv\Scripts\python.exe scripts/seed_packs_to_db.py

## When that language's validators have rated items
4. Export the vNext items to the validation project, pinning the validator pair so one
   pair accumulates the >= 10 shared items a kappa needs:
       .\.venv\Scripts\python.exe scripts/validation_export_tasks.py --validators sme-aaa,sme-bbb
5. Import ratings, then stamp the pack:
       .\.venv\Scripts\python.exe scripts/validation_import_ratings.py
       .\.venv\Scripts\python.exe scripts/validation_writeback.py --dry-run
       .\.venv\Scripts\python.exe scripts/validation_writeback.py --apply
   **Scope guard:** writeback stamps every pack file sharing an item id. Confirm
   `git diff` touches only the target vNext; `git checkout --` any older version it brushed
   (the multi-version stamping trap from the Amharic run).
6. Resolve anything flagged:
       .\.venv\Scripts\python.exe scripts/validation_adjudicate.py

## When a pack is ready
`coverage_report` marks it `READY-TO-FLIP` (clears 10 + all scored items validated).
Flip it by editing `PACK_CATALOG` in `console/app.py` to the new version id, commit, and
reboot the console. The flipped version is now released and immutable — never edit it in
place; start a further vNext instead.

## De-risking / sanity check
    .\.venv\Scripts\python.exe scripts/dry_run_pipeline.py   # promote+writeback on synthetic data
```

- [ ] **Step 2: Verify the commands reference real scripts**

Run: `.\.venv\Scripts\python.exe scripts/promote_pack.py --help` and `.\.venv\Scripts\python.exe scripts/coverage_report.py --help`
Expected: both print usage without error.

- [ ] **Step 3: Commit**

```bash
git add docs/FLOOR_RUNBOOK.md
git commit -m "docs(runbook): per-language coverage-floor pipeline runbook

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Final verification

- [ ] **Step 1: Full suite + lint**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q` then `ruff check .`
Expected: all tests pass (existing 352 + the new coverage/promote/seam/dry-run tests), ruff clean.

- [ ] **Step 2: Real tracker read**

Run: `.\.venv\Scripts\python.exe scripts/coverage_report.py`
Expected: the 11 `v1.0.0` packs show their 1–6 gaps as `released` (current catalog versions); `community_health_am_v1.2.0` shows `gap 0`. No pack shows `READY-TO-FLIP` yet (nothing new authored, no working vNext files).

---

## Self-Review

**Spec coverage:**
- Coverage tracker → Task 1. Promotion helper → Task 2. Dry-run harness + parse-seam tests → Tasks 3 & 4. Runbook (roster prereq + scope-to-vNext guardrail) → Task 5. ✓
- Core principle (per-language, idempotent, re-runnable) → `build_next_pack` idempotency test (Task 2) + runbook framing (Task 5). ✓
- "Ready to flip = clears 10 AND validated AND not released" pinned in `ready_to_flip` + `pack_status` tests (Task 1) — resolves the spec's deliberate soft spot. ✓
- No auto catalog-flip → flip is a manual `PACK_CATALOG` edit in the runbook only. ✓
- Immutability of released versions → `build_next_pack` refusal test (Task 2) + scope guard (Task 5). ✓
- No new draft generation → nothing in the plan writes to project 9 or generates drafts. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every step has real code or a concrete command. ✓

**Type consistency:** `pack_status` returns the same dict keys consumed by `ready_to_flip` and the dry-run harness (`scored`, `tier1`, `clears_floor`, `all_validated`). `build_next_pack` returns `(Path, list, list, int)` as consumed in Task 4. `item_content_hash(prompt, expected_behavior)` and `compute_item_results(validations, items)` match the real signatures in `validation_writeback`. ✓
