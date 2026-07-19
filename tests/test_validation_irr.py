"""
Kappa is a property of a RATER PAIR over a BATCH, never of a single item.
These tests lock that framing as much as the arithmetic.
"""
import pytest

from validation.irr import IRR_FLOOR, MIN_SHARED_BATCH, batch_key, pair_kappa


def test_perfect_agreement_is_one():
    scores = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    assert pair_kappa(scores, scores) == pytest.approx(1.0)


def test_below_minimum_batch_returns_none_not_a_number():
    """9 shared items cannot produce a defensible kappa. None, never an estimate."""
    nine = [1, 2, 3, 4, 5, 1, 2, 3, 4]
    assert len(nine) == MIN_SHARED_BATCH - 1
    assert pair_kappa(nine, nine) is None


def test_exactly_the_minimum_batch_is_allowed():
    ten = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    assert len(ten) == MIN_SHARED_BATCH
    assert pair_kappa(ten, ten) is not None


def test_near_agreement_scores_higher_than_far_disagreement():
    """
    Quadratic weighting is the point: on an ordinal 1-5 scale, 4-vs-5 must cost far less
    than 1-vs-5. Unweighted kappa would treat them identically.
    """
    a = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    near = [1, 2, 3, 4, 4, 1, 2, 3, 4, 4]   # off by one on two items
    far = [5, 2, 3, 4, 1, 5, 2, 3, 4, 1]    # inverted on the same two items
    assert pair_kappa(a, near) > pair_kappa(a, far)


def test_mismatched_lengths_raise_rather_than_truncate():
    """Silent zip truncation would pair each rating with the wrong item."""
    with pytest.raises(ValueError, match="same length"):
        pair_kappa([1] * 10, [1] * 9)


def test_batch_key_is_order_independent():
    """The pair (A,B) and (B,A) are the same pair and must share one batch."""
    assert batch_key("sme-aaa", "sme-bbb") == batch_key("sme-bbb", "sme-aaa")


def test_irr_floor_is_the_agreed_070():
    assert IRR_FLOOR == 0.70
