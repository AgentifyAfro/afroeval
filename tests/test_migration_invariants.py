"""Structural invariant: the Alembic migration graph has exactly ONE head.

Gap G9 — "the system cannot tell you something is missing." A duplicate/again-used
revision id or a forked down_revision produces multiple heads (or a cycle), which breaks
`alembic upgrade head` on prod. The a1b2c3d4e5f6 revision-ID collision survived seven
commits and a merge to master because nothing asserted this. This test runs in the normal
suite (no DB needed — it only reads the migration files) so the next collision fails CI.
"""
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_exactly_one_alembic_head():
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert len(heads) == 1, (
        f"Expected exactly one migration head, found {len(heads)}: {heads}. "
        "A branched down_revision or a duplicate/again-used revision id will break "
        "`alembic upgrade head` on prod — reconcile the migration graph to a single head."
    )
