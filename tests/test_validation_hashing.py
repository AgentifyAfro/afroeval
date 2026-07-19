"""The content hash is what makes a stale validation detectable."""
from validation.hashing import item_content_hash


def test_hash_is_stable_for_identical_content():
    a = item_content_hash("What is the fee?", "Names the operator tariff page.")
    b = item_content_hash("What is the fee?", "Names the operator tariff page.")
    assert a == b
    assert len(a) == 64


def test_hash_changes_when_the_prompt_changes():
    before = item_content_hash("What is the fee?", "Names the tariff page.")
    after = item_content_hash("What is the charge?", "Names the tariff page.")
    assert before != after


def test_hash_changes_when_expected_behavior_changes():
    before = item_content_hash("What is the fee?", "Names the tariff page.")
    after = item_content_hash("What is the fee?", "States the exact amount.")
    assert before != after


def test_field_boundary_cannot_be_forged():
    """
    Concatenating without a separator would make ("ab","c") and ("a","bc") hash alike,
    letting a content edit that shifts text across the field boundary go undetected.
    """
    assert item_content_hash("ab", "c") != item_content_hash("a", "bc")
