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
