"""WCAG contrast guards for the console palette and the theme-aware radar.

Locks the chosen colours to their targets so a future edit can't silently
reintroduce a low-contrast value.
"""

from console.theme import (
    BG_CANVAS,
    BG_SURFACE,
    ERROR,
    LINK,
    SUCCESS,
    WARNING,
    contrast_ratio,
)
from reporting.radar import RADAR_THEMES

AA = 4.5
AAA = 7.0


def test_contrast_ratio_sanity():
    assert round(contrast_ratio("#FFFFFF", "#000000")) == 21
    assert contrast_ratio("#000000", "#000000") == 1.0


def test_link_meets_aa_on_card_background():
    assert contrast_ratio(LINK, BG_SURFACE) >= AA


def test_semantic_colours_meet_targets_on_card_background():
    assert contrast_ratio(SUCCESS, BG_SURFACE) >= AAA
    assert contrast_ratio(ERROR, BG_SURFACE) >= AA
    assert contrast_ratio(WARNING, BG_SURFACE) >= AA


def test_dark_radar_label_is_aaa_on_dark_console():
    assert contrast_ratio(RADAR_THEMES["dark"]["label"], BG_CANVAS) >= AAA


def test_light_radar_label_is_aaa_on_offwhite_report():
    # The PDF renders on an off-white page; the light-theme label must read there.
    assert contrast_ratio(RADAR_THEMES["light"]["label"], "#FAF9F5") >= AAA
