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
