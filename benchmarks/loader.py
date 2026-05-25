"""
Benchmark pack loader — versioned, contamination-safe.

Rules:
  - Packs are loaded by name + version; never by path glob.
  - Held-out splits are filtered out and never returned to callers.
  - Every item carries its provenance and language metadata.
"""

import json
from pathlib import Path

PACKS_DIR = Path(__file__).parent / "packs"


def load_pack(name: str, version: str, include_held_out: bool = False) -> list[dict]:
    """
    Load benchmark items from a versioned JSONL pack file.

    Args:
        name: Pack name (e.g. "mobile_money_sw")
        version: Version string (e.g. "v1.0.0")
        include_held_out: Must be explicitly True to load held-out splits.
                          Default False enforces contamination control.

    Returns list of item dicts, each with: prompt, expected_behavior,
    language, domain, cohort, provenance, is_gold, tags.
    """
    filename = f"{name}_{version}.jsonl"
    pack_path = PACKS_DIR / filename

    if not pack_path.exists():
        raise FileNotFoundError(
            f"Benchmark pack not found: {pack_path}. "
            "Check the pack name and version, or run scripts/seed_benchmarks.py."
        )

    items = []
    with pack_path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num} of {filename}: {e}") from e

            if item.get("is_held_out") and not include_held_out:
                continue

            _validate_item(item, line_num, filename)
            items.append(item)

    return items


def list_available_packs() -> list[dict]:
    """Return metadata for all available (non-held-out) packs."""
    packs = []
    for path in sorted(PACKS_DIR.glob("*.jsonl")):
        if "_held_out" in path.name:
            continue
        packs.append({"filename": path.name, "size_bytes": path.stat().st_size})
    return packs


def _validate_item(item: dict, line_num: int, filename: str) -> None:
    required = {"prompt", "expected_behavior", "language", "domain"}
    missing = required - set(item.keys())
    if missing:
        raise ValueError(
            f"Benchmark item on line {line_num} of {filename} "
            f"is missing required fields: {missing}"
        )
