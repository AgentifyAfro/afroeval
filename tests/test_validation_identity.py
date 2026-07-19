"""
Proves the author-exclusion re-check can actually match: the id produced when an SME's
email is pseudonymised at authoring time (import_authored_items._pseudonymise) must equal
the id produced when the same email is pseudonymised again at validation-import time
(validation.identity.pseudonymise). Both call sites now share one implementation.
"""

from scripts.import_authored_items import _pseudonymise as pseudonymise_at_authoring
from validation.identity import pseudonymise


def test_authoring_and_import_time_pseudonymise_agree():
    email = "sme@example.com"
    assert pseudonymise_at_authoring(email) == pseudonymise(email)


def test_pseudonymise_is_deterministic_and_shaped_like_pack_values():
    result = pseudonymise("sme@example.com")
    assert result == pseudonymise("sme@example.com")
    assert result.startswith("sme-")
    assert len(result) == len("sme-") + 8


def test_pseudonymise_empty_identity_returns_empty_string():
    assert pseudonymise("") == ""
