# Item Validation Path — Core Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Tier 1 publication reachable — two independent SMEs rate an item, an inter-rater reliability score is computed, and `validation_count` / `irr_score` are written back onto the item.

**Architecture:** A new `item_validations` table holds one row per (item, validator) with the four-part instrument from `SME_ROLE_PACKS.md`. An export script assigns each item to two eligible validators (never its author) and pushes them to a Label Studio validation project; an import script reads ratings back. A pure `validation/irr.py` module computes quadratic-weighted Cohen's kappa per rater-pair per batch. A writeback step stamps the results onto the pack JSONL, which is the source of truth.

**Tech Stack:** Python 3.12, SQLModel + Alembic, Label Studio REST (`hitl/client.py`), scikit-learn `cohen_kappa_score`, pytest.

**Spec:** `docs/superpowers/specs/2026-07-19-item-validation-path-design.md`

## Scope

This plan covers spec gaps **1–5 and 7** — the loop that takes an item from unvalidated to Tier 1, including the adjudication path for pairs that disagree. It produces working software on its own: after this plan, an item can legitimately reach `validation_count: 2` and a real `irr_score`.

**Deliberately in follow-on plans, each independently testable:**
- **Gap 6 — promotion** (`staged candidates + validation records → versioned pack`). Depends on this loop existing.
- **Gap 8 — gold drift monitoring.** Blocked on data regardless: `cultural_rubric_gold_score` is unpopulated on all 28 gold items.
- **Gap 9 — `ResponseReview` consumption.** A different subsystem entirely (response calibration, not item validation).

## Global Constraints

- **IRR floor is 0.70.** `BENCHMARK_ITEM_SCHEMA.md:57` and `scripts/import_authored_items.py:51` both currently say 0.60 and must be updated.
- **`irr_score` is per rater-pair per batch**, not per item. Computed once across every item a pair both rated, then written onto each item in that batch.
- **Minimum shared batch is 10 items.** Below that `irr_score` stays `null` and the item is not Tier 1. Never estimated, extrapolated, or borrowed from another pair.
- **Kappa is quadratic-weighted, computed on `cultural_score` (1–5) only.** Factual accuracy is a separate hard gate, never averaged into kappa.
- **A validator may never rate an item they authored.** Enforced at assignment AND re-checked at import.
- **`validation_count` counts distinct people.** Never incremented for one person rating twice.
- **Every validation row stores `item_content_hash`** = `sha256(prompt + "\x00" + expected_behavior)`. A row whose hash no longer matches the item is stale and does not count.
- **The pack JSONL is the source of truth.** Writeback targets the JSONL; the DB is re-seeded from it.
- **`benchmarks/packs/*.jsonl` is SME-validated data.** Only the writeback step in Task 6 writes to it, and only for `validation_count` / `irr_score` / adjudication fields — never prompts, never expected_behavior, never item content.
- **Cohort vocabulary is `formal`, `informal_economy`, `informal_rural` only.**
- Never modify `ail/hallucination_probes.py`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `db/models.py` | `ItemValidation` table | Modify |
| `db/migrations/versions/d1e2f3a4b5c6_add_item_validations.py` | schema migration | Create |
| `validation/__init__.py` | package marker | Create |
| `validation/hashing.py` | content hash — the staleness primitive | Create |
| `validation/irr.py` | quadratic-weighted kappa, batch grouping, floor check | Create |
| `validation/assignment.py` | pick 2 eligible validators per item | Create |
| `hitl/label_config.py` | `build_validation_label_config()` + `VALIDATION_PROJECT_TITLE` | Modify |
| `scripts/data/validator_roster.json` | who validates which languages | Create |
| `scripts/validation_export_tasks.py` | assign + push to Label Studio | Create |
| `scripts/validation_import_ratings.py` | read ratings → `item_validations` | Create |
| `scripts/validation_writeback.py` | compute IRR, stamp packs, report adjudication | Create |
| `scripts/seed_packs_to_db.py` | carry `validation_count` / `irr_score` into the DB | Modify |
| `scripts/import_authored_items.py` | IRR floor 0.60 → 0.70 | Modify |
| `docs/BENCHMARK_ITEM_SCHEMA.md` | IRR floor + `irr_score` semantics | Modify |
| `requirements.txt` | declare `scikit-learn` | Modify |
| `tests/test_validation_hashing.py` · `test_validation_irr.py` · `test_validation_assignment.py` · `test_validation_writeback.py` | tests | Create |

---

### Task 1: Storage — `item_validations` table and the content hash

**Files:**
- Create: `validation/__init__.py`, `validation/hashing.py`, `tests/test_validation_hashing.py`
- Modify: `db/models.py` (below `ResponseReview`, ~line 198)
- Create: `db/migrations/versions/d1e2f3a4b5c6_add_item_validations.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validation.hashing.item_content_hash(prompt: str, expected_behavior: str) -> str`; `db.models.ItemValidation`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validation_hashing.py`:

```python
"""The content hash is what makes a stale validation detectable."""
from validation.hashing import item_content_hash


def test_hash_is_stable_for_identical_content():
    a = item_content_hash("What is the fee?", "Names the operator tariff page.")
    b = item_content_hash("What is the fee?", "Names the operator tariff page.")
    assert a == b
    assert len(a) == 64


def test_hash_changes_when_the_prompt_changes():
    before = item_content_hash("What is the fee?", "Names the tariff page.")
    after = item_content_hash("What is the charge?", "Names the tariff page.")
    assert before != after


def test_hash_changes_when_expected_behavior_changes():
    before = item_content_hash("What is the fee?", "Names the tariff page.")
    after = item_content_hash("What is the fee?", "States the exact amount.")
    assert before != after


def test_field_boundary_cannot_be_forged():
    """
    Concatenating without a separator would make ("ab","c") and ("a","bc") hash alike,
    letting a content edit that shifts text across the field boundary go undetected.
    """
    assert item_content_hash("ab", "c") != item_content_hash("a", "bc")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_hashing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validation'`

- [ ] **Step 3: Create the package and the hash**

Create `validation/__init__.py` (empty file).

Create `validation/hashing.py`:

