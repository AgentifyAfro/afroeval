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

That is Tier 1. Methodology v1.3 adds Tier 2 — single-expert validated — for items whose
one validator holds BOTH native/fluent command of the language AND domain expertise. Tier 2
keeps validation_count at 1 and irr_score null (IRR is undefined for a single rater and is
never estimated), and in exchange requires an authoritative external source in provenance,
is_gold false, the `single_expert_validated` tag, dated founder sign-off, and a cap of 40%
of the target pack.

Authoring ≠ validation: an authored item that only one SME approved is NOT automatically
publishable. The script reports which tier each item qualifies for and what is missing; it
never applies the Tier 2 tag itself, since that tag represents the founder's sign-off.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/import_authored_items.py
    .\\.venv\\Scripts\\python.exe scripts/import_authored_items.py --project-title "AfroEval — SME Item Authoring (2026-07-16)"
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.loader import SINGLE_EXPERT_VALIDATED_TAG
from hitl.client import LabelStudioClient
from hitl.label_config import AUTHORING_PROJECT_TITLE

_TEXT_FIELDS = ("prompt", "expected_behavior", "provenance", "sme_notes")
_CHOICE_FIELDS = ("language", "domain", "cohort", "difficulty", "status")

_STAGING_DIR = Path(__file__).parent.parent / "output" / "authored_candidates"

# Publication gates (docs/BENCHMARK_ITEM_SCHEMA.md). Named so the report is legible.
_IRR_FLOOR = 0.60
_MIN_VALIDATORS = 2

# Tier 2 — single-expert validated (Methodology v1.3). Tag lives in benchmarks.loader so
# the packs, this script, and the reporting disclosure all read one definition.
_TIER2_TAG = SINGLE_EXPERT_VALIDATED_TAG
_TIER2_MAX_SHARE = 0.40   # Max Tier 2 share of a pack's SCORED set — see tier2_share().

# Provenance that only points back at the author does not establish an external source,
# so it cannot satisfy Tier 2 (where one expert's judgment is the only review).
_SELF_REFERENTIAL_PROVENANCE = re.compile(
    r"\b(sme|self|internal(ly)?|founder|author)[\s\-]*(authored|written|generated)\b",
    re.IGNORECASE,
)

# A Tier 2 citation must be checkable by someone else later, so it has to identify *which*
# document — a year, edition, section, or URL. "Ministry of Health Website" names a
# publisher but no source, and cannot be verified or challenged.
#
# This is deliberately stricter than Tier 1, which only requires provenance to be non-empty:
# 18 provenance strings in the existing packs ("Yoruba cultural norms documentation",
# "AfroEval safety red-team set v1") would not clear this bar. That is intended and is NOT
# retroactive — those items were dual-validated, so two independent reviewers stood behind
# them. A Tier 2 item has one, which is why its source has to carry more of the weight.
_CITATION_MARKER = re.compile(
    r"\b(19|20)\d{2}\b"          # year
    r"|\b\d+(st|nd|rd|th)\s*ed\b"  # edition
    r"|\bv?\d+\.\d+\b"           # version
    r"|§|\bhttps?://",           # section marker or URL
    re.IGNORECASE,
)


def _cites_external_source(provenance: str) -> bool:
    """True when provenance names a checkable external source rather than the author."""
    p = (provenance or "").strip()
    if not p or _SELF_REFERENTIAL_PROVENANCE.search(p):
        return False
    return bool(_CITATION_MARKER.search(p))


def _pseudonymise(identity: str) -> str:
    """Map a Label Studio identity (usually an email) to a stable pseudonymous author id.

    `sme_author_id` is published inside pack files, which are shared with clients — the
    schema requires it to be anonymised. Label Studio hands us real emails, so hashing
    happens here, at the boundary, rather than being left to each promotion step to
    remember. Deterministic, so the same SME keeps the same id across imports.

    The real identity is kept alongside as `_sme_author_identity`; underscore-prefixed
    fields are staging-only and are stripped when an item is promoted into a pack.
    """
    if not identity:
        return ""
    return "sme-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]


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
        "sme_author_id": _pseudonymise(author_id),
        "validation_count": validation_count,   # distinct SME approvers; needs >= 2 to publish
        "irr_score": None,                        # from the validation step, not authoring
        "_authoring_status": latest.get("status", ""),
        "_sme_notes": latest.get("sme_notes", ""),
        "_sme_author_identity": author_id,      # local only — never promote (see _pseudonymise)
    }


