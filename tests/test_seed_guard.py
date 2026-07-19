"""
Guard tests for scripts/seed_benchmarks.py.

This script is a Week 3 bootstrap tool whose hardcoded lists share filenames with the live
SME-validated packs but hold far fewer items. Before 2026-07-19 it opened every pack file in
"w" mode unconditionally: running it would have replaced 66 live items with 21 seeds,
destroying 45 SME-authored items, in violation of the project rule that
benchmarks/packs/*.jsonl is never rewritten by an automated tool.

These tests lock the guard in place. If someone removes the existence check, they fail.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "seed_benchmarks.py"


def _load(pack_dir: Path):
    """Fresh module instance with PACKS_DIR redirected at a sandbox."""
    spec = importlib.util.spec_from_file_location("seed_benchmarks_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.PACKS_DIR = pack_dir
    return mod


def _write_pack(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"id": f"live-{i}", "prompt": "x"}) + "\n" for i in range(n)),
        encoding="utf-8",
    )


def _run(mod, argv):
    sys.argv = ["seed_benchmarks.py", *argv]
    mod.main()


def test_refuses_to_overwrite_an_existing_pack(tmp_path, capsys):
    """The core guard: a live pack must survive a bare run untouched."""
    packs = tmp_path / "packs"
    live = packs / "mobile_money_sw_v1.0.0.jsonl"
    _write_pack(live, 11)
    before = live.read_bytes()

    _run(_load(packs), [])

    assert live.read_bytes() == before, "live pack was modified by a bare run"
    out = capsys.readouterr().out
    assert "REFUSING to overwrite" in out


def test_reports_the_item_loss_before_refusing(tmp_path, capsys):
    """The operator must see what would be destroyed, not just that it stopped."""
    packs = tmp_path / "packs"
    _write_pack(packs / "mobile_money_sw_v1.0.0.jsonl", 11)

    _run(_load(packs), [])

    out = capsys.readouterr().out
    assert "would destroy" in out
    assert "11" in out  # the live count is surfaced


def test_writes_packs_that_do_not_exist_yet(tmp_path):
    """Bootstrapping an empty checkout must still work — the guard is not a blanket block."""
    packs = tmp_path / "packs"
    packs.mkdir(parents=True)

    _run(_load(packs), [])

    written = list(packs.glob("*.jsonl"))
    assert len(written) == 6, f"expected all 6 seed packs, got {len(written)}"


def test_force_overwrites_only_when_explicitly_asked(tmp_path):
    """--force must still work; it is an escape hatch, not a removed feature."""
    packs = tmp_path / "packs"
    live = packs / "mobile_money_sw_v1.0.0.jsonl"
    _write_pack(live, 11)

    _run(_load(packs), ["--force"])

    n = sum(1 for line in live.read_text(encoding="utf-8").splitlines() if line.strip())
    assert n == 6, "with --force the seed content should replace the live pack"


def test_dry_run_writes_nothing(tmp_path):
    packs = tmp_path / "packs"
    packs.mkdir(parents=True)

    _run(_load(packs), ["--dry-run"])

    assert list(packs.glob("*.jsonl")) == []


@pytest.mark.parametrize("pack_file", [p.name for p in
                                       (Path(__file__).parent.parent / "benchmarks" / "packs").glob("*.jsonl")])
def test_real_packs_are_never_smaller_than_their_seed_equivalent(pack_file):
    """
    Canary on the real corpus: if a live pack ever shrinks to seed size, someone ran the
    bootstrap with --force against production data.
    """
    packs_dir = Path(__file__).parent.parent / "benchmarks" / "packs"
    mod = _load(packs_dir)
    seeds = {p["filename"]: len(p["items"]) for p in mod.SEED_PACKS}
    if pack_file not in seeds:
        pytest.skip(f"{pack_file} is not produced by the bootstrap script")
    live = sum(1 for line in (packs_dir / pack_file).read_text(encoding="utf-8").splitlines()
               if line.strip())
    assert live > seeds[pack_file], (
        f"{pack_file} has {live} items, the bootstrap seed count is {seeds[pack_file]} — "
        "this pack may have been overwritten by scripts/seed_benchmarks.py --force"
    )
