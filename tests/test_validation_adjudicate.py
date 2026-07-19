"""
Task-construction and pairing logic for the adjudication queue (2026-07-19 review Findings
1 and 2). build_adjudication_tasks is the pure core of scripts/validation_adjudicate.py:
main() only reads packs, calls this, prints, and optionally pushes to Label Studio.
"""
from scripts.validation_adjudicate import build_adjudication_tasks
from validation.hashing import item_content_hash

ITEM = {"id": "ch-am-001", "prompt": "p", "expected_behavior": "e"}
HASH = item_content_hash("p", "e")
STALE_HASH = "stale-hash-that-does-not-match"


def _rating(validator, cultural, justification, factual="yes", h=HASH):
    return {
        "item_id": "ch-am-001",
        "validator_id": validator,
        "cultural_score": cultural,
        "factual_accuracy": factual,
        "item_content_hash": h,
        "justification": justification,
    }


def test_factual_dispute_task_carries_both_scores_and_justifications():
    """
    A factual-accuracy dispute is the flagged() shape validation_writeback produces. The
    adjudicator must see both validators' scores AND their justifications - the whole reason
    the role exists is to decide with context the (blind) validators didn't have.
    """
    flagged = {"ch-am-001": {"needs_adjudication": True,
                              "reason": "factual accuracy disputed: yes vs no"}}
    ratings_by_item = {
        "ch-am-001": [
            _rating("sme-a", 4, "Matches the local remittance rules I know.", factual="yes"),
            _rating("sme-b", 4, "The fee cap cited is out of date.", factual="no"),
        ]
    }

    tasks, warnings = build_adjudication_tasks(flagged, ratings_by_item, {"ch-am-001": ITEM})

    assert warnings == []
    assert len(tasks) == 1
    task = tasks[0]
    assert task["item_id"] == "ch-am-001"
    assert "sme-a" in task["rating_a"] and "cultural 4" in task["rating_a"]
    assert "Matches the local remittance rules I know." in task["rating_a"]
    assert "sme-b" in task["rating_b"] and "factual no" in task["rating_b"]
    assert "The fee cap cited is out of date." in task["rating_b"]


def test_flagged_item_without_exactly_two_fresh_ratings_is_warned_not_dropped_silently():
    """
    Three rows for one item (e.g. a stale pair plus one fresh re-rater) must not silently
    vanish from the queue - the whole point of flagging is that a human needs to see it.
    """
    flagged = {"ch-am-001": {"needs_adjudication": True, "reason": "pair kappa 0.10 below floor 0.7"}}
    ratings_by_item = {
        "ch-am-001": [
            _rating("sme-a", 4, "j1"),
            _rating("sme-b", 4, "j2"),
            _rating("sme-c", 2, "j3"),
        ]
    }

    tasks, warnings = build_adjudication_tasks(flagged, ratings_by_item, {"ch-am-001": ITEM})

    assert tasks == []
    assert len(warnings) == 1
    assert "ch-am-001" in warnings[0]
    assert "3 fresh validation" in warnings[0]


def test_stale_rating_excluded_from_pairing():
    """
    A rating whose item_content_hash no longer matches the live item's content is a rating
    of text nobody currently sees. It must not be paired in, even though it shares the
    item_id - that is exactly the re-validated-after-edit scenario the content hash exists
    to catch.
    """
    flagged = {"ch-am-001": {"needs_adjudication": True, "reason": "cultural scores differ"}}
    ratings_by_item = {
        "ch-am-001": [
            _rating("sme-a", 4, "fresh justification a", h=HASH),
            _rating("sme-b", 2, "fresh justification b", h=HASH),
            _rating("sme-old", 5, "stale justification", h=STALE_HASH),
        ]
    }

    tasks, warnings = build_adjudication_tasks(flagged, ratings_by_item, {"ch-am-001": ITEM})

    assert warnings == []
    assert len(tasks) == 1
    assert "sme-old" not in tasks[0]["rating_a"]
    assert "sme-old" not in tasks[0]["rating_b"]
    assert "stale justification" not in tasks[0]["rating_a"]
    assert "stale justification" not in tasks[0]["rating_b"]