```python
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
    payload = f"{prompt}{_SEP}{expected_behavior}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_hashing.py -v`
Expected: 4 passed.

- [ ] **Step 5: Add the model**

In `db/models.py`, add `UniqueConstraint` to the sqlmodel import line so it reads:

```python
from sqlmodel import JSON, Column, Field, Relationship, SQLModel, UniqueConstraint
```

Then add below the `ResponseReview` class:

```python
class ItemValidation(SQLModel, table=True):
    """
    One SME's validation of one benchmark item (Methodology v1.4 Tier 1 path).

    Distinct from ResponseReview, which rates a model RESPONSE on the six scorecard
    dimensions. This rates the ITEM itself against the four-part validator instrument in
    docs/SME_ROLE_PACKS.md.
    """
    __tablename__ = "item_validations"
    __table_args__ = (
        UniqueConstraint("item_id", "validator_id", name="uq_item_validations_item_validator"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    item_id: uuid.UUID = Field(foreign_key="benchmark_items.id", index=True)

    # sha256 of the item content at rating time. A row whose hash no longer matches the
    # item is STALE and must not count toward validation_count.
    item_content_hash: str = Field(index=True)

    validator_id: str = Field(index=True)      # pseudonymised, as sme_author_id already is
    batch_id: str = Field(default="", index=True)  # the (pair, batch) kappa is computed over

    factual_accuracy: str                      # "yes" | "no" | "needs_revision" - hard gate
    language_quality: int                      # 1-3
    cultural_score: int                        # 1-5, the kappa input
    schema_compliant: bool
    justification: str = ""
    verdict: str                               # "validated" | "needs_revision"

    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 6: Create the migration**

Create `db/migrations/versions/d1e2f3a4b5c6_add_item_validations.py`:

```python
"""add item_validations table (Methodology v1.4 Tier 1 path)

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-07-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'item_validations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('item_content_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('validator_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('batch_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                  server_default=''),
        sa.Column('factual_accuracy', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('language_quality', sa.Integer(), nullable=False),
        sa.Column('cultural_score', sa.Integer(), nullable=False),
        sa.Column('schema_compliant', sa.Boolean(), nullable=False),
        sa.Column('justification', sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                  server_default=''),
        sa.Column('verdict', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['benchmark_items.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id', 'validator_id',
                            name='uq_item_validations_item_validator'),
    )
    op.create_index(op.f('ix_item_validations_item_id'), 'item_validations', ['item_id'])
    op.create_index(op.f('ix_item_validations_validator_id'), 'item_validations',
                    ['validator_id'])
    op.create_index(op.f('ix_item_validations_batch_id'), 'item_validations', ['batch_id'])
    op.create_index(op.f('ix_item_validations_item_content_hash'), 'item_validations',
                    ['item_content_hash'])


def downgrade() -> None:
    op.drop_index(op.f('ix_item_validations_item_content_hash'), table_name='item_validations')
    op.drop_index(op.f('ix_item_validations_batch_id'), table_name='item_validations')
    op.drop_index(op.f('ix_item_validations_validator_id'), table_name='item_validations')
    op.drop_index(op.f('ix_item_validations_item_id'), table_name='item_validations')
    op.drop_table('item_validations')
```

- [ ] **Step 7: Verify the migration chain has a single head**

Run: `.\.venv\Scripts\python.exe -m alembic heads`
Expected: exactly one line, `d1e2f3a4b5c6 (head)`. If two heads appear, the `down_revision` is wrong — fix it before continuing.

- [ ] **Step 8: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q` then `.\.venv\Scripts\python.exe -m ruff check .`
Expected: all pass, ruff clean. (Trust the exit code — the pytest summary line is swallowed on this machine.)

- [ ] **Step 9: Commit**

```bash
git add validation/ tests/test_validation_hashing.py db/models.py \
        db/migrations/versions/d1e2f3a4b5c6_add_item_validations.py
git commit -m "feat(validation): item_validations table + content hash

One row per (item, validator) holding the four-part instrument from
SME_ROLE_PACKS.md. A DB-level unique constraint on (item_id, validator_id)
prevents the double-count that ResponseReview relies on in-memory Python dedupe
to avoid.

item_content_hash makes staleness detectable: item UUIDs derive from the string
id alone, so an item's text can change under a stable identity and a validation
would otherwise stay silently attached to content nobody rated."
```

---

### Task 2: IRR — quadratic-weighted kappa per rater-pair per batch

**Files:**
- Create: `validation/irr.py`, `tests/test_validation_irr.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing from Task 1 (pure functions over plain data).
- Produces:
  - `validation.irr.MIN_SHARED_BATCH: int = 10`
  - `validation.irr.IRR_FLOOR: float = 0.70`
  - `validation.irr.pair_kappa(a_scores: list[int], b_scores: list[int]) -> float | None`
  - `validation.irr.batch_key(validator_a: str, validator_b: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validation_irr.py`:

```python
"""
Kappa is a property of a RATER PAIR over a BATCH, never of a single item.
These tests lock that framing as much as the arithmetic.
"""
import pytest

from validation.irr import IRR_FLOOR, MIN_SHARED_BATCH, batch_key, pair_kappa


def test_perfect_agreement_is_one():
    scores = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    assert pair_kappa(scores, scores) == pytest.approx(1.0)


def test_below_minimum_batch_returns_none_not_a_number():
    """9 shared items cannot produce a defensible kappa. None, never an estimate."""
    nine = [1, 2, 3, 4, 5, 1, 2, 3, 4]
    assert len(nine) == MIN_SHARED_BATCH - 1
    assert pair_kappa(nine, nine) is None


def test_exactly_the_minimum_batch_is_allowed():
    ten = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    assert len(ten) == MIN_SHARED_BATCH
    assert pair_kappa(ten, ten) is not None


def test_near_agreement_scores_higher_than_far_disagreement():
    """
    Quadratic weighting is the point: on an ordinal 1-5 scale, 4-vs-5 must cost far less
    than 1-vs-5. Unweighted kappa would treat them identically.
    """
    a = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    near = [1, 2, 3, 4, 4, 1, 2, 3, 4, 4]   # off by one on two items
    far = [5, 2, 3, 4, 1, 5, 2, 3, 4, 1]    # inverted on the same two items
    assert pair_kappa(a, near) > pair_kappa(a, far)


def test_mismatched_lengths_raise_rather_than_truncate():
    """Silent zip truncation would pair each rating with the wrong item."""
    with pytest.raises(ValueError, match="same length"):
        pair_kappa([1] * 10, [1] * 9)


def test_batch_key_is_order_independent():
    """The pair (A,B) and (B,A) are the same pair and must share one batch."""
    assert batch_key("sme-aaa", "sme-bbb") == batch_key("sme-bbb", "sme-aaa")


def test_irr_floor_is_the_agreed_070():
    assert IRR_FLOOR == 0.70
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_irr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validation.irr'`

- [ ] **Step 3: Declare the dependency**

Add to `requirements.txt`, after the `fairlearn>=0.10.0` line:

```
scikit-learn>=1.5.0
```

`cohen_kappa_score` currently works only transitively via fairlearn. Declaring it makes an existing implicit dependency explicit — nothing new is installed.

- [ ] **Step 4: Implement**

Create `validation/irr.py`:

```python
"""
Inter-rater reliability for item validation (Methodology v1.4).

