# Contributing to AfroEval — Module Contract

**Read this before writing any code.**

## The One Rule

Every capability in AfroEval must follow the module contract:

> A module contributes a **benchmark pack**, a set of **evaluators**, and a **report section**.
> It consumes shared ingestion, orchestration, scoring, and reporting services.
> **Nothing reaches into another module's internals.**

This contract is what makes Phase 2 modules additive instead of rewrites.

## Module structure

Each module (`evaluators/`, `ail/`, `scoring/`, etc.) must:

1. Expose a public API via its `__init__.py` only.
2. Accept inputs and return outputs using the types defined in `db/models.py` and the base classes.
3. Never import from a sibling module's internal files directly.
4. Never write to the database directly — use the session passed by the orchestrator.

## Evaluator contract

All evaluators extend `evaluators.base.BaseEvaluator`:

```python
class MyEvaluator(BaseEvaluator):
    @property
    def dimension(self) -> str: ...       # one of the six AfroEval dimensions

    @property
    def metric_name(self) -> str: ...     # unique within the dimension

    def evaluate(self, prompt, model_response, expected_behavior, context) -> MetricOutput: ...
```

Register it in the module's `__init__.py` registry. The orchestrator reads registries — it never imports evaluators by name.

## Benchmark pack format

Packs are versioned JSONL files in `benchmarks/packs/`. Each line:

```json
{
  "id": "mm-sw-001",
  "prompt": "...",
  "expected_behavior": "...",
  "language": "sw",
  "domain": "mobile_money",
  "cohort": "informal_economy",
  "provenance": "Source description",
  "is_gold": false,
  "is_held_out": false,
  "tags": []
}
```

**Never transmit or publish `is_held_out: true` items.** The loader filters them automatically.

## Testing requirements

- Unit tests for every evaluator, adapter, and scoring function.
- CI runs on every pull request (`ruff check` + `pytest`).
- Any change to the scoring methodology must pass `tests/test_scoring.py` (the regression harness).
- No PR merges to `main` without green CI.

## Documented shortcuts

Some choices in this codebase are deliberate, time-boxed shortcuts:

| Decision | Replacement trigger |
|---|---|
| Streamlit console instead of React | Recurring revenue or multi-tenant need |
| SQLite for test DB | Production always uses PostgreSQL |
| Background tasks instead of Celery | >10 concurrent runs or queue depth |

If you add a new shortcut, document it here with its replacement trigger.
