"""
Pseudonymous SME identity.

sme_author_id and validator_id are published inside pack files, which are shared with
clients, so the schema requires them anonymised. Label Studio hands us real emails, so
hashing happens at the boundary. Deterministic: the same person keeps the same id across
imports, which is what makes "never validate your own item" checkable at all.
"""

import hashlib


def pseudonymise(identity: str) -> str:
    """Map a Label Studio identity (usually an email) to a stable pseudonymous id."""
    if not identity:
        return ""
    return "sme-" + hashlib.sha256(identity.encode()).hexdigest()[:8]
