"""Logical backup of Label Studio — export EVERY project's tasks + annotations to
timestamped JSON files.

Why this exists: the self-hosted LS Community edition has no per-role delete guardrail
and no undo, so an SME could (knowingly or not) delete a project/tasks. This produces a
recoverable off-instance snapshot — the safety net for SME access until/if LS Starter
(with real RBAC) is adopted. The canonical benchmark packs live in the repo + Supabase;
this backs up the LS-side working data (authored items + SME annotations/ratings).

Run it regularly (Windows Task Scheduler / cron / CI). From afroeval/:
    .\\.venv\\Scripts\\python.exe scripts/ls_backup_export.py
    .\\.venv\\Scripts\\python.exe scripts/ls_backup_export.py --out D:\\ls_backups
Reads LABEL_STUDIO_URL + LABEL_STUDIO_API_KEY from the environment/.env.
"""
import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hitl.client import LabelStudioClient


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "untitled"


def main() -> None:
    ap = argparse.ArgumentParser(description="Back up all Label Studio projects (tasks + annotations) to JSON.")
    ap.add_argument("--out", default="ls_backups", help="output directory (default: ./ls_backups)")
    args = ap.parse_args()

    client = LabelStudioClient()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = Path(args.out) / stamp
    dest.mkdir(parents=True, exist_ok=True)

    projects = client.list_projects()
    print(f"Backing up {len(projects)} project(s) from {client.base_url} -> {dest}")

    manifest: dict = {
        "exported_at_utc": stamp, "base_url": client.base_url,
        "project_count": len(projects), "projects": [],
    }
    failures = 0
    for p in projects:
        pid, title = p["id"], p.get("title", "")
        try:
            tasks = client.export_full_snapshot(pid)
        except Exception as exc:  # noqa: BLE001 — one bad project must not abort the rest
            failures += 1
            print(f"  [FAIL] project {pid} ({title!r}): {exc}")
            manifest["projects"].append({"id": pid, "title": title, "error": str(exc)})
            continue
        fname = f"project-{pid}-{_slug(title)}.json"
        (dest / fname).write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        n_ann = sum(len(t.get("annotations", [])) for t in tasks)
        print(f"  [ok]   project {pid:>4}  tasks={len(tasks):>4}  annotations={n_ann:>4}  {title[:44]}")
        manifest["projects"].append(
            {"id": pid, "title": title, "file": fname, "tasks": len(tasks), "annotations": n_ann}
        )

    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone ({failures} failure(s)). Manifest: {dest / 'manifest.json'}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
