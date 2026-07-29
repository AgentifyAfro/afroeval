"""
Pure view-gating logic for the operator console's two access tiers.

Kept separate from app.py so it's testable without Streamlit or Supabase.
See docs/superpowers/specs/2026-06-25-two-tier-auth-design.md.
"""

from auth.client import AuthUser

# Access tiers govern VISIBILITY.
CATEGORY_1_VIEWS = ["Run Scorecard", "Provider Comparison", "Language Comparison", "SME Calibration"]
CATEGORY_2_VIEWS = ["Run Evaluation", "Pack Management", "HITL Management"]

# Sidebar DISPLAY order, independent of tier. Run Evaluation leads so the menu flows
# Run Evaluation → Run Scorecard → Provider Comparison → …; the remaining Category-2 admin
# views (Pack / HITL Management) trail the Category-1 read views. Tier membership above still
# decides which of these a given session actually sees.
VIEW_ORDER = [
    "Run Evaluation",
    "Run Scorecard",
    "Provider Comparison",
    "Language Comparison",
    "SME Calibration",
    "Pack Management",
    "HITL Management",
]


def resolve_views(auth_user: AuthUser | None, operator_unlocked: bool) -> list[str]:
    """Returns the console view names visible to this session, in sidebar display order."""
    has_cat1 = auth_user is not None or operator_unlocked
    has_cat2 = (auth_user is not None and auth_user.role == "admin") or operator_unlocked

    visible: set[str] = set()
    if has_cat1:
        visible.update(CATEGORY_1_VIEWS)
    if has_cat2:
        visible.update(CATEGORY_2_VIEWS)
    return [v for v in VIEW_ORDER if v in visible]


def can_archive_runs(auth_user: AuthUser | None, operator_unlocked: bool) -> bool:
    """
    Archiving/unarchiving a run is a Category 2 (admin/operator) action — it
    curates what every viewer sees, so only admins or the operator override may
    do it. Category 1 viewers see the curated list but cannot change it.
    """
    return (auth_user is not None and auth_user.role == "admin") or operator_unlocked
