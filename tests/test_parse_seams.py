# tests/test_parse_seams.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import import_authored_items as iai  # noqa: E402
import validation_import_ratings as vir  # noqa: E402


def test_parse_authored_extracts_text_and_choice_fields():
    result = [
        {"from_name": "prompt", "value": {"text": ["  ናይ ጤና ጥያቄ  "]}},
        {"from_name": "expected_behavior", "value": {"text": ["Answer safely."]}},
        {"from_name": "language", "value": {"choices": ["am"]}},
        {"from_name": "status", "value": {"choices": ["approve"]}},
    ]
    parsed = iai._parse_authored(result)
    assert parsed["prompt"] == "ናይ ጤና ጥያቄ"          # trimmed
    assert parsed["language"] == "am"
    assert parsed["status"] == "approve"


def test_cites_external_source_handles_non_latin_year():
    assert iai._cites_external_source("የጤና ሚኒስቴር መመሪያ በ2021 ዓ.ም") is True   # Amharic + glued year
    assert iai._cites_external_source("WHO guidelines, 2019") is True
    assert iai._cites_external_source("https://moh.gov.et/epi") is True
    assert iai._cites_external_source("SME authored") is False               # self-referential
    assert iai._cites_external_source("") is False


def test_ratings_parse_flattens_instrument():
    annotation = {"result": [
        {"from_name": "factual_accuracy", "value": {"choices": ["yes"]}},
        {"from_name": "cultural_score", "value": {"choices": ["4"]}},
        {"from_name": "verdict", "value": {"choices": ["pass"]}},
        {"from_name": "justification", "value": {"text": ["culturally sound"]}},
    ]}
    parsed = vir._parse(annotation)
    assert parsed["factual_accuracy"] == "yes"
    assert parsed["cultural_score"] == "4"
    assert parsed["justification"] == "culturally sound"
