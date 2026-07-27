"""Provenance citation detection must work for non-Latin (Amharic) scripts.

`_cites_external_source` gates Tier-2 eligibility. Its year pattern used `\b`
word boundaries, which do NOT fire between an Amharic letter and a digit (both
are \\w), so a year glued to Amharic text (e.g. "በ2021") was missed — wrongly
marking well-cited Amharic items as not citing a source.
"""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "import_authored_items",
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "import_authored_items.py",
)
_iai = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_iai)
cites = _iai._cites_external_source


def test_amharic_provenance_with_glued_year_is_recognised():
    # "በ2021" — year glued to an Amharic prefix; the old \b year pattern missed it.
    prov = "ይህ ማጣቀሻ የተዘጋጀው በኢትዮጵያ ጤና ሚኒስቴር በ2021 የታተመ ነው"
    assert cites(prov) is True


def test_amharic_year_glued_on_both_sides_is_recognised():
    prov = "ሚኒስቴር2021የታተመ"          # year with Amharic on both sides, no spaces
    assert cites(prov) is True


def test_latin_citation_still_recognised():
    assert cites("WHO Guidelines (2010), 3rd ed.") is True
    assert cites("see https://ephi.gov.et/report") is True


def test_self_referential_still_rejected_even_with_year():
    assert cites("SME authored, 2021") is False


def test_no_checkable_source_rejected():
    assert cites("Ministry of Health website") is False
    assert cites("") is False
    assert cites("   ") is False
