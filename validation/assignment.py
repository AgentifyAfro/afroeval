"""
Validator assignment for the Tier 1 path.

Two rules make a validation count, and both are enforced here AND re-checked at import - an
assignment bug must never silently produce a self-validated item:
  1. Two DISTINCT people per item (validation_count counts people, not ratings).
  2. A validator may never rate an item they authored (docs/SME_ROLE_PACKS.md:76).
"""


def assign_validators(
    item: dict,
    roster: list[dict],
    existing: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Pick exactly two eligible validator ids for one item, or [] if two cannot be found.

    Eligible = speaks the item's language AND did not author it. Ties break toward the
    validator with the smallest current load, so pairs accumulate the 10 shared items a
    kappa needs instead of piling everything on the first two names in the roster.

    Returns [] rather than a single id: assigning one validator would imply the item is on
    its way to Tier 1 when it structurally cannot get there.
    """
    load = existing or {}
    author = item.get("sme_author_id") or ""
    language = item.get("language")

    eligible = [
        r["validator_id"]
        for r in roster
        if language in r.get("languages", []) and r["validator_id"] != author
    ]
    if len(eligible) < 2:
        return []

    # Deterministic: load ascending, then id - so a re-run assigns the same pair.
    eligible.sort(key=lambda v: (len(load.get(v, [])), v))
    return eligible[:2]
