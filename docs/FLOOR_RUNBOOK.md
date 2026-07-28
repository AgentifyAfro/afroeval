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
