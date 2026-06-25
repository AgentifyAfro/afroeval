# RLS Fix for Public Tables — Design

**Date:** 2026-06-25
**Status:** Approved, pending implementation plan

## Problem

Supabase's security advisor flags 9 tables in the `public` schema with Row Level
Security (RLS) disabled: `benchmark_packs`, `benchmark_items`, `assessments`, `runs`,
`model_responses`, `metric_results`, `scorecards`, `response_reviews`,
`alembic_version`. With RLS disabled, these tables are fully exposed to the `anon`
and `authenticated` Postgres roles that Supabase's PostgREST API (and any client
using the project's anon key) authenticates as — anyone with the anon key can read
or modify every row directly via `https://yjaftvqpkrtyjtkfdgen.supabase.co/rest/v1/...`,
completely bypassing the console application.

This was identified as a follow-up during the 2026-06-25 two-tier console auth work
(see `2026-06-25-two-tier-auth-design.md`), deliberately scoped out of that change
as a separate task. It is the larger of the two exposures: the console-level fix
closes access through the app's UI, but anyone who already has (or finds) the anon
key can still hit these tables directly, including `response_reviews` — the same
table whose SME-email exposure motivated the console fix in the first place.

## Why this fix is safe

The AfroEval console and API connect to Postgres exclusively via `db/session.py`,
which uses `DATABASE_URL` (a direct Postgres connection through Supabase's session
pooler, authenticating as the `postgres` role) — never through `supabase-py`'s
PostgREST client (`.table()` calls). A repo-wide search confirms the only
`supabase-py` usage anywhere in the codebase is `auth/client.py`, which exclusively
calls `.auth.sign_in_with_password()` for the console login — it never queries a
data table.

Postgres table owners (and superuser-equivalent roles, which `postgres` is here)
bypass RLS entirely, regardless of whether RLS is enabled or what policies exist.
This means: enabling RLS on these 9 tables with **zero policies** — the strictest
possible setting — has no effect on the app's own queries, because the app never
authenticates as `anon`/`authenticated`. It only closes the previously-open
PostgREST path that those roles use.

Verified directly: the live DB's `alembic_version` is at `9cb5227a017d`, matching
the latest migration file in the repo — no drift between the repo's migration
history and the deployed schema.

## Non-goals

- **No RLS policies are added.** Zero policies + RLS enabled = deny-all for every
  role except the table owner, which is exactly correct here: there is no current,
  legitimate use case for `anon`/`authenticated` access to any of these 9 tables.
  If a future feature needs PostgREST/anon-key access to specific rows, that's a
  new, separate design decision — not assumed or pre-built here.
- **No changes to `db/session.py`, `auth/client.py`, or any application code.** This
  is a pure database-schema change.
- **No GRANT/REVOKE-based alternative.** RLS is the mechanism Supabase's own
  tooling and security advisor check for; revoking privileges separately would
  still leave the advisor flagging these tables indefinitely and fights the
  platform's conventions for no benefit.

## Implementation

**Migration file:** `db/migrations/versions/<revision>_enable_rls_public_tables.py`
- `down_revision = '9cb5227a017d'` (confirmed current head, matches live DB)
- `upgrade()`: for each of the 9 tables, `op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")`
- `downgrade()`: for each of the 9 tables, `op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")`
- RLS is not an ORM-modeled concept, so this is raw SQL via `op.execute()`, consistent
  with how Alembic handles any DDL outside SQLAlchemy's table/column model.

Tables, in the order the migration touches them: `benchmark_packs`,
`benchmark_items`, `assessments`, `runs`, `model_responses`, `metric_results`,
`scorecards`, `response_reviews`, `alembic_version`.

## Verification

The existing pytest suite runs against an ephemeral in-memory SQLite DB
(`tests/conftest.py`), which has no concept of RLS (a Postgres-only feature) and
never invokes Alembic. It cannot prove this fix works. Verification instead happens
directly against the real database and the real PostgREST endpoint:

1. **Before applying:** `GET https://yjaftvqpkrtyjtkfdgen.supabase.co/rest/v1/model_responses?limit=1`
   with the anon key in the `apikey`/`Authorization` headers — confirm it returns
   real row data, proving the exposure exists right now.
2. **Apply:** `alembic upgrade head` against the real DB via `DATABASE_URL`.
3. **After applying:** repeat the identical request — confirm it now returns `[]`
   (an empty array, not an HTTP error — that's the expected behavior for RLS
   enabled with no policies: the request succeeds, the row set is just empty).
4. **Regression check:** run the existing pytest suite (108 tests at last count) —
   expected to pass unchanged, since none of it touches RLS or PostgREST.
5. **Live console smoke check:** reload `https://afroeval-console.streamlit.app`,
   log in, confirm scorecards/data still render normally — proving the `postgres`-role
   direct connection is unaffected in practice, not just in theory.

## Rollback

If step 3 or 5 shows anything unexpectedly broke, `alembic downgrade -1` reverts
cleanly to RLS-disabled. That would indicate some access path uses the anon key
that this design's code search didn't find — production behavior is the ground
truth over a static search, so an unexpected break there should trigger
re-investigation rather than a silent retry.
