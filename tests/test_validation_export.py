"""_select_validators lets an export concentrate on a chosen validator pool.

Spreading across the whole roster fragments pairs below MIN_SHARED_BATCH (10), so a
round can be scoped to e.g. one non-author pair to clear the kappa floor.
"""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "validation_export_tasks",
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "validation_export_tasks.py",
)
_ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ve)
select = _ve._select_validators

ROSTER = [
    {"validator_id": "sme-a", "languages": ["am"]},
    {"validator_id": "sme-b", "languages": ["am"]},
    {"validator_id": "sme-c", "languages": ["am"]},
]


def test_no_ids_returns_full_roster():
    assert select(ROSTER, None) == ROSTER
    assert select(ROSTER, []) == ROSTER


def test_restricts_to_given_ids_preserving_roster_order():
    out = select(ROSTER, ["sme-c", "sme-a"])
    assert [r["validator_id"] for r in out] == ["sme-a", "sme-c"]


def test_unknown_ids_are_ignored():
    assert select(ROSTER, ["sme-x"]) == []
