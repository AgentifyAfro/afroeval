"""
Create the SME item-authoring Label Studio project and import AI-drafted
candidate placeholders for SMEs to review, author (in-language), and finalize.

The candidates are DRAFTS — English scenario/intent only. They are NOT validated
benchmark data and are never written to benchmarks/packs/. SMEs author the real
in-language prompt + expected-behavior spec + provenance in Label Studio; approved
items then go through the normal two-validator + IRR pipeline
(docs/BENCHMARK_ITEM_SCHEMA.md) before they can ever become pack data.

Idempotent: re-running syncs the canonical authoring project (AUTHORING_PROJECT_TITLE) —
it imports only candidate drafts whose draft_id is not already a task, so it never
duplicates. Pass --project-title only to target a different project.

Usage (from afroeval/):
    .venv/Scripts/python.exe scripts/create_authoring_project.py
    .venv/Scripts/python.exe scripts/create_authoring_project.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hitl.client import LabelStudioClient
from hitl.label_config import AUTHORING_PROJECT_TITLE, build_authoring_label_config

_CANDIDATES_FILE = Path(__file__).parent / "data" / "authoring_candidates_v2.jsonl"


def _load_candidates() -> list[dict]:
    tasks = []
    with _CANDIDATES_FILE.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{_CANDIDATES_FILE.name} line {i}: invalid JSON — {exc}") from exc
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-title", default=AUTHORING_PROJECT_TITLE)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate the config + candidates without touching Label Studio.")
    args = parser.parse_args()

    candidates = _load_candidates()
    config = build_authoring_label_config()
    print(f"Loaded {len(candidates)} draft candidate(s) from {_CANDIDATES_FILE.name}")
    print(f"Authoring label config: {len(config)} chars")

    if args.dry_run:
        print("\n--dry-run: not creating the project. Candidate draft_ids:")
        for c in candidates:
            print(f"  {c.get('draft_id', '?'):18} {c.get('target_label', '')}")
        return

    client = LabelStudioClient()
    project = client.get_or_create_project(args.project_title, config)

    # Idempotent sync: import only drafts not already present (keyed on draft_id), so re-running
    # against an established project never duplicates its tasks.
    existing = {t.get("data", {}).get("draft_id") for t in client.list_tasks(project["id"])}
    new_candidates = [c for c in candidates if c.get("draft_id") not in existing]

    print(f"\nProject '{args.project_title}' (id={project['id']}).")
    if new_candidates:
        result = client.import_tasks(project["id"], new_candidates)
        print(f"Imported {len(new_candidates)} new candidate task(s): {result}")
    else:
        print("No new candidates — project already in sync.")
    skipped = len(candidates) - len(new_candidates)
    if skipped:
        print(f"Skipped {skipped} candidate(s) already present.")
    print("\nOpen Label Studio to review:")
    print("  https://afroeval-label-studio.azurewebsites.net")


if __name__ == "__main__":
    main()
