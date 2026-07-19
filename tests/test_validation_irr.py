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
    Quadratic weighting is the point: on an ordinal 1-5 scale, a single item off by one
    must cost far less than the same single item off by four. The disagreement COUNT is
    held constant (exactly one mismatched item in both fixtures) so only distance varies -
    otherwise unweighted kappa would rank them the same way and this test would pass for
    the wrong reason.
    """
    a = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    near = [1, 2, 3, 4, 4, 1, 2, 3, 4, 5]  # one item off by one (5 -> 4)
    far = [1, 2, 3, 4, 1, 1, 2, 3, 4, 5]  # the same item off by four (5 -> 1)
    assert pair_kappa(a, near) > pair_kappa(a, far)


def test_labels_are_pinned_to_the_cultural_scale_not_inferred_from_the_batch():
    """
    cohen_kappa_score builds its quadratic weight matrix from the labels it is given. If we
    don't pass labels=[1,2,3,4,5] explicitly, sklearn infers them from whatever values
    happen to appear in the batch. This batch only uses {1,2,5} - no rater ever used 3 or 4
    - so an unpinned call treats 2-vs-5 as an adjacent-category disagreement (distance 1 in
    the observed-label space) instead of its true distance of 3 on the real 1-5 scale. That
    inflates kappa past the 0.70 floor and would wrongly let a Tier 1 item through. This
    must fail if `labels=CULTURAL_SCALE` is removed from pair_kappa.
    """
    a = [2, 1, 5, 5, 5, 1, 1, 2, 1, 5]
    b = [1, 2, 2, 5, 2, 1, 1, 2, 1, 5]
    kappa = pair_kappa(a, b)
    assert kappa < IRR_FLOOR


def test_mismatched_lengths_raise_rather_than_truncate():
    """Silent zip truncation would pair each rating with the wrong item."""
    with pytest.raises(ValueError, match="same length"):
        pair_kappa([1] * 10, [1] * 9)


def test_batch_key_is_order_independent():
    """The pair (A,B) and (B,A) are the same pair and must share one batch."""
    assert batch_key("sme-aaa", "sme-bbb") == batch_key("sme-bbb", "sme-aaa")


def test_irr_floor_is_the_agreed_070():
    assert IRR_FLOOR == 0.70
