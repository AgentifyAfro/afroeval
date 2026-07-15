"""
Benchmark loader tests — contamination controls.

Held-out and gold items must never reach a scoring run unless explicitly
requested. Gold items are calibration anchors ("never scored") — the loader
is the enforcement point (Methodology v1.1).

These tests use a temp pack fixture (tmp_path) and never touch the real
SME-authored packs in benchmarks/packs/ (read-only per CLAUDE.md).
"""

import json

import pytest

from benchmarks import loader

BASE = {"prompt": "p", "expected_behavior": "e", "language": "sw", "domain": "d"}


def _write_pack(dir_path, items):
    f = dir_path / "testpack_v1.0.0.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it) + "\n")
    return dir_path


def test_load_pack_excludes_gold_by_default(tmp_path, monkeypatch):
    packs = _write_pack(tmp_path, [
        {**BASE, "id": "normal"},
        {**BASE, "id": "goldie", "is_gold": True},
    ])
    monkeypatch.setattr(loader, "PACKS_DIR", packs)
    items = loader.load_pack("testpack", "v1.0.0")
    ids = [it.get("id") for it in items]
    assert "normal" in ids
    assert "goldie" not in ids, "gold items must be excluded from scoring by default"


def test_load_pack_includes_gold_when_requested(tmp_path, monkeypatch):
    packs = _write_pack(tmp_path, [
        {**BASE, "id": "normal"},
        {**BASE, "id": "goldie", "is_gold": True},
    ])
    monkeypatch.setattr(loader, "PACKS_DIR", packs)
    items = loader.load_pack("testpack", "v1.0.0", include_gold=True)
    ids = [it.get("id") for it in items]
    assert "normal" in ids
    assert "goldie" in ids, "include_gold=True must return gold items (calibration path)"


def test_load_pack_gold_and_held_out_filters_are_independent(tmp_path, monkeypatch):
    packs = _write_pack(tmp_path, [
        {**BASE, "id": "normal"},
        {**BASE, "id": "goldie", "is_gold": True},
        {**BASE, "id": "heldout", "is_held_out": True},
    ])
    monkeypatch.setattr(loader, "PACKS_DIR", packs)
    # Default: both gold and held-out excluded.
    ids = [it.get("id") for it in loader.load_pack("testpack", "v1.0.0")]
    assert ids == ["normal"]
    # include_gold alone must NOT also let held-out through.
    ids_gold = [it.get("id") for it in loader.load_pack("testpack", "v1.0.0", include_gold=True)]
    assert "heldout" not in ids_gold
    assert set(ids_gold) == {"normal", "goldie"}