def _gate_status(item: dict) -> dict[str, bool]:
    """Tier 1 gates (dual-SME). See _tier2_status for the single-expert exception."""
    return {
        "required_fields": all(item.get(k) for k in ("prompt", "expected_behavior", "language", "domain")),
        "provenance": bool(item.get("provenance")),
        "not_held_out": not item.get("is_held_out", False),
        f"validators>={_MIN_VALIDATORS}": item.get("validation_count", 0) >= _MIN_VALIDATORS,
        f"irr>={_IRR_FLOOR}": item.get("irr_score") is not None and item["irr_score"] >= _IRR_FLOOR,
    }


def _tier2_status(item: dict) -> dict[str, bool]:
    """Tier 2 gates — single-expert validated (Methodology v1.3, BENCHMARK_ITEM_SCHEMA.md).

    Deliberately stricter than Tier 1 on provenance and gold status: a Tier 2 item rests on
    one unreplicated judgment, so its external source must be real and it may never serve as
    a calibration anchor. irr_score must stay null — IRR is undefined for a single rater and
    is never estimated to clear a gate.
    """
    return {
        "required_fields": all(item.get(k) for k in ("prompt", "expected_behavior", "language", "domain")),
        "provenance_cites_source": _cites_external_source(item.get("provenance", "")),
        "not_held_out": not item.get("is_held_out", False),
        "not_gold": not item.get("is_gold", False),
        "validators==1": item.get("validation_count", 0) == 1,
        "irr_is_null": item.get("irr_score") is None,
        "tagged": _TIER2_TAG in (item.get("tags") or []),
    }


def tier2_share(items: list[dict]) -> float:
    """Tier 2 share of a pack's SCORED set (Methodology v1.3, publication rule 9).

    Gold and held-out items are excluded from the denominator: they are never scored, so
    counting them would let a pack dilute its way under the cap without changing what any
    evaluation actually rests on. Returns 0.0 for a pack with no scored items.
    """
    scored = [i for i in items if not i.get("is_gold") and not i.get("is_held_out")]
    if not scored:
        return 0.0
    return sum(1 for i in scored if _TIER2_TAG in (i.get("tags") or [])) / len(scored)


def _tier_of(item: dict) -> str | None:
    """Return 'tier1', 'tier2', or None if the item is publishable under neither."""
    if all(_gate_status(item).values()):
        return "tier1"
    if all(_tier2_status(item).values()):
        return "tier2"
    return None


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
    tier1 = tier2_eligible = 0
    print(f"\nStaged {len(staged)} approved authored candidate(s) → {out_path}")
    print("(NOT published — these are candidates pending validation + founder sign-off.)\n")
    for item in staged:
        gates = _gate_status(item)
        if all(gates.values()):
            tier1 += 1
            marks = "  ".join(f"PASS:{k}" for k in gates)
            print(f"  {item['id']:20} READY (tier 1)      [{marks}]")
            continue

        # Tier 2 minus the tag, which is the founder's stamp applied at promotion.
        t2 = _tier2_status(item)
        blockers = [k for k, v in t2.items() if not v and k != "tagged"]
        if not blockers:
            tier2_eligible += 1
            print(f"  {item['id']:20} TIER-2 ELIGIBLE     [needs founder sign-off + "
                  f"{_TIER2_TAG} tag at promotion]")
        else:
            fails = "  ".join(f"FAIL:{k}" for k in blockers)
            print(f"  {item['id']:20} PENDING             [tier1: "
                  f"{'  '.join(f'FAIL:{k}' for k, v in gates.items() if not v)} | tier2: {fails}]")

    pending = len(staged) - tier1 - tier2_eligible
    print(f"\n{tier1} meet Tier 1 (dual-SME + IRR); {tier2_eligible} are Tier 2 eligible "
          f"(single expert); {pending} meet neither.")
    if tier2_eligible:
        print(f"Tier 2 requires a validator qualified in BOTH the item's language and domain, "
              f"dated founder sign-off, and <= {_TIER2_MAX_SHARE:.0%} of the target pack. "
              f"irr_score stays null — it is never estimated for a single rater.")
    print("Next: a founder promotes qualifying items into a new "
          "benchmarks/packs/<pack>_v<next>.jsonl on sign-off.")


def main() -> None:
    default_title = f"{AUTHORING_PROJECT_TITLE} ({datetime.now(UTC).strftime('%Y-%m-%d')})"
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-title", default=default_title)
    args = parser.parse_args()
    import_authored_items(args.project_title)


if __name__ == "__main__":
    main()