irr_score is a property of a RATER PAIR over a BATCH, not of an item. Cohen's kappa is
undefined for a single item, so it is computed once across every item a pair both rated and
that value is written onto each item in the batch. See
docs/superpowers/specs/2026-07-19-item-validation-path-design.md.
"""

from sklearn.metrics import cohen_kappa_score

# Below this many shared items a kappa is noise wearing a number. irr_score stays null and
# the item is not Tier 1 - never estimated, extrapolated, or borrowed from another pair.
MIN_SHARED_BATCH = 10

# Methodology v1.4. Three docs said 0.70 and one said 0.60; 0.70 governs. Also the
# conventional "substantial agreement" bar for Cohen's kappa.
IRR_FLOOR = 0.70


def batch_key(validator_a: str, validator_b: str) -> str:
    """Order-independent identifier for a rater pair. (A,B) and (B,A) are one pair."""
    lo, hi = sorted([validator_a, validator_b])
    return f"{lo}|{hi}"


def pair_kappa(a_scores: list[int], b_scores: list[int]) -> float | None:
    """
    Quadratic-weighted Cohen's kappa over one pair's shared items.

    Computed on cultural_score (1-5) only. Factual accuracy is a separate hard gate and is
    never averaged in - two validators disagreeing on whether an item is factually correct
    is a blocking defect, not a reliability statistic.

    Returns None when the shared batch is under MIN_SHARED_BATCH.
    """
    if len(a_scores) != len(b_scores):
        raise ValueError(
            f"rating lists must be the same length: {len(a_scores)} vs {len(b_scores)}"
        )
    if len(a_scores) < MIN_SHARED_BATCH:
        return None
    if a_scores == b_scores:
        # cohen_kappa_score returns nan when both raters use a single identical label
        # (zero variance). Perfect agreement is 1.0 by definition.
        return 1.0
    return float(cohen_kappa_score(a_scores, b_scores, weights="quadratic"))
```

- [ ] **Step 5: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_irr.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add validation/irr.py tests/test_validation_irr.py requirements.txt
git commit -m "feat(validation): quadratic-weighted kappa per rater-pair per batch

Kappa is undefined for a single item, so irr_score is computed once per pair per
batch and stamped onto each item in it. Under 10 shared items it returns None
rather than a number nobody should trust.

Quadratic weighting because the scale is ordinal: 4-vs-5 must cost far less than
1-vs-5, which unweighted kappa treats identically. Computed on cultural_score
only - factual accuracy is a hard gate, not a reliability input.

Declares scikit-learn, which cohen_kappa_score has been using transitively via
fairlearn."
```

---

### Task 3: Assignment — two eligible validators, never the author

**Files:**
- Create: `validation/assignment.py`, `scripts/data/validator_roster.json`, `tests/test_validation_assignment.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validation.assignment.assign_validators(item: dict, roster: list[dict], existing: dict[str, list[str]] | None = None) -> list[str]` returning 0 or 2 validator ids.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validation_assignment.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_assignment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validation.assignment'`

- [ ] **Step 3: Create the roster**

Create `scripts/data/validator_roster.json`. These are placeholders — the founder replaces
`validator_id` values with real pseudonymised ids before the first export:

```json
[
  {"validator_id": "sme-placeholder-1", "languages": ["am", "en"], "domains": ["community_health"]},
  {"validator_id": "sme-placeholder-2", "languages": ["sw", "sheng", "en"], "domains": ["mobile_money"]},
  {"validator_id": "sme-placeholder-3", "languages": ["ha", "yo", "en"], "domains": ["agriculture", "customer_service"]},
  {"validator_id": "sme-placeholder-4", "languages": ["zu", "so", "en"], "domains": ["public_services", "remittance"]}
]
```

- [ ] **Step 4: Implement**

Create `validation/assignment.py`:

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_assignment.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add validation/assignment.py scripts/data/validator_roster.json \
        tests/test_validation_assignment.py
git commit -m "feat(validation): validator assignment with author exclusion and load balance

Returns exactly 2 eligible validators or none at all - assigning one would imply
an item is on its way to Tier 1 when it structurally cannot get there.

Load-balances across eligible validators so pairs accumulate the 10 shared items
kappa needs, instead of every item landing on the first two roster names.
Deterministic, so a re-run assigns the same pair."
```

---

### Task 4: The validation label config and export script

**Files:**
- Modify: `hitl/label_config.py`
- Create: `scripts/validation_export_tasks.py`

**Interfaces:**
- Consumes: `validation.assignment.assign_validators`, `validation.hashing.item_content_hash`.
- Produces: `hitl.label_config.build_validation_label_config() -> str`, `hitl.label_config.VALIDATION_PROJECT_TITLE: str`.

- [ ] **Step 1: Add the label config**

In `hitl/label_config.py`, add at the end:

```python
VALIDATION_PROJECT_TITLE = "AfroEval — SME Item Validation"


def build_validation_label_config() -> str:
    """
    The four-part validator instrument from docs/SME_ROLE_PACKS.md:77-97.

    Distinct from the authoring config: the SME is not writing an item here, they are
    judging one that already exists. cultural_score is the kappa input; factual_accuracy is
    a hard gate that sends an item to adjudication on disagreement regardless of kappa.
    """
    return f"""
