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


def test_kpi_row_renders_label_value_sub_and_grid_class():
    with patch("console.branding.st.markdown") as m:
        branding.render_kpi_row([
            {"label": "Top model", "value": "claude-haiku", "sm": True, "sub": "89.6 composite", "trend": "up"},
            {"label": "Models compared", "value": "3"},
        ], columns=3)
    html = m.call_args[0][0]
    assert "kpi-row" in html and "Top model" in html and "claude-haiku" in html
    assert "v sm" in html                    # text KPI uses the small variant
    assert "▲ 89.6 composite" in html        # up-trend sub-line with arrow


def test_kpi_row_two_column_variant_sets_k2():
    with patch("console.branding.st.markdown") as m:
        branding.render_kpi_row([{"label": "A", "value": "1"}, {"label": "B", "value": "2"}], columns=2)
    assert "kpi-row k2" in m.call_args[0][0]


def test_callout_default_is_info_and_warn_flag_switches_class():
    with patch("console.branding.st.markdown") as m:
        branding.render_callout("<b>Note.</b> body")
    assert "brand-callout" in m.call_args[0][0] and "warn" not in m.call_args[0][0]
    with patch("console.branding.st.markdown") as m:
        branding.render_callout("<b>Coverage.</b> below floor", kind="warn")
    assert "brand-callout warn" in m.call_args[0][0]


def test_item_detail_renders_fields_metrics_and_escapes():
    with patch("console.branding.st.markdown") as m:
        branding.render_item_detail({
            "id": "ch-am-201", "cohort": "informal_rural", "tags": "child health",
            "prompt": "a <script> b", "expected": "ask danger signs", "response": "go to clinic",
            "foot": "Language: am  |  Domain: community_health",
            "metrics": [("cultural_appropriateness", "cultural_score", 90.0, "pass", "warm framing"),
                        ("language_performance", "fluency", 80.0, "warn", "a touch stiff")],
        })
    html = m.call_args[0][0]
    assert "ch-am-201" in html and "idetail" in html
    assert "cultural_appropriateness" in html and "90.0" in html
    assert "Attention" in html               # warn status maps to the "Attention" label
    assert "&lt;script&gt;" in html          # prompt is HTML-escaped


def test_detail_placeholder_uses_empty_state_class():
    with patch("console.branding.st.markdown") as m:
        branding.render_detail_placeholder("Select a row")
    assert "idetail-empty" in m.call_args[0][0] and "Select a row" in m.call_args[0][0]


def test_inject_brand_css_covers_new_component_surfaces():
    with patch("console.branding.st.markdown") as m:
        branding.inject_brand_css()
    css = m.call_args[0][0]
    assert "kpi-row" in css and "brand-callout" in css and "idetail" in css
    assert "brand-table" in css


def test_data_table_renders_headers_rows_and_alignment_classes():
    with patch("console.branding.st.markdown") as m:
        branding.render_data_table(
            ["Language", "Staged", "Status"],
            [["Amharic (am)", "12", '<span class="sc-badge pass">Complete</span>']],
            right_cols={1}, score_cols={1},
        )
    html = m.call_args[0][0]
    assert "brand-table" in html and "Amharic (am)" in html
    assert '<span class="sc-badge pass">Complete</span>' in html   # badge cell kept as trusted markup
    assert 'class="r score"' in html                                # col 1 is right-aligned + score-styled


def test_data_table_escapes_headers():
    with patch("console.branding.st.markdown") as m:
        branding.render_data_table(["A<b>", "B"], [["1", "2"]])
    assert "A&lt;b&gt;" in m.call_args[0][0]
