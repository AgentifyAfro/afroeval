"""
Deterministic UUID helpers for AfroEval benchmark entities.

uuid5 is collision-resistant and deterministic: same inputs always produce
the same UUID. This means the seed script and the dispatcher can independently
compute the same item UUID without a lookup table.
"""

import uuid

# Fixed AfroEval namespace — never change this or all UUIDs will rotate.
AFROEVAL_NAMESPACE = uuid.UUID("e3d4f5a6-b7c8-4d9e-a0b1-c2d3e4f5a6b7")


def stable_pack_uuid(name: str, version: str) -> uuid.UUID:
    """Deterministic UUID for a benchmark pack (e.g. 'mobile_money_sw', 'v1.0.0')."""
    return uuid.uuid5(AFROEVAL_NAMESPACE, f"{name}_{version}")


def stable_item_uuid(item_string_id: str) -> uuid.UUID:
    """Deterministic UUID for a benchmark item from its string ID (e.g. 'mm-sw-001')."""
    return uuid.uuid5(AFROEVAL_NAMESPACE, item_string_id)
