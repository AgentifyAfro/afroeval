# Two-Tier Console Access Design

**Date:** 2026-06-25
**Status:** Approved, pending implementation plan

## Problem

The AfroEval console (`console/app.py`) currently gates access with a single shared
`operator_password`. Reporting views (Run Scorecard, Provider Comparison, Language
Comparison, SME Calibration) were public to anyone with the link — including SME
emails surfaced in the SME Calibration table. A prior fix (2026-06-25, uncommitted)
gated all views behind the single operator password as a stopgap.

This design replaces that stopgap with real per-user accounts and two access tiers:

- **Category 1 ("Original access"):** Run Scorecard, Provider Comparison, Language
  Comparison, SME Calibration.
- **Category 2 ("Super access"):** Everything in Category 1, plus Run Evaluation,
  Pack Management, HITL Management.

## Goals

- Real per-user login via Supabase Auth (already provisioned, `auth.users` is empty
  and unused).
- Category 1 requires any authenticated account. Category 2 requires an account
  flagged as admin, or the existing operator-password fallback.
- No self-service signup for either tier — Dan provisions all accounts manually via
  the Supabase dashboard (invite-only, confirmed in brainstorm).
- Keep `operator_password` as a parallel Category 2 fallback (not retired) — an
  admin escape hatch if Supabase Auth has an outage, or before any admin account
  exists.

## Non-goals (explicitly cut, YAGNI)

- No self-service signup or open registration.
- No password reset flow in-app — handled via the Supabase dashboard if ever needed.
- No persistent session across browser refresh/new tab — login lasts for the
  Streamlit session only, matching the current operator-password UX. No cookie
  library needed.
- No admin CLI tooling for provisioning — manual Supabase dashboard work only.
- No changes to RLS on `public.*` tables — RLS is currently disabled on
  `benchmark_packs`, `benchmark_items`, `assessments`, `runs`, `model_responses`,
  `metric_results`, `scorecards`, `response_reviews`, `alembic_version`. This is a
  pre-existing, parallel security gap (the app connects via `DATABASE_URL`, not the
  anon-key REST API, so it isn't exploitable through the console itself — but the
  anon key could still query these tables directly via PostgREST). Tracked
  separately; out of scope for this design.

## Architecture

- **Identity provider:** Supabase Auth. New thin client module `auth/client.py`,
  mirroring the existing `hitl/client.py` pattern — a small wrapper class, no extra
  abstraction.
  - `sign_in(email, password) -> AuthUser | None`
  - `sign_out()`
  - `AuthUser` is a simple frozen dataclass: `id`, `email`, `role`.
- **Role storage:** Supabase `app_metadata.role` on the user record. Only the
  service-role key can write `app_metadata`, and the app never holds that key — so
  a logged-in user can never self-promote. No role set = Category 1. `role == "admin"`
  = Category 2.
- **New dependency:** `supabase` (official Python client) — required for
  `sign_in_with_password`. Approved by Dan before install.
- **New settings** (`api/settings.py`, alongside existing `operator_password`):
  - `supabase_url`
  - `supabase_anon_key`
  - Both loaded from `.env`. Only the anon key is ever used by the app — never the
    service-role key.
- **Sidebar:** the existing lock screen gets a real login form (email + password)
  replacing the single password box. A collapsed "Admin override" expander retains
  the current `operator_password` field as the Category 2 fallback.

## View gating

Replaces today's single `unlocked` boolean:

```python
category1 = ["Run Scorecard", "Provider Comparison", "Language Comparison", "SME Calibration"]
category2 = ["Run Evaluation", "Pack Management", "HITL Management"]

has_cat1 = auth_user is not None or operator_unlocked
has_cat2 = (auth_user is not None and auth_user.role == "admin") or operator_unlocked

all_views = (category1 if has_cat1 else []) + (category2 if has_cat2 else [])
```

The operator-password override grants Category 1 + Category 2 — a full admin
escape hatch, not a narrower "Category 2 only" carve-out (confirmed in brainstorm:
an admin override that can't see basic reporting views would be unusually
restrictive for no benefit).

## Data flow

1. User opens console → no `auth_user` in session, `operator_unlocked` false →
   `all_views` is empty → lock screen renders (same pattern as the existing
   stopgap fix, now backed by a real login form).
2. User submits email + password → `auth_client.sign_in()` calls
   `sign_in_with_password()`.
3. On success: store `{"id": ..., "email": ..., "role": app_metadata.get("role")}`
   in `st.session_state["auth_user"]` → rerun → sidebar/view-gating recomputes.
4. Logout button clears `st.session_state["auth_user"]` (and `operator_unlocked` if
   set) → rerun → back to lock screen.
5. Per-session only: a hard refresh or new tab loses `st.session_state`, requiring
   login again. This is intentional (Dan's choice — matches current
   operator-password behavior, avoids a cookie dependency).

## Error handling

- **Wrong email/password:** caught, shown as a single generic
  `st.error("Invalid email or password")`. Deliberately not distinguishing
  "no such user" from "wrong password" to avoid email enumeration.
- **Supabase Auth unreachable:** caught broadly, shown as
  "Login service unavailable, try again." Because the operator-password fallback
  doesn't depend on Supabase Auth, Category 2 access isn't blocked by a Supabase
  outage.
- **Missing config:** if `supabase_url`/`supabase_anon_key` aren't set, fail fast at
  settings load — same pattern `LabelStudioClient` uses today for its required env
  var.

## Testing

- **Unit test the gating logic in isolation.** Extract the `has_cat1`/`has_cat2`/
  `all_views` computation into a pure function, e.g.
  `resolve_views(auth_user: AuthUser | None, operator_unlocked: bool) -> list[str]`,
  with no Streamlit or Supabase dependency. Cases to cover:
  - No auth, no override → `[]`
  - Logged in, no role → category1 only
  - Logged in, `role == "admin"` → category1 + category2
  - Not logged in, operator override → category1 + category2
- **Manual verification before merge:** create one Category 1 test account and one
  Category 2 (`role: admin`) test account directly in the Supabase dashboard, then
  confirm:
  - Each account sees exactly the expected view list.
  - Wrong password shows the generic error.
  - Logout clears state and returns to the lock screen.
  - The operator-password override still grants full access without any Supabase
    account.

## Migration notes

- `operator_password` is **not** retired — it remains a parallel fallback per Dan's
  explicit choice.
- Before merging, Dan needs to create at least one Category 2 (`role: admin`)
  Supabase account for himself so he isn't locked out of admin views pending the
  operator-password fallback.
- The RLS gap noted in Non-goals is tracked as a separate follow-up, not bundled
  into this change.
