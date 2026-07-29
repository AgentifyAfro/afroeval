"""
Tests for console/access.py — pure function, no Streamlit or Supabase dependency.
"""

from auth.client import AuthUser
from console.access import CATEGORY_1_VIEWS, VIEW_ORDER, can_archive_runs, resolve_views


def test_no_auth_no_override_returns_empty():
    assert resolve_views(auth_user=None, operator_unlocked=False) == []


def test_logged_in_no_role_returns_category1_only():
    user = AuthUser(id="u1", email="viewer@agentifyafro.ai", role=None)
    # Read-only viewer sees the Category-1 views in display order (Run Evaluation is
    # Category-2, so it's absent and the menu leads with Run Scorecard).
    assert resolve_views(auth_user=user, operator_unlocked=False) == CATEGORY_1_VIEWS


def test_logged_in_admin_role_returns_all_views_in_display_order():
    user = AuthUser(id="u2", email="admin@agentifyafro.ai", role="admin")
    assert resolve_views(auth_user=user, operator_unlocked=False) == VIEW_ORDER


def test_operator_override_without_login_returns_all_views_in_display_order():
    assert resolve_views(auth_user=None, operator_unlocked=True) == VIEW_ORDER


def test_operator_override_combined_with_non_admin_login_returns_all_views_in_display_order():
    user = AuthUser(id="u3", email="viewer@agentifyafro.ai", role=None)
    assert resolve_views(auth_user=user, operator_unlocked=True) == VIEW_ORDER


def test_run_evaluation_leads_the_menu_for_operators():
    admin = AuthUser(id="u2", email="admin@agentifyafro.ai", role="admin")
    assert resolve_views(auth_user=admin, operator_unlocked=False)[0] == "Run Evaluation"


# ── can_archive_runs: archiving is a Category 2 (admin/operator) action ──────

def test_archive_denied_for_anonymous():
    assert can_archive_runs(auth_user=None, operator_unlocked=False) is False


def test_archive_denied_for_non_admin_viewer():
    user = AuthUser(id="u1", email="viewer@agentifyafro.ai", role=None)
    assert can_archive_runs(auth_user=user, operator_unlocked=False) is False


def test_archive_allowed_for_admin():
    user = AuthUser(id="u2", email="admin@agentifyafro.ai", role="admin")
    assert can_archive_runs(auth_user=user, operator_unlocked=False) is True


def test_archive_allowed_for_operator_override():
    assert can_archive_runs(auth_user=None, operator_unlocked=True) is True
