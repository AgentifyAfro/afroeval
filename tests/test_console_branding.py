"""Tests for console/branding.py — pure presentation helpers, WCAG-AA colours.

No Streamlit runtime needed: the string-returning helper is tested directly and the
st.markdown-calling helpers are exercised with st.markdown patched.
"""

from unittest.mock import patch

from console import branding
from console.theme import BG_SURFACE, ERROR, SUCCESS, TEXT_FAINT, WARNING, contrast_ratio


def test_status_badge_embeds_label_and_theme_colours():
    assert SUCCESS in branding.render_status_badge("Ready", "pass")
    assert ERROR in branding.render_status_badge("Fail", "fail")
    assert WARNING in branding.render_status_badge("Attn", "warning")
    assert "Ready" in branding.render_status_badge("Ready", "pass")


def test_status_badge_unknown_status_falls_back_to_info():
    assert branding.INFO in branding.render_status_badge("x", "bogus")


def test_badge_colours_clear_wcag_aa_on_the_card_surface():
    # The brief's literal #EF4444 / #7C3AED fail AA on #1A1A24; the tested theme values
    # this module sources must clear AA (>= 4.5) so the redesign can't regress contrast.
    for status in ("pass", "warning", "fail"):
        color, _label = branding.STATUS_CONFIG[status]
        assert contrast_ratio(color, BG_SURFACE) >= 4.5, status


def test_caption_is_the_aa_safe_lift_not_the_briefs_failing_grey():
    assert branding.CAPTION == TEXT_FAINT  # #A6ABC4, not the brief's #6B7280 (3.57:1 — fails)
    assert contrast_ratio(branding.CAPTION, BG_SURFACE) >= 4.5


def test_tint_produces_rgba():
    assert branding._tint("#34D399", 0.12).startswith("rgba(")


def test_section_header_renders_eyebrow_title_and_gradient_accent():
    with patch("console.branding.st.markdown") as m:
        branding.render_section_header("COVERAGE", "Language Comparison", "Comparison")
    html = m.call_args[0][0]
    assert "COVERAGE" in html
    assert "Language" in html
    assert "gradient-text" in html  # the accent word is wrapped in the gradient span


def test_section_divider_emits_brand_divider():
    with patch("console.branding.st.markdown") as m:
        branding.render_section_divider()
    assert "brand-divider" in m.call_args[0][0]


def test_inject_brand_css_covers_the_key_surfaces():
    with patch("console.branding.st.markdown") as m:
        branding.inject_brand_css()
    css = m.call_args[0][0]
    assert ".stApp" in css and "#000000" in css  # pure-black canvas
    assert "role-badge" in css                     # admin/viewer tier badge
    assert "stDataFrame" in css                    # table overrides
    assert "sc-hero" in css and "sc-dcard" in css  # scorecard hero + dimension cards


def test_scorecard_header_renders_hero_and_kpis():
    with patch("console.branding.st.markdown") as m:
        branding.render_scorecard_header(89.6, "Deployment-Ready", "standard",
                                         "claude-haiku", "Amharic · Community Health", "2m 37s")
    html = m.call_args[0][0]
    assert "89.6" in html and "sc-hero" in html
    assert "Deployment-Ready" in html
    assert "Runtime" in html and "2m 37s" in html  # runtime is now a KPI card


def test_dimension_cards_render_scores_ci_and_status():
    with patch("console.branding.st.markdown") as m:
        branding.render_dimension_cards([
            {"name": "Cultural", "weight": 0.20, "score": 31.2, "ci": (23.2, 39.3), "status": "fail"},
            {"name": "Bias Fairness", "weight": 0.15, "score": None, "ci": None, "status": "na"},
        ])
    html = m.call_args[0][0]
    assert "31.2" in html and "Below 60" in html
    assert "N/A" in html and "95% CI 23.2" in html and "sc-dcard" in html
