import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import promote_pack as pp  # noqa: E402


def _write_pack(path, items):
    path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def _staged(id_, lang="ha"):
    return {"id": id_, "prompt": "p", "expected_behavior": "e", "language": lang,
            "domain": "agriculture", "cohort": "informal_rural", "provenance": "src 2020",
            "is_gold": False, "is_held_out": False, "tags": [], "difficulty": "standard",
            "sme_author_id": "sme-abc123", "validation_count": 1, "irr_score": None,
            "_authoring_status": "approve", "_sme_notes": "note", "_sme_author_identity": "a@b.com"}


def test_bump_minor():
    assert pp.bump_minor((1, 0, 0)) == (1, 1, 0)
    assert pp.format_version((1, 1, 0)) == "v1.1.0"


def test_clean_for_pack_strips_internal_and_resets_validation():
    out = pp.clean_for_pack(_staged("x"))
    assert not any(k.startswith("_") for k in out)     # underscore fields gone
    assert out["sme_author_id"] == "sme-abc123"        # kept for author exclusion
    assert out["validation_count"] == 0 and out["irr_score"] is None  # pending


def test_select_staged_by_ids_and_by_language():
    staged = [_staged("a", "ha"), _staged("b", "sw")]
    pack_items = [{"language": "ha"}]
    assert {i["id"] for i in pp.select_staged(staged, pack_items, None)} == {"a"}   # lang match
    assert {i["id"] for i in pp.select_staged(staged, pack_items, ["b"])} == {"b"}  # explicit ids


def test_build_next_pack_appends_and_projects_floor(tmp_path):
    cur = [dict(_staged(f"ag-ha-{n:03d}"), validation_count=2, irr_score=0.8) for n in range(8)]
    for i in cur:
        i.pop("_authoring_status", None)
        i.pop("_sme_notes", None)
        i.pop("_sme_author_identity", None)
    _write_pack(tmp_path / "agriculture_ha_v1.0.0.jsonl", cur)
    staged = [_staged(f"ag-ha-2{n:02d}") for n in range(3)]
    target, rows, added, scored = pp.build_next_pack(
        "agriculture_ha", tmp_path, staged, released_ids={"agriculture_ha_v1.0.0"})
    assert target.name == "agriculture_ha_v1.1.0.jsonl"
    assert added == ["ag-ha-200", "ag-ha-201", "ag-ha-202"]
    assert scored == 11


def test_build_next_pack_is_idempotent(tmp_path):
    _write_pack(tmp_path / "p_ha_v1.0.0.jsonl", [dict(_staged("p-1"), validation_count=2, irr_score=0.8)])
    staged = [_staged("p-2")]
    target, rows, added, scored = pp.build_next_pack("p_ha", tmp_path, staged, {"p_ha_v1.0.0"})
    _write_pack(target, rows)                     # simulate --apply
    _, rows2, added2, _ = pp.build_next_pack("p_ha", tmp_path, staged, {"p_ha_v1.0.0"})
    assert added2 == []                           # already present -> no dupes
    assert len(rows2) == len(rows)


def test_build_next_pack_refuses_released_target(tmp_path):
    _write_pack(tmp_path / "p_ha_v1.0.0.jsonl", [_staged("p-1")])
    with pytest.raises(ValueError, match="already released"):
        pp.build_next_pack("p_ha", tmp_path, [], {"p_ha_v1.0.0"}, to_version="v1.0.0")
