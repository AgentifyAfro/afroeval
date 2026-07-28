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

import coverage_report as cr
import promote_pack as pp
import validation_writeback as vw

from validation.hashing import item_content_hash
from validation.irr import batch_key  # noqa: F401  (kept for parity; pair math lives in writeback)

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
