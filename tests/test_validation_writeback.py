"""The rules that decide whether an item is Tier 1."""
import json

from scripts.validation_writeback import apply_results, compute_item_results, load_packs
from validation.hashing import item_content_hash

ITEM = {"id": "ch-am-001", "prompt": "p", "expected_behavior": "e"}
HASH = item_content_hash("p", "e")


def _v(validator, cultural, factual="yes", h=HASH, item_id="ch-am-001"):
    return {"item_id": item_id, "validator_id": validator, "cultural_score": cultural,
            "factual_accuracy": factual, "item_content_hash": h}


def _batch(pair, n, cultural_a=4, cultural_b=4, factual_b="yes"):
    """n items rated by the same pair, so the batch clears MIN_SHARED_BATCH."""
    out = []
    for i in range(n):
        iid = f"itm-{i}"
        out.append(_v(pair[0], cultural_a, item_id=iid,
                      h=item_content_hash(f"p{i}", f"e{i}")))
        out.append(_v(pair[1], cultural_b, factual=factual_b, item_id=iid,
                      h=item_content_hash(f"p{i}", f"e{i}")))
    return out


def _items(n):
    return [{"id": f"itm-{i}", "prompt": f"p{i}", "expected_behavior": f"e{i}"}
            for i in range(n)]


def test_two_validators_over_a_full_batch_yields_an_irr_score():
    res = compute_item_results(_batch(("sme-a", "sme-b"), 10), _items(10))
    assert res["itm-0"]["validation_count"] == 2
    assert res["itm-0"]["irr_score"] is not None


def test_short_batch_leaves_irr_null():
    """9 shared items: validated by two people, but no defensible reliability number."""
    res = compute_item_results(_batch(("sme-a", "sme-b"), 9), _items(9))
    assert res["itm-0"]["validation_count"] == 2
    assert res["itm-0"]["irr_score"] is None


def test_stale_validation_does_not_count():
    """A rating whose content hash no longer matches the item is attached to text nobody rated."""
    vals = [_v("sme-a", 4), _v("sme-b", 4, h="stale-hash-that-does-not-match")]
    res = compute_item_results(vals, [ITEM])
    assert res["ch-am-001"]["validation_count"] == 1


def test_one_person_rating_twice_is_not_two_validators():
    vals = [_v("sme-a", 4), _v("sme-a", 5)]
    res = compute_item_results(vals, [ITEM])
    assert res["ch-am-001"]["validation_count"] == 1


def test_factual_disagreement_forces_adjudication_regardless_of_kappa():
    """
    Perfect cultural agreement, opposite factual verdicts. Kappa would be 1.0; the item
    must still go to adjudication - a factual dispute is a defect, not noise.
    """
    res = compute_item_results(
        _batch(("sme-a", "sme-b"), 10, factual_b="no"), _items(10))
    assert res["itm-0"]["needs_adjudication"] is True
    assert "factual" in res["itm-0"]["reason"].lower()


def test_kappa_below_the_floor_forces_adjudication():
    """
    Only the kappa branch can catch this batch. The pair alternates 3/4 against 4/3, so
    every single item is within 1 rubric point (the per-item gap branch never fires) and
    the factual verdicts match - but across the batch they agree on nothing, giving a
    kappa of -1.0. Reliability is a batch property; per-item closeness cannot stand in
    for it.
    """
    vals = []
    for i in range(10):
        iid, h = f"itm-{i}", item_content_hash(f"p{i}", f"e{i}")
        a, b = (3, 4) if i % 2 == 0 else (4, 3)
        vals.append(_v("sme-a", a, item_id=iid, h=h))
        vals.append(_v("sme-b", b, item_id=iid, h=h))

    res = compute_item_results(vals, _items(10))
    assert res["itm-0"]["needs_adjudication"] is True
    assert "kappa" in res["itm-0"]["reason"]
    assert res["itm-0"]["irr_score"] < 0.70


def test_factual_dispute_is_written_to_a_pack_with_a_null_irr_score(tmp_path):
    """
    Same scenario as test_factual_disagreement_forces_adjudication_regardless_of_kappa
    (identical cultural scores -> kappa would be 1.0, opposite factual verdicts), but
    exercised end-to-end through apply_results against a temp pack. A factual dispute
    must never be stamped onto disk as a passing irr_score - the pack should read
    validation_count=2 (two people did rate it) and irr_score=null (unresolved), not
    irr_score=1.0.
    """
    items = _items(10)
    vals = _batch(("sme-a", "sme-b"), 10, factual_b="no")
    results = compute_item_results(vals, items)
    assert results["itm-0"]["needs_adjudication"] is True
    assert results["itm-0"]["irr_score"] == 1.0  # the raw kappa would pass on its own

    pack_path = tmp_path / "disputed_v1.0.0.jsonl"
    rows = [
        {"id": item["id"], "prompt": item["prompt"], "expected_behavior": item["expected_behavior"],
         "validation_count": 0, "irr_score": None}
        for item in items
    ]
    pack_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    _, rows_by_path, newline_by_path = load_packs(tmp_path)
    written, changed = apply_results(results, rows_by_path, newline_by_path)

    assert pack_path in written
    updated = {
        json.loads(line)["id"]: json.loads(line)
        for line in pack_path.read_text(encoding="utf-8").splitlines()
    }
    assert updated["itm-0"]["validation_count"] == 2
    assert updated["itm-0"]["irr_score"] is None
