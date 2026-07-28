import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import dry_run_pipeline as drp  # noqa: E402


def test_dry_run_clears_floor_and_flags_dispute(tmp_path):
    result = drp.run(tmp_path)
    assert result["scored"] >= 10           # promoted past the floor
    assert result["tier1"] >= 10            # the agreeing pair reached Tier 1
    assert result["adjudicate"]             # the seeded factual dispute was caught