<View>
  <Header value="Validate this benchmark item"/>
  <Text name="item_language" value="$language" />
  <Text name="item_domain" value="$domain" />
  <Header value="Prompt"/>
  <Text name="prompt" value="$prompt"/>
  <Header value="Expected behaviour (the ground truth an evaluator scores against)"/>
  <Text name="expected_behavior" value="$expected_behavior"/>
  <Header value="Provenance"/>
  <Text name="provenance" value="$provenance"/>

  <Header value="1. Factual accuracy — is the expected behaviour correct?"/>
  {_choices("factual_accuracy", ["yes", "no", "needs_revision"])}

  <Header value="2. Language quality (1 unnatural — 3 native register)"/>
  {_choices("language_quality", ["1", "2", "3"])}

  <Header value="3. Cultural appropriateness (1-5, per CULTURAL_RUBRIC_V1.md)"/>
  {_choices("cultural_score", ["1", "2", "3", "4", "5"])}

  <Header value="4. Schema compliant — required fields present, provenance cites a dated source, cohort is one of formal / informal_economy / informal_rural?"/>
  {_choices("schema_compliant", ["yes", "no"])}

  <Header value="Justification (one sentence — required)"/>
  <TextArea name="justification" toName="prompt" rows="3" maxSubmissions="1"/>

  <Header value="Verdict"/>
  {_choices("verdict", ["validated", "needs_revision"])}
</View>
""".strip()
```

- [ ] **Step 2: Verify the config parses and offers the right choices**

Run:

```bash
.venv/Scripts/python.exe -c "import re; from hitl.label_config import build_validation_label_config as b; c=b(); print(re.findall(r'name=\"(\w+)\"', c))"
```

Expected: the list contains `factual_accuracy`, `language_quality`, `cultural_score`, `schema_compliant`, `justification`, `verdict`.

- [ ] **Step 3: Write the export script**

Create `scripts/validation_export_tasks.py`:

```python
"""
Push benchmark items into the SME item-VALIDATION Label Studio project.

Distinct from scripts/hitl_export_tasks.py, which exports model RESPONSES for calibration.
This exports ITEMS for Tier 1 validation: each item is assigned to exactly two eligible
validators who did not author it (validation/assignment.py).

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_export_tasks.py --packs mobile_money_sw_v1.0.0
    .\\.venv\\Scripts\\python.exe scripts/validation_export_tasks.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.loader import load_pack
from hitl.client import LabelStudioClient
from hitl.label_config import VALIDATION_PROJECT_TITLE, build_validation_label_config
from validation.assignment import assign_validators
from validation.hashing import item_content_hash
from validation.irr import batch_key

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"
_ROSTER = Path(__file__).parent / "data" / "validator_roster.json"


