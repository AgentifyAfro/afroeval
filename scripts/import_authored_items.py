"""
Pull APPROVED, SME-authored benchmark items out of the Label Studio item-authoring
project and STAGE them for validation + founder sign-off.

This script deliberately does NOT publish to benchmarks/packs/. Authored items are
written to a staging file (output/authored_candidates/) and each is checked against
the publication gates from docs/BENCHMARK_ITEM_SCHEMA.md:
    - required fields present (prompt, expected_behavior, language, domain)
    - non-empty provenance
    - is_held_out == false
    - validation_count >= 2   (distinct SMEs who approved the task)
    - irr_score >= 0.60       (comes from the separate validation step; absent here)

Authoring ≠ validation: an authored item that only one SME approved is NOT yet
publishable — it still needs a second validator + IRR before a founder promotes it
into a pack. The script reports exactly which gates each item does/doesn't meet.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/import_authored_items.py
    .\\.venv\\Scripts\\python.exe scripts/import_authored_items.py --project-title "AfroEval — SME Item Authoring (2026-07-16)"
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hitl.client import LabelStudioClient
from hitl.label_config import AUTHORING_PROJECT_TITLE

_TEXT_FIELDS = ("prompt", "expected_behavior", "provenance", "sme_notes")
_CHOICE_FIELDS = ("language", "domain", "cohort", "difficulty", "status")

_STAGING_DIR = Path(__file__).parent.parent / "output" / "authored_candidates"

# Publication gates (docs/BENCHMARK_ITEM_SCHEMA.md). Named so the report is legible.
_IRR_FLOOR = 0.60
_MIN_VALIDATORS = 2


def _build_user_lookup(client: LabelStudioClient) -> dict[int, str]:
    try:
        users = client.list_users()
    except Exception:
        return {}
    return {u["id"]: u.get("email") or u.get("username") or f"user_{u['id']}" for u in users}


def _parse_authored(result: list[dict]) -> dict:
    """Map one Label Studio annotation `result` list to authored-item fields."""
    out: dict[str, str] = {}
    for entry in result:
        fn = entry.get("from_name", "")
        value = entry.get("value", {})
        if fn in _TEXT_FIELDS and value.get("text"):
            out[fn] = value["text"][0].strip()
        elif fn in _CHOICE_FIELDS and value.get("choices"):
            out[fn] = value["choices"][0]
    return out


def _build_item(task: dict, latest: dict, validation_count: int, author_id: str) -> dict:
    """Assemble a staged benchmark-item candidate from the SME's authored annotation.

    Falls back to the draft target_* metadata when the SME didn't override a choice.
    validation_count and irr_score reflect authoring state, not the validation step.
    """
    data = task.get("data", {})
    return {
        "id": data.get("draft_id", "draft-unknown"),
        "prompt": latest.get("prompt", ""),
        "expected_behavior": latest.get("expected_behavior", ""),
        "language": latest.get("language") or data.get("target_language", ""),
        "domain": latest.get("domain") or data.get("target_domain", ""),
        "cohort": latest.get("cohort") or data.get("target_cohort", ""),
        "provenance": latest.get("provenance", ""),
        "is_gold": False,
        "is_held_out": False,
        "tags": [],
        "difficulty": latest.get("difficulty", "standard"),
        "sme_author_id": author_id,
        "validation_count": validation_count,   # distinct SME approvers; needs >= 2 to publish
        "irr_score": None,                        # from the validation step, not authoring
        "_authoring_status": latest.get("status", ""),
        "_sme_notes": latest.get("sme_notes", ""),
    }


def _gate_status(item: dict) -> dict[str, bool]:
    return {
        "required_fields": all(item.get(k) for k in ("prompt", "expected_behavior", "language", "domain")),
        "provenance": bool(item.get("provenance")),
        "not_held_out": not item.get("is_held_out", False),
        f"validators>={_MIN_VALIDATORS}": item.get("validation_count", 0) >= _MIN_VALIDATORS,
        f"irr>={_IRR_FLOOR}": item.get("irr_score") is not None and item["irr_score"] >= _IRR_FLOOR,
    }


def import_authored_items(project_title: str) -> None:
    client = LabelStudioClient()
    project = client.find_project_by_title(project_title)
    if project is None:
        print(f"No Label Studio project named '{project_title}' found — nothing to import.")
        return

    tasks = client.export_annotated_tasks(project["id"])
    user_lookup = _build_user_lookup(client)

    staged: list[dict] = []
    for task in tasks:
        annotations = task.get("annotations", [])
        if not annotations:
            continue

        # Parse every annotation; keep only those the SME marked "approve".
        approved = []
        for ann in annotations:
            parsed = _parse_authored(ann.get("result", []))
            if parsed.get("status") == "approve":
                approved.append((ann, parsed))
        if not approved:
            continue

        # validation_count = distinct SMEs who approved; content from the latest approval.
        approver_ids = {a.get("completed_by") for a, _ in approved}
        latest_ann, latest = approved[-1][0], approved[-1][1]
        author_id = user_lookup.get(latest_ann.get("completed_by"), f"user_{latest_ann.get('completed_by')}")
        staged.append(_build_item(task, latest, len(approver_ids), author_id))

    if not staged:
        print("No APPROVED authored items found yet — SMEs haven't approved any tasks.")
        return

    _STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _STAGING_DIR / f"authored_{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for item in staged:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # ── Report ────────────────────────────────────────────────────────────────
    publishable = 0
    print(f"\nStaged {len(staged)} approved authored candidate(s) → {out_path}")
    print("(NOT published — these are candidates pending validation + founder sign-off.)\n")
    for item in staged:
        gates = _gate_status(item)
        ok = all(gates.values())
        publishable += ok
        marks = "  ".join(f"{'PASS' if v else 'FAIL'}:{k}" for k, v in gates.items())
        print(f"  {item['id']:20} {'READY' if ok else 'PENDING'}  [{marks}]")

    pending = len(staged) - publishable
    print(f"\n{publishable} meet all publication gates; {pending} still pending "
          f"(typically need a 2nd validator + IRR from the validation step).")
    print("Next: run these through validation (>=2 SMEs + IRR), then a founder promotes "
          "the READY ones into a new benchmarks/packs/<pack>_v<next>.jsonl on sign-off.")


def main() -> None:
    default_title = f"{AUTHORING_PROJECT_TITLE} ({datetime.now(UTC).strftime('%Y-%m-%d')})"
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-title", default=default_title)
    args = parser.parse_args()
    import_authored_items(args.project_title)


if __name__ == "__main__":
    main()
