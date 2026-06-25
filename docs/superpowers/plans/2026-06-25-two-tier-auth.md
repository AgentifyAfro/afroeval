# Two-Tier Console Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single shared `operator_password` console gate with real per-user Supabase Auth login, split into two access tiers (Category 1: reporting views, Category 2: reporting + operator views), while keeping `operator_password` as a parallel Category 2 fallback.

**Architecture:** A new `auth/client.py` wraps `supabase-py`'s `sign_in_with_password`, returning a frozen `AuthUser(id, email, role)` where `role` comes from Supabase's `app_metadata` (writable only via the service-role key, never exposed to the app). A new pure function `console/access.py::resolve_views()` takes `(auth_user, operator_unlocked)` and returns the visible view list — no Streamlit or network dependency, fully unit-testable. `console/app.py` is wired to call both: a login form replaces the old single password box, and the admin-override password field moves into a collapsed expander.

**Tech Stack:** Python 3.12, Streamlit, `supabase` (official Python client), `pydantic-settings`, `pytest`.

## Global Constraints

- Per the approved spec (`docs/superpowers/specs/2026-06-25-two-tier-auth-design.md`): no self-service signup, no in-app password reset, no persistent session across browser refresh (per-session only), no admin CLI tooling — all account provisioning is manual via the Supabase dashboard.
- `operator_password` is **not** retired — it remains a parallel Category 2 fallback that also grants Category 1 (full admin escape hatch, confirmed in brainstorm).
- Never commit secrets — `SUPABASE_URL`/`SUPABASE_ANON_KEY` go in `.env` only (already gitignored). Only the anon key is ever used by the app; the service-role key is never read by any code in this plan.
- Do not commit to git without Dan's explicit approval — stage changes and stop for review at the end of each task.
- RLS on `public.*` tables is out of scope for this plan (tracked separately per the spec's Non-goals).

---

### Task 1: Auth client (`auth/client.py`)

**Files:**
- Create: `auth/__init__.py`
- Create: `auth/client.py`
- Test: `tests/test_auth_client.py`
- Modify: `api/settings.py` (add `supabase_url`, `supabase_anon_key` fields)
- Modify: `requirements.txt` (add `supabase` dependency, pinned to the version actually installed)
- Modify: `pyproject.toml` (add `supabase` to `dependencies`, add `"auth"` to `[tool.hatch.build.targets.wheel].packages`)

**Interfaces:**
- Produces: `auth.client.AuthUser` — frozen dataclass with fields `id: str`, `email: str`, `role: str | None`.
- Produces: `auth.client.SupabaseAuthClient` — `__init__(self, url: str | None = None, anon_key: str | None = None)`, `sign_in(self, email: str, password: str) -> AuthUser`, `sign_out(self) -> None`.
- Produces: `auth.client.InvalidCredentialsError(Exception)`, `auth.client.AuthServiceUnavailableError(Exception)` — raised by `sign_in` on bad credentials vs. unreachable service, respectively.
- Consumes: `api.settings.get_settings()` (existing, `api/settings.py:51`) for `supabase_url`/`supabase_anon_key`.

- [ ] **Step 1: Add settings fields**

In `api/settings.py`, add after the existing `# Operator console` block (currently ending at line 43 with `operator_password: str = ""`):

```python
    # Operator console
    operator_password: str = ""

    # Supabase Auth (console login)
    supabase_url: str = ""
    supabase_anon_key: str = ""
```

- [ ] **Step 2: Install the `supabase` package and pin the resolved version**

```powershell
.\.venv\Scripts\pip.exe install supabase
.\.venv\Scripts\pip.exe show supabase
```

Note the `Version:` line from the `pip show` output — use that exact version in the next step (do not guess a version number).

- [ ] **Step 3: Pin the dependency in `requirements.txt` and `pyproject.toml`**

In `requirements.txt`, add a new line after `deepeval>=4.0.0` (currently the last line):

```
supabase==<version from Step 2>
```

In `pyproject.toml`, add to the `dependencies` list, after the `# Operator console` entry (currently `"streamlit>=1.36.0",`):

```toml
    # Operator console
    "streamlit>=1.36.0",
    "supabase>=2.0.0",
```

And add `"auth"` to the wheel packages list (currently lines 76-88), alphabetically after `"api"`:

```toml
[tool.hatch.build.targets.wheel]
packages = [
    "api",
    "auth",
    "ingestion",
    "orchestration",
    "evaluators",
    "ail",
    "scoring",
    "benchmarks",
    "reporting",
    "console",
    "hitl",
    "db",
]
```

- [ ] **Step 4: Create the `auth` package**

Create `auth/__init__.py`:

```python
"""
Auth module — Supabase Auth integration for console login.

Account creation and role assignment happen manually in the Supabase
dashboard (invite-only, admin-provisioned). This module only handles
sign-in/sign-out for an already-existing account.
"""
```

- [ ] **Step 5: Write the failing tests**

Create `tests/test_auth_client.py`:

```python
"""
Tests for auth/client.py — mocks the supabase client entirely, no network calls.
"""

from unittest.mock import MagicMock

import pytest
from gotrue.errors import AuthApiError

from auth.client import (
    AuthServiceUnavailableError,
    AuthUser,
    InvalidCredentialsError,
    SupabaseAuthClient,
)


def _client_with_fake_supabase(monkeypatch, fake_supabase) -> SupabaseAuthClient:
    monkeypatch.setattr("auth.client.create_client", lambda url, key: fake_supabase)
    return SupabaseAuthClient(url="https://example.supabase.co", anon_key="anon-key")


def test_sign_in_returns_auth_user_with_role(monkeypatch):
    fake_user = MagicMock(id="u1", email="admin@agentifyafro.ai", app_metadata={"role": "admin"})
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.return_value = MagicMock(user=fake_user)

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    result = client.sign_in("admin@agentifyafro.ai", "correct-password")

    assert result == AuthUser(id="u1", email="admin@agentifyafro.ai", role="admin")


def test_sign_in_defaults_role_to_none_when_no_app_metadata(monkeypatch):
    fake_user = MagicMock(id="u2", email="viewer@agentifyafro.ai", app_metadata={})
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.return_value = MagicMock(user=fake_user)

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    result = client.sign_in("viewer@agentifyafro.ai", "correct-password")

    assert result.role is None


def test_sign_in_raises_invalid_credentials_on_auth_api_error(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.side_effect = AuthApiError("Invalid login credentials", 400, "invalid_credentials")

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    with pytest.raises(InvalidCredentialsError):
        client.sign_in("viewer@agentifyafro.ai", "wrong-password")


def test_sign_in_raises_service_unavailable_on_other_errors(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.side_effect = ConnectionError("network down")

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    with pytest.raises(AuthServiceUnavailableError):
        client.sign_in("viewer@agentifyafro.ai", "any-password")


def test_missing_url_raises_value_error():
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        SupabaseAuthClient(url="", anon_key="anon-key")


def test_missing_anon_key_raises_value_error():
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        SupabaseAuthClient(url="https://example.supabase.co", anon_key="")
```

- [ ] **Step 6: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'auth'` (or `ImportError`) — the module doesn't exist yet.

- [ ] **Step 7: Write the implementation**

Create `auth/client.py`:

```python
"""
Thin wrapper around supabase-py for console login.

Only sign-in/sign-out are needed here — account creation and role
assignment happen manually in the Supabase dashboard (invite-only,
admin-provisioned). See docs/superpowers/specs/2026-06-25-two-tier-auth-design.md.
"""

from dataclasses import dataclass

from gotrue.errors import AuthApiError
from supabase import Client, create_client

from api.settings import get_settings


class InvalidCredentialsError(Exception):
    """Raised when email/password don't match a Supabase Auth account."""


class AuthServiceUnavailableError(Exception):
    """Raised when Supabase Auth itself can't be reached."""


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    role: str | None


class SupabaseAuthClient:
    def __init__(self, url: str | None = None, anon_key: str | None = None):
        settings = get_settings()
        self.url = url if url is not None else settings.supabase_url
        self.anon_key = anon_key if anon_key is not None else settings.supabase_anon_key
        if not self.url or not self.anon_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        self._client: Client = create_client(self.url, self.anon_key)

    def sign_in(self, email: str, password: str) -> AuthUser:
        try:
            resp = self._client.auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError as exc:
            raise InvalidCredentialsError(str(exc)) from exc
        except Exception as exc:
            raise AuthServiceUnavailableError(str(exc)) from exc

        user = resp.user
        role = (user.app_metadata or {}).get("role")
        return AuthUser(id=user.id, email=user.email, role=role)

    def sign_out(self) -> None:
        self._client.auth.sign_out()
```

- [ ] **Step 8: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_client.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 9: Stage and stop for review**

```powershell
git add auth/__init__.py auth/client.py tests/test_auth_client.py api/settings.py requirements.txt pyproject.toml
git status
```

Do not commit — show Dan the staged diff and wait for explicit approval before any commit.

---

### Task 2: View-gating logic (`console/access.py`)

**Files:**
- Create: `console/access.py`
- Test: `tests/test_console_access.py`

**Interfaces:**
- Consumes: `auth.client.AuthUser` (from Task 1) — uses only the `.role` attribute.
- Produces: `console.access.CATEGORY_1_VIEWS: list[str]`, `console.access.CATEGORY_2_VIEWS: list[str]`, `console.access.resolve_views(auth_user: AuthUser | None, operator_unlocked: bool) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_console_access.py`:

```python
"""
Tests for console/access.py — pure function, no Streamlit or Supabase dependency.
"""

from auth.client import AuthUser
from console.access import CATEGORY_1_VIEWS, CATEGORY_2_VIEWS, resolve_views


def test_no_auth_no_override_returns_empty():
    assert resolve_views(auth_user=None, operator_unlocked=False) == []


def test_logged_in_no_role_returns_category1_only():
    user = AuthUser(id="u1", email="viewer@agentifyafro.ai", role=None)
    assert resolve_views(auth_user=user, operator_unlocked=False) == CATEGORY_1_VIEWS


def test_logged_in_admin_role_returns_both_categories():
    user = AuthUser(id="u2", email="admin@agentifyafro.ai", role="admin")
    assert resolve_views(auth_user=user, operator_unlocked=False) == CATEGORY_1_VIEWS + CATEGORY_2_VIEWS


def test_operator_override_without_login_returns_both_categories():
    assert resolve_views(auth_user=None, operator_unlocked=True) == CATEGORY_1_VIEWS + CATEGORY_2_VIEWS


def test_operator_override_combined_with_non_admin_login_returns_both_categories():
    user = AuthUser(id="u3", email="viewer@agentifyafro.ai", role=None)
    assert resolve_views(auth_user=user, operator_unlocked=True) == CATEGORY_1_VIEWS + CATEGORY_2_VIEWS
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_console_access.py -v
```

Expected: `ModuleNotFoundError: No module named 'console.access'`.

- [ ] **Step 3: Write the implementation**

Create `console/access.py`:

```python
"""
Pure view-gating logic for the operator console's two access tiers.

Kept separate from app.py so it's testable without Streamlit or Supabase.
See docs/superpowers/specs/2026-06-25-two-tier-auth-design.md.
"""

from auth.client import AuthUser

CATEGORY_1_VIEWS = ["Run Scorecard", "Provider Comparison", "Language Comparison", "SME Calibration"]
CATEGORY_2_VIEWS = ["Run Evaluation", "Pack Management", "HITL Management"]


def resolve_views(auth_user: AuthUser | None, operator_unlocked: bool) -> list[str]:
    """Returns the ordered list of console view names visible to this session."""
    has_cat1 = auth_user is not None or operator_unlocked
    has_cat2 = (auth_user is not None and auth_user.role == "admin") or operator_unlocked

    views: list[str] = []
    if has_cat1:
        views.extend(CATEGORY_1_VIEWS)
    if has_cat2:
        views.extend(CATEGORY_2_VIEWS)
    return views
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_console_access.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Stage and stop for review**

```powershell
git add console/access.py tests/test_console_access.py
git status
```

Do not commit — wait for Dan's approval.

---

### Task 3: Wire login + gating into `console/app.py`

**Files:**
- Modify: `console/app.py:1-29` (imports)
- Modify: `console/app.py:1619-1692` (the `main()` function — current line numbers as of this plan; re-read the file before editing in case Tasks 1-2 shifted nothing here, since they only touched other files)

**Interfaces:**
- Consumes: `auth.client.SupabaseAuthClient`, `auth.client.AuthUser`, `auth.client.InvalidCredentialsError`, `auth.client.AuthServiceUnavailableError` (Task 1); `console.access.resolve_views` (Task 2).
- Produces: nothing new for other tasks — this is the final integration point.

- [ ] **Step 1: Add imports**

In `console/app.py`, after the existing import block (currently lines 26-29):

```python
from benchmarks.ids import stable_item_uuid
from benchmarks.loader import PACKS_DIR
from db.models import Assessment, BenchmarkItem, BenchmarkPack, MetricResult, ModelResponse, ResponseReview, Run, RunStatus, Scorecard
from db.session import get_engine
from sqlmodel import Session, col, select
```

add:

```python
from auth.client import AuthServiceUnavailableError, AuthUser, InvalidCredentialsError, SupabaseAuthClient
from console.access import resolve_views
```

- [ ] **Step 2: Replace the `main()` function body**

Re-read `console/app.py` to confirm the current line range for `main()` (it starts at `def main() -> None:` — verify it still matches the range below before replacing; Tasks 1-2 did not touch this file, so it should be unchanged from this plan's exploration), then replace the full function with:

```python
def main() -> None:
    with st.sidebar:
        st.markdown(
            '<div style="height:3px;background:linear-gradient(90deg,#7C3AED 0%,#4169E1 50%,#00CFFF 100%);'
            'margin:-1rem -1rem 0.75rem -1rem;"></div>',
            unsafe_allow_html=True,
        )
        st.header("View")

        auth_user: AuthUser | None = st.session_state.get("auth_user")
        unlocked = st.session_state.get("operator_unlocked", False)
        all_views = resolve_views(auth_user, unlocked)

        if all_views:
            # nav_view is managed as plain session state (not a widget key) so it can
            # be set from button callbacks without triggering StreamlitAPIException.
            if st.session_state.get("nav_view") not in all_views:
                st.session_state["nav_view"] = all_views[0]
            _nav_idx = all_views.index(st.session_state["nav_view"])
            selected = st.radio("View", all_views, label_visibility="collapsed", index=_nav_idx)
            st.session_state["nav_view"] = selected
            view = selected
        else:
            st.caption("Log in to view the console.")
            view = None

        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()

        if auth_user is not None:
            role_label = auth_user.role or "viewer"
            st.success(f"🔓 Logged in as {auth_user.email} ({role_label})")
            if st.button("Log out", key="auth_logout", use_container_width=True):
                st.session_state.pop("auth_user", None)
                st.rerun()
        else:
            st.caption("🔐 LOG IN")
            login_email = st.text_input(
                "login_email", placeholder="Email",
                label_visibility="collapsed", key="login_email_input",
            )
            login_pwd = st.text_input(
                "login_pwd", type="password", placeholder="Password",
                label_visibility="collapsed", key="login_pwd_input",
            )
            if st.button("Log in", key="login_submit", use_container_width=True):
                if login_email and login_pwd:
                    try:
                        user = SupabaseAuthClient().sign_in(login_email, login_pwd)
                        st.session_state["auth_user"] = user
                        st.rerun()
                    except InvalidCredentialsError:
                        st.error("Invalid email or password")
                    except AuthServiceUnavailableError:
                        st.error("Login service unavailable, try again")
                else:
                    st.error("Enter both email and password")

        with st.expander("Admin override"):
            if not unlocked:
                pwd = st.text_input(
                    "operator_pwd", type="password",
                    placeholder="Enter operator password",
                    label_visibility="collapsed",
                    key="op_pwd_input",
                )
                if pwd:
                    from api.settings import get_settings
                    correct = get_settings().operator_password
                    if correct and pwd == correct:
                        st.session_state["operator_unlocked"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect password")
            else:
                st.success("🔓 Operator override active")
                if st.button("🔒 Lock override", key="op_lock", use_container_width=True):
                    st.session_state["operator_unlocked"] = False
                    st.session_state.pop("op_active_run_id", None)
                    st.rerun()

    if view is None:
        st.title("AfroEval Console")
        st.info("🔐 This console is restricted. Log in, or use the admin override, in the sidebar to continue.")
    elif view == "Provider Comparison":
        render_provider_comparison()
    elif view == "Language Comparison":
        render_language_breakdown()
    elif view == "SME Calibration":
        render_calibration_view()
    elif view == "Run Evaluation":
        render_run_evaluation()
    elif view == "Pack Management":
        render_pack_management()
    elif view == "HITL Management":
        render_hitl_management()
    else:
        render_run_scorecard()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the file still compiles**

```powershell
.\.venv\Scripts\python.exe -m py_compile console/app.py
```

Expected: no output (success).

- [ ] **Step 4: Run the full test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all tests PASS (including the new `test_auth_client.py` and `test_console_access.py` from Tasks 1-2).

- [ ] **Step 5: Manual verification (Streamlit has no automated UI test in this codebase — do not introduce new UI test infra for this alone)**

Before this step, Dan must create at least one Category 2 test account in the Supabase dashboard (`app_metadata: {"role": "admin"}`) and one Category 1 test account (no `role` set), per the spec's Migration notes — otherwise there is no way to log in as anything but the operator-password fallback.

```powershell
.\.venv\Scripts\streamlit.exe run console/app.py
```

Check, in order:
1. On load, no views are visible and the main area shows "This console is restricted."
2. Log in with the Category 1 test account → only Run Scorecard, Provider Comparison, Language Comparison, SME Calibration appear in the sidebar radio.
3. Log out → back to the restricted screen.
4. Log in with the Category 2 (`role: admin`) test account → all 7 views appear.
5. Log out, then enter the correct `operator_password` in the "Admin override" expander → all 7 views appear without any Supabase login.
6. Enter a wrong password (either login form or operator override) → generic error shown, no information leaked about which field was wrong.

- [ ] **Step 6: Stage and stop for review**

```powershell
git add console/app.py
git status
```

Do not commit — present the full diff across all three tasks to Dan and wait for his explicit approval before committing anything.

---

## Self-Review Notes

- **Spec coverage:** Architecture (Task 1: `auth/client.py`, settings, dependency), View gating (Task 2: `console/access.py` matches the exact logic and four test cases enumerated in the spec's Testing section, plus a fifth combining override + non-admin login), Data flow + Error handling + sidebar UI (Task 3) — all spec sections have a corresponding task.
- **Type consistency:** `AuthUser` defined once in Task 1 (`id`, `email`, `role`), consumed identically in Task 2's `resolve_views()` and Task 3's `st.session_state["auth_user"]` — no renamed fields across tasks.
- **No placeholders:** every step has complete, runnable code; the only "TBD"-shaped item — the exact `supabase` version — is intentionally resolved at install time via `pip show`, not guessed, since fabricating a version number could reference a non-existent release.
