import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import coverage_report as cr  # noqa: E402


def _item(id_, scored=True, vc=0, irr=None, tags=None):
    it = {"id": id_, "prompt": "p", "expected_behavior": "e",
          "language": "ha", "domain": "agriculture",
          "validation_count": vc, "irr_score": irr, "tags": tags or []}
    if not scored:
        it["is_gold"] = True
    return it


def test_parse_pack_filename():
    assert cr.parse_pack_filename("agriculture_ha_v1.0.0") == ("agriculture_ha", (1, 0, 0))
    assert cr.parse_pack_filename("community_health_am_v1.2.0") == ("community_health_am", (1, 2, 0))
    assert cr.parse_pack_filename("not_a_pack") is None


def test_item_tier():
    assert cr.item_tier(_item("a", vc=2, irr=0.8)) == "tier1"
    assert cr.item_tier(_item("b", vc=2, irr=0.5)) is None          # below IRR floor
    assert cr.item_tier(_item("c", vc=1, tags=["single_expert_validated"])) == "tier2"
    assert cr.item_tier(_item("d", vc=0)) is None                    # pending


def test_pack_status_counts_and_floor():
    items = [_item(f"i{n}", vc=2, irr=0.8) for n in range(8)]        # 8 validated tier1
    items += [_item("gold", scored=False)]                          # excluded from scored
    st = cr.pack_status(items)
    assert st["scored"] == 8
    assert st["floor_gap"] == 2
    assert st["tier1"] == 8 and st["pending"] == 0
    assert st["clears_floor"] is False and st["all_validated"] is True


def test_ready_to_flip():
    st = {"clears_floor": True, "all_validated": True}
    assert cr.ready_to_flip("agriculture_ha_v1.1.0", st, {"agriculture_ha_v1.0.0"}) is True
    assert cr.ready_to_flip("agriculture_ha_v1.0.0", st, {"agriculture_ha_v1.0.0"}) is False  # already released
    assert cr.ready_to_flip("x_v1.1.0", {"clears_floor": False, "all_validated": True}, set()) is False


def test_released_pack_ids(tmp_path):
    app = tmp_path / "app.py"
    app.write_text(
        'LANGUAGE_NAMES = {}\n'
        'PACK_CATALOG = [\n'
        '    {"id": "mobile_money_sw_v1.0.0", "label": "MM", "language": "sw"},\n'
        '    {"id": "customer_service_en_v1.0.0", "label": "CS", "language": "en"},\n'
        ']\n'
        'OTHER = ["id"]\n',
        encoding="utf-8",
    )
    assert cr.released_pack_ids(app) == {"mobile_money_sw_v1.0.0", "customer_service_en_v1.0.0"}
