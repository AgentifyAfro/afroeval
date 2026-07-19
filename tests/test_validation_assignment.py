"""Assignment enforces the two rules that make a validation count."""
from validation.assignment import assign_validators

ROSTER = [
    {"validator_id": "sme-aaa", "languages": ["am", "en"]},
    {"validator_id": "sme-bbb", "languages": ["am", "sw"]},
    {"validator_id": "sme-ccc", "languages": ["am"]},
    {"validator_id": "sme-ddd", "languages": ["zu"]},
]


def test_assigns_exactly_two_validators():
    item = {"id": "ch-am-001", "language": "am", "sme_author_id": ""}
    assert len(assign_validators(item, ROSTER)) == 2


def test_never_assigns_the_author():
    """SME_ROLE_PACKS.md:76 - a validator may never rate an item they authored."""
    item = {"id": "ch-am-001", "language": "am", "sme_author_id": "sme-aaa"}
    assert "sme-aaa" not in assign_validators(item, ROSTER)


def test_only_assigns_validators_who_have_the_language():
    item = {"id": "ps-zu-001", "language": "zu", "sme_author_id": ""}
    # only sme-ddd speaks zu, so a pair cannot be formed
    assert assign_validators(item, ROSTER) == []


def test_returns_empty_when_fewer_than_two_are_eligible():
    """Better to assign nobody than to assign one and imply the item is on its way."""
    item = {"id": "ch-am-001", "language": "am", "sme_author_id": "sme-aaa"}
    small = [ROSTER[0], ROSTER[1]]  # aaa authored it, only bbb remains
    assert assign_validators(item, small) == []


def test_balances_load_across_eligible_validators():
    """
    Without balancing, the first two in the roster get every item and no other pair ever
    reaches the 10-item batch minimum needed for a kappa.
    """
    existing = {"sme-aaa": ["i1"] * 10, "sme-bbb": ["i1"] * 10, "sme-ccc": []}
    item = {"id": "ch-am-002", "language": "am", "sme_author_id": ""}
    assert "sme-ccc" in assign_validators(item, ROSTER, existing=existing)


def test_assignment_is_deterministic():
    item = {"id": "ch-am-001", "language": "am", "sme_author_id": ""}
    assert assign_validators(item, ROSTER) == assign_validators(item, ROSTER)