def _load_roster() -> list[dict]:
    with _ROSTER.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packs", nargs="+", default=None,
                        help="Pack ids to export. Default: every pack file.")
    parser.add_argument("--project-title", default=VALIDATION_PROJECT_TITLE)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report assignments without touching Label Studio.")
    args = parser.parse_args()

    roster = _load_roster()
    pack_ids = args.packs or [p.stem for p in sorted(_PACKS_DIR.glob("*.jsonl"))]

    tasks: list[dict] = []
    load: dict[str, list[str]] = {}
    unassignable: list[tuple[str, str]] = []

    for pack_id in pack_ids:
        for item in load_pack(pack_id):
            pair = assign_validators(item, roster, existing=load)
            if not pair:
                unassignable.append((item["id"], item.get("language", "?")))
                continue
            for v in pair:
                load.setdefault(v, []).append(item["id"])
            tasks.append({
                "item_id": item["id"],
                "prompt": item["prompt"],
                "expected_behavior": item["expected_behavior"],
                "provenance": item.get("provenance", ""),
                "language": item.get("language", ""),
                "domain": item.get("domain", ""),
                "assigned_validators": ",".join(pair),
                "batch_id": batch_key(pair[0], pair[1]),
                "item_content_hash": item_content_hash(
                    item["prompt"], item["expected_behavior"]
                ),
            })

    print(f"Assignable items: {len(tasks)}")
    for v, items in sorted(load.items()):
        print(f"   {v}: {len(items)} items")
    if unassignable:
        print(f"\nUNASSIGNABLE ({len(unassignable)}) — fewer than 2 eligible validators:")
        for iid, lang in unassignable[:20]:
            print(f"   {iid} ({lang})")
        print("   Add a second validator for these languages to scripts/data/validator_roster.json.")

    if args.dry_run:
        print("\n--dry-run: nothing sent to Label Studio.")
        return

    client = LabelStudioClient()
    project = client.get_or_create_project(args.project_title, build_validation_label_config())
    result = client.import_tasks(project["id"], tasks)
    print(f"\nProject '{args.project_title}' (id={project['id']}): imported {len(tasks)} task(s)")
    print(f"   {result}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify the dry run**

Run: `.\.venv\Scripts\python.exe scripts/validation_export_tasks.py --dry-run`
Expected: prints an assignable count, a per-validator load breakdown, and an unassignable list (the placeholder roster covers every language once, so most items will be unassignable until real validators are added — that is correct behaviour, not a bug). Nothing is sent to Label Studio.

- [ ] **Step 5: Run the full suite and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q` and `.\.venv\Scripts\python.exe -m ruff check .`

```bash
git add hitl/label_config.py scripts/validation_export_tasks.py
git commit -m "feat(validation): validator label config + item export with assignment

Implements the four-part instrument from SME_ROLE_PACKS.md as a Label Studio
config, and an export that assigns each item to two eligible validators.

Items with fewer than two eligible validators are reported as UNASSIGNABLE
rather than silently exported to one person - a language with a single
contracted SME cannot produce a Tier 1 item, and the operator needs to see that
before paying for the work."
```

---

### Task 5: Import ratings into `item_validations`

**Files:**
- Create: `scripts/validation_import_ratings.py`

**Interfaces:**
- Consumes: `db.models.ItemValidation`, `validation.hashing.item_content_hash`, `benchmarks.ids.stable_item_uuid`.
- Produces: rows in `item_validations`.

- [ ] **Step 1: Write the script**

Create `scripts/validation_import_ratings.py`:

```python
"""
Read SME item-validation ratings out of Label Studio into item_validations.

Re-checks the author-exclusion rule that assignment already enforced: an assignment bug
must never silently produce a self-validated item.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_import_ratings.py
"""

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.ids import stable_item_uuid
from db.models import BenchmarkItem, ItemValidation
from db.session import get_engine
from hitl.client import LabelStudioClient
from hitl.label_config import VALIDATION_PROJECT_TITLE

_CHOICE_FIELDS = ("factual_accuracy", "language_quality", "cultural_score",
                  "schema_compliant", "verdict")


def _parse(annotation: dict) -> dict:
    """Flatten one Label Studio annotation into the instrument's fields."""
    out: dict = {}
    for r in annotation.get("result", []):
        name = r.get("from_name")
        val = r.get("value", {})
        if name in _CHOICE_FIELDS:
            choices = val.get("choices") or []
            if choices:
                out[name] = choices[0]
        elif name == "justification":
            texts = val.get("text") or []
            if texts:
                out["justification"] = texts[0]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-title", default=VALIDATION_PROJECT_TITLE)
    args = parser.parse_args()

    client = LabelStudioClient()
    project = client.find_project_by_title(args.project_title)
    if project is None:
        print(f"No Label Studio project titled {args.project_title!r}.")
        return

    users = {u["id"]: (u.get("email") or f"user_{u['id']}") for u in client.list_users()}
    engine = get_engine()
    written = skipped_self = skipped_incomplete = skipped_dupe = 0

    with Session(engine) as session:
        for task in client.export_annotated_tasks(project["id"]):
            data = task.get("data", {})
            item_uuid = stable_item_uuid(data["item_id"])
            item = session.get(BenchmarkItem, item_uuid)
            if item is None:
                continue

            for ann in task.get("annotations", []):
                parsed = _parse(ann)
                if not all(k in parsed for k in _CHOICE_FIELDS):
                    skipped_incomplete += 1
                    continue

                validator = users.get(ann.get("completed_by"), "")
                # Re-check author exclusion. Assignment enforces it; if an assignment bug
                # ever lets one through, it must die here rather than become a Tier 1 item.
                if validator and validator == (item.sme_author_id or ""):
                    skipped_self += 1
                    continue

                existing = session.exec(
                    select(ItemValidation).where(
                        ItemValidation.item_id == item_uuid,
                        ItemValidation.validator_id == validator,
                    )
                ).first()
                if existing is not None:
                    skipped_dupe += 1
                    continue

                session.add(ItemValidation(
                    item_id=item_uuid,
                    item_content_hash=data.get("item_content_hash", ""),
                    validator_id=validator,
                    batch_id=data.get("batch_id", ""),
                    factual_accuracy=parsed["factual_accuracy"],
                    language_quality=int(parsed["language_quality"]),
                    cultural_score=int(parsed["cultural_score"]),
                    schema_compliant=parsed["schema_compliant"] == "yes",
                    justification=parsed.get("justification", ""),
                    verdict=parsed["verdict"],
                ))
                written += 1
        session.commit()

    print(f"Wrote {written} validation row(s).")
    print(f"  skipped — already recorded for this validator: {skipped_dupe}")
    print(f"  skipped — incomplete instrument:                {skipped_incomplete}")
    print(f"  skipped — validator authored the item:          {skipped_self}")
```

Add at the end of the file:

```python

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs against an empty project**

Run: `.\.venv\Scripts\python.exe scripts/validation_import_ratings.py`
Expected: `No Label Studio project titled 'AfroEval — SME Item Validation'.` and a clean exit — the validation project does not exist until Task 4's export is run for real.

- [ ] **Step 3: Run the suite and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q` and `.\.venv\Scripts\python.exe -m ruff check .`

```bash
git add scripts/validation_import_ratings.py
git commit -m "feat(validation): import SME item ratings into item_validations

Re-checks author exclusion at import even though assignment already enforces it -
an assignment bug must not be able to produce a self-validated Tier 1 item.

Dedupes against the DB rather than an in-memory set, so a re-run cannot
double-count the way the calibration importer can."
```

---

### Task 6: Writeback — compute IRR, stamp the packs, flag adjudication

**Files:**
- Create: `scripts/validation_writeback.py`, `tests/test_validation_writeback.py`
- Modify: `scripts/seed_packs_to_db.py`, `scripts/import_authored_items.py:51`, `docs/BENCHMARK_ITEM_SCHEMA.md`

**Interfaces:**
- Consumes: `validation.irr.pair_kappa`, `validation.irr.IRR_FLOOR`, `validation.hashing.item_content_hash`, `db.models.ItemValidation`.
- Produces: `scripts.validation_writeback.compute_item_results(validations, items) -> dict[str, dict]` — per item id, `{"validation_count": int, "irr_score": float | None, "needs_adjudication": bool, "reason": str}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validation_writeback.py`:

```python
"""The rules that decide whether an item is Tier 1."""
from scripts.validation_writeback import compute_item_results
from validation.hashing import item_content_hash

ITEM = {"id": "ch-am-001", "prompt": "p", "expected_behavior": "e"}
HASH = item_content_hash("p", "e")


def _v(validator, cultural, factual="yes", h=HASH, item_id="ch-am-001"):
    return {"item_id": item_id, "validator_id": validator, "cultural_score": cultural,
            "factual_accuracy": factual, "item_content_hash": h}


def _batch(pair, n, cultural_a=4, cultural_b=4, factual_b="yes"):
    """n items rated by the same pair, so the batch clears MIN_SHARED_BATCH."""
    out = []
    for i in range(n):
        iid = f"itm-{i}"
        out.append(_v(pair[0], cultural_a, item_id=iid,
                      h=item_content_hash(f"p{i}", f"e{i}")))
        out.append(_v(pair[1], cultural_b, factual=factual_b, item_id=iid,
                      h=item_content_hash(f"p{i}", f"e{i}")))
    return out


def _items(n):
    return [{"id": f"itm-{i}", "prompt": f"p{i}", "expected_behavior": f"e{i}"}
            for i in range(n)]


def test_two_validators_over_a_full_batch_yields_an_irr_score():
    res = compute_item_results(_batch(("sme-a", "sme-b"), 10), _items(10))
    assert res["itm-0"]["validation_count"] == 2
    assert res["itm-0"]["irr_score"] is not None


def test_short_batch_leaves_irr_null():
    """9 shared items: validated by two people, but no defensible reliability number."""
    res = compute_item_results(_batch(("sme-a", "sme-b"), 9), _items(9))
    assert res["itm-0"]["validation_count"] == 2
    assert res["itm-0"]["irr_score"] is None


def test_stale_validation_does_not_count():
    """A rating whose content hash no longer matches the item is attached to text nobody rated."""
    vals = [_v("sme-a", 4), _v("sme-b", 4, h="stale-hash-that-does-not-match")]
    res = compute_item_results(vals, [ITEM])
    assert res["ch-am-001"]["validation_count"] == 1


def test_one_person_rating_twice_is_not_two_validators():
    vals = [_v("sme-a", 4), _v("sme-a", 5)]
    res = compute_item_results(vals, [ITEM])
    assert res["ch-am-001"]["validation_count"] == 1


def test_factual_disagreement_forces_adjudication_regardless_of_kappa():
    """
    Perfect cultural agreement, opposite factual verdicts. Kappa would be 1.0; the item
    must still go to adjudication - a factual dispute is a defect, not noise.
    """
    res = compute_item_results(
        _batch(("sme-a", "sme-b"), 10, factual_b="no"), _items(10))
    assert res["itm-0"]["needs_adjudication"] is True
    assert "factual" in res["itm-0"]["reason"].lower()


def test_kappa_below_the_floor_forces_adjudication():
    res = compute_item_results(
        _batch(("sme-a", "sme-b"), 10, cultural_a=1, cultural_b=5), _items(10))
    assert res["itm-0"]["needs_adjudication"] is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_writeback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.validation_writeback'`

- [ ] **Step 3: Implement the pure function and the script**

Create `scripts/validation_writeback.py`:

```python
"""
Turn item_validations rows into validation_count / irr_score on the pack files.

The pack JSONL is the source of truth (the DB is a mirror re-seeded from it), so this writes
there - and ONLY to validation_count, irr_score and needs_adjudication. Item content is
never touched.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_writeback.py --dry-run
    .\\.venv\\Scripts\\python.exe scripts/validation_writeback.py --apply
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validation.hashing import item_content_hash
from validation.irr import IRR_FLOOR, batch_key, pair_kappa

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"


def compute_item_results(validations: list[dict], items: list[dict]) -> dict[str, dict]:
    """
    Per item: how many DISTINCT non-stale validators rated it, the kappa of the pair that
    rated it (computed over their whole shared batch), and whether it needs adjudication.

    validations: dicts with item_id, validator_id, cultural_score, factual_accuracy,
                 item_content_hash.
    items:       dicts with id, prompt, expected_behavior.
    """
    live_hash = {i["id"]: item_content_hash(i["prompt"], i["expected_behavior"])
                 for i in items}

    # Drop stale rows first: a rating attached to content that has since changed is not a
    # rating of this item.
    fresh = [v for v in validations
             if v.get("item_content_hash") == live_hash.get(v["item_id"])]

    by_item: dict[str, dict[str, dict]] = defaultdict(dict)
    for v in fresh:
        # dict keyed by validator_id: one person rating twice counts once
        by_item[v["item_id"]][v["validator_id"]] = v

    # Group ratings by pair so kappa is computed over the pair's whole shared batch.
    pair_scores: dict[str, tuple[list[int], list[int]]] = {}
    for item_id, raters in by_item.items():
        if len(raters) != 2:
            continue
        a, b = sorted(raters)
        key = batch_key(a, b)
        sa, sb = pair_scores.setdefault(key, ([], []))
        sa.append(int(raters[a]["cultural_score"]))
        sb.append(int(raters[b]["cultural_score"]))

    pair_kappa_by_key = {k: pair_kappa(a, b) for k, (a, b) in pair_scores.items()}

    results: dict[str, dict] = {}
    for item in items:
        item_id = item["id"]
        raters = by_item.get(item_id, {})
        count = len(raters)
        kappa = None
        adjudicate = False
        reason = ""

        if count == 2:
            a, b = sorted(raters)
            kappa = pair_kappa_by_key.get(batch_key(a, b))
            if raters[a]["factual_accuracy"] != raters[b]["factual_accuracy"]:
                adjudicate = True
                reason = (f"factual accuracy disputed: {raters[a]['factual_accuracy']} "
                          f"vs {raters[b]['factual_accuracy']}")
            elif kappa is not None and kappa < IRR_FLOOR:
                adjudicate = True
                reason = f"pair kappa {kappa:.3f} below floor {IRR_FLOOR}"
            elif abs(int(raters[a]["cultural_score"]) - int(raters[b]["cultural_score"])) > 1:
                adjudicate = True
                reason = "cultural scores differ by more than 1 rubric point"

        results[item_id] = {
            "validation_count": count,
            "irr_score": kappa,
            "needs_adjudication": adjudicate,
            "reason": reason,
        }
    return results


def _load_validations() -> list[dict]:
    from sqlmodel import Session, select

    from db.models import BenchmarkItem, ItemValidation
    from db.session import get_engine

    with Session(get_engine()) as session:
        rows = session.exec(select(ItemValidation)).all()
        id_by_uuid = {i.id: i for i in session.exec(select(BenchmarkItem)).all()}
        out = []
        for r in rows:
            item = id_by_uuid.get(r.item_id)
            if item is None:
                continue
            out.append({
                "item_id": item.prompt[:0] or _string_id_for(item),
                "validator_id": r.validator_id,
                "cultural_score": r.cultural_score,
                "factual_accuracy": r.factual_accuracy,
                "item_content_hash": r.item_content_hash,
            })
        return out


def _string_id_for(item) -> str:
    """BenchmarkItem stores a uuid; pack files key on the string id. Match on content."""
    for path in _PACKS_DIR.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("prompt") == item.prompt:
                return d["id"]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Write validation_count / irr_score into the pack files.")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default).")
    args = parser.parse_args()

    items, path_of = [], {}
    for path in sorted(_PACKS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                items.append(d)
                path_of[d["id"]] = path

    results = compute_item_results(_load_validations(), items)
    tier1 = sum(1 for r in results.values()
                if r["validation_count"] >= 2 and (r["irr_score"] or 0) >= IRR_FLOOR)
    adj = [i for i, r in results.items() if r["needs_adjudication"]]
    print(f"Items: {len(items)} | Tier 1 eligible: {tier1} | needing adjudication: {len(adj)}")
    for item_id in adj[:20]:
        print(f"   {item_id}: {results[item_id]['reason']}")

    if not args.apply:
        print("\nReport only. Pass --apply to write validation_count / irr_score into the packs.")
        return

    by_path: dict[Path, list[dict]] = defaultdict(list)
    for d in items:
        r = results.get(d["id"], {})
        if r.get("validation_count"):
            d["validation_count"] = r["validation_count"]
            d["irr_score"] = r["irr_score"]
        by_path[path_of[d["id"]]].append(d)

    for path, rows in by_path.items():
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    print(f"\nUpdated {len(by_path)} pack file(s). Review with `git diff` before committing.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_writeback.py -v`
Expected: 6 passed.

- [ ] **Step 5: Raise the IRR floor to 0.70**

In `scripts/import_authored_items.py:51`, change `_IRR_FLOOR = 0.60` to:

```python
from validation.irr import IRR_FLOOR as _IRR_FLOOR  # 0.70 — single source of truth (v1.4)
```

Place the import with the other project imports at the top of the file and delete the old
constant assignment, so the floor is defined in exactly one place.

- [ ] **Step 6: Carry validation fields into the DB**

In `scripts/seed_packs_to_db.py`, in the `BenchmarkItem(...)` construction (~line 90-101),
add these two fields so the DB stops silently disagreeing with the packs:

```python
                    validation_count=item.get("validation_count", 0),
                    irr_score=item.get("irr_score"),
```

- [ ] **Step 7: Update the schema doc**

In `docs/BENCHMARK_ITEM_SCHEMA.md`, replace the `irr_score` row's description with:

```
Inter-rater reliability for the PAIR who validated this item, measured across their whole
shared batch — quadratic-weighted Cohen's kappa on cultural_score (1-5). It is a property of
the rating process, not of the item. `null` when validation_count < 2, or when the pair share
fewer than 10 items. Never estimated or backfilled. Items below **0.70** go to adjudication.
```

And change the Tier 1 requirement from `irr_score >= 0.60` to `irr_score >= 0.70`.

- [ ] **Step 8: Verify the floor is consistent everywhere**

Run: `grep -rn "0\.60\|0\.6 " --include=*.py --include=*.md scripts/ validation/ docs/BENCHMARK_ITEM_SCHEMA.md docs/CULTURAL_RUBRIC_V1.md`
Expected: no hit that refers to the IRR floor. Any remaining `0.60` must be an unrelated number; check each.

- [ ] **Step 9: Run the full suite and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q` and `.\.venv\Scripts\python.exe -m ruff check .`

```bash
git add scripts/validation_writeback.py tests/test_validation_writeback.py \
        scripts/seed_packs_to_db.py scripts/import_authored_items.py \
        docs/BENCHMARK_ITEM_SCHEMA.md
git commit -m "feat(validation): IRR writeback, adjudication flags, floor raised to 0.70

Computes kappa per pair per batch and stamps validation_count / irr_score onto
the pack files, which are the source of truth. Only those fields are written -
item content is never touched.

Adjudication fires on a factual-accuracy dispute regardless of kappa: two
validators disagreeing on whether an item is CORRECT is a defect, not noise to
be averaged. It also fires below the 0.70 floor or on a cultural gap over one
rubric point.

Stale validations (content hash no longer matches the item) are dropped before
counting, and one person rating twice counts once.

Fixes seed_packs_to_db.py, which dropped validation_count and irr_score on seed
and left both DB columns structurally dead."
```

---

### Task 7: Adjudication queue

**Files:**
- Create: `scripts/validation_adjudicate.py`
- Modify: `hitl/label_config.py`

**Interfaces:**
- Consumes: `scripts.validation_writeback.compute_item_results`, `validation.assignment.assign_validators`.
- Produces: `hitl.label_config.build_adjudication_label_config() -> str`, `ADJUDICATION_PROJECT_TITLE`.

- [ ] **Step 1: Add the adjudication config**

At the end of `hitl/label_config.py`:

```python
ADJUDICATION_PROJECT_TITLE = "AfroEval — Item Adjudication"


def build_adjudication_label_config() -> str:
    """
    Third-rater adjudication for items where the original pair disagreed.

    The adjudicator sees BOTH original ratings and their justifications — unlike the
    validators, who rate blind. The decision is theirs to make on the record, so the
    rationale field is required.
    """
    return f"""
<View>
  <Header value="Adjudicate — the two validators disagreed"/>
  <Text name="reason" value="$reason"/>
  <Header value="Prompt"/>
  <Text name="prompt" value="$prompt"/>
  <Header value="Expected behaviour"/>
  <Text name="expected_behavior" value="$expected_behavior"/>
  <Header value="Validator A"/>
  <Text name="rating_a" value="$rating_a"/>
  <Header value="Validator B"/>
  <Text name="rating_b" value="$rating_b"/>

  <Header value="Adjudicated cultural score (1-5)"/>
  {_choices("adjudicated_cultural_score", ["1", "2", "3", "4", "5"])}
  <Header value="Adjudicated factual accuracy"/>
  {_choices("adjudicated_factual_accuracy", ["yes", "no", "needs_revision"])}
  <Header value="Outcome"/>
  {_choices("adjudicated_verdict", ["publish", "revise", "reject"])}
  <Header value="Rationale (required — this is the record of the decision)"/>
  <TextArea name="adjudication_rationale" toName="prompt" rows="4" maxSubmissions="1"/>
</View>
""".strip()
```

- [ ] **Step 2: Write the adjudication export**

Create `scripts/validation_adjudicate.py`:

```python
"""
Push items whose validators disagreed into the adjudication project.

Triggered by scripts/validation_writeback.py flagging needs_adjudication: a factual-accuracy
dispute, a pair kappa below the 0.70 floor, or cultural scores more than one rubric point
apart.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/validation_adjudicate.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hitl.client import LabelStudioClient
from hitl.label_config import ADJUDICATION_PROJECT_TITLE, build_adjudication_label_config
from scripts.validation_writeback import _load_validations, compute_item_results

_PACKS_DIR = Path(__file__).parent.parent / "benchmarks" / "packs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-title", default=ADJUDICATION_PROJECT_TITLE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    items = []
    for path in sorted(_PACKS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
    by_id = {i["id"]: i for i in items}

    validations = _load_validations()
    results = compute_item_results(validations, items)
    flagged = {i: r for i, r in results.items() if r["needs_adjudication"]}

    ratings_by_item: dict[str, list[dict]] = {}
    for v in validations:
        ratings_by_item.setdefault(v["item_id"], []).append(v)

    tasks = []
    for item_id, r in flagged.items():
        pair = sorted(ratings_by_item.get(item_id, []), key=lambda x: x["validator_id"])
        if len(pair) != 2:
            continue
        item = by_id[item_id]
        tasks.append({
            "item_id": item_id,
            "prompt": item["prompt"],
            "expected_behavior": item["expected_behavior"],
            "reason": r["reason"],
            "rating_a": (f"{pair[0]['validator_id']}: cultural "
                         f"{pair[0]['cultural_score']}, factual "
                         f"{pair[0]['factual_accuracy']}"),
            "rating_b": (f"{pair[1]['validator_id']}: cultural "
                         f"{pair[1]['cultural_score']}, factual "
                         f"{pair[1]['factual_accuracy']}"),
        })

    print(f"Items needing adjudication: {len(tasks)}")
    for t in tasks[:20]:
        print(f"   {t['item_id']}: {t['reason']}")

    if args.dry_run or not tasks:
        print("\n--dry-run or nothing to send: Label Studio untouched.")
        return

    client = LabelStudioClient()
    project = client.get_or_create_project(args.project_title,
                                           build_adjudication_label_config())
    result = client.import_tasks(project["id"], tasks)
    print(f"\nProject '{args.project_title}' (id={project['id']}): {result}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the dry run**

Run: `.\.venv\Scripts\python.exe scripts/validation_adjudicate.py --dry-run`
Expected: `Items needing adjudication: 0` (no validations exist yet) and a clean exit.

- [ ] **Step 4: Run the full suite and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q` and `.\.venv\Scripts\python.exe -m ruff check .`

```bash
git add hitl/label_config.py scripts/validation_adjudicate.py
git commit -m "feat(validation): adjudication queue for disagreeing validator pairs

A third rater sees BOTH original ratings and their justifications - unlike the
validators, who rate blind - and records a rationale, because the decision
becomes part of the item's provenance.

Fires on a factual dispute, a pair kappa below 0.70, or cultural scores more
than one rubric point apart."
```

---

## Self-Review Notes

**Spec coverage.** Gap 1 → Task 1 (`item_validations` + unique constraint + content hash).
Gap 2 → Task 4 Step 1 (`build_validation_label_config` implementing the four-part instrument).
Gap 3 → Tasks 3, 4, 5 (assignment with author exclusion, export, import).
Gap 4 → Task 2 (`validation/irr.py`, per pair per batch, quadratic-weighted, 0.70 floor,
10-item minimum). Gap 5 → Task 6 (writeback to pack JSONL + `seed_packs_to_db.py` fix).
Gap 7 → Task 7 (adjudication queue with `adjudicated_*` fields and required rationale).
Gaps 6, 8, 9 are explicitly out of scope, in the Scope section, with the reason for each.

**D1 (0.70 floor)** — Task 6 Steps 5, 7, 8 change the code constant, the schema doc, and
verify no stale 0.60 survives. **D2 (per-pair-per-batch)** — Task 2's `pair_kappa` plus Task
6's pair grouping; documented in the schema doc at Task 6 Step 7. **D3 (quadratic on
cultural, factual as a hard gate)** — Task 2's `weights="quadratic"` and Task 6's
`test_factual_disagreement_forces_adjudication_regardless_of_kappa`. **D4 (JSONL is truth,
fix the seeder)** — Task 6 Steps 3 and 6. **D5 (content hash)** — Task 1, enforced in Task 6's
`test_stale_validation_does_not_count`.

**Type consistency.** `item_content_hash(prompt, expected_behavior) -> str` is defined in
Task 1 and used in Tasks 4 and 6. `pair_kappa(a, b) -> float | None` and `batch_key(a, b) ->
str` are defined in Task 2 and used in Tasks 4 and 6. `assign_validators(item, roster,
existing=None) -> list[str]` is defined in Task 3 and used in Task 4.
`compute_item_results(validations, items) -> dict[str, dict]` is defined in Task 6 and used
in Task 7. `ItemValidation` is defined in Task 1 and used in Tasks 5 and 6.

**Known weakness to watch in review.** `_string_id_for` in Task 6 maps a `BenchmarkItem`
back to its pack string id by matching on `prompt`, because the DB stores only the uuid.
This is O(items × packs) and breaks if two items share a prompt. It is acceptable at 147
items but is the first thing to replace if the corpus grows — the clean fix is storing the
string id on `BenchmarkItem`, which is a schema change and out of scope here. Flag it to the
reviewer rather than letting them discover it.

**Operational note, not a task.** The placeholder `validator_roster.json` will make most
items unassignable until real validator ids and languages are filled in. That is correct
behaviour — a language with one contracted SME genuinely cannot produce a Tier 1 item — and
the export reports it explicitly rather than silently exporting to a single person.
