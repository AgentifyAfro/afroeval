"""
Content hashing for validation staleness.

Item UUIDs are derived from the item's string id alone (benchmarks/ids.py), so an item's
TEXT can change while its identity stays fixed. Without a content hash a validation record
would silently remain attached to content nobody rated. Every validation row stores the hash
of what was actually in front of the validator.
"""

import hashlib

# NUL separator: without it, ("ab", "c") and ("a", "bc") would hash identically, so an edit
# that shifts text across the prompt/expected_behavior boundary would go undetected.
_SEP = "\x00"


def item_content_hash(prompt: str, expected_behavior: str) -> str:
    """sha256 of the item content a validator actually saw. 64 hex chars."""
    payload = f"{prompt}{_SEP}{expected_behavior}".encode()
    return hashlib.sha256(payload).hexdigest()
