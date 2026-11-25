"""/contracts must match the Pydantic models. Fix with: uv run hark-contracts"""

from __future__ import annotations

from hark_engine.contracts import default_contracts_dir, render_all


def test_contracts_in_sync():
    target = default_contracts_dir()
    for filename, expected in render_all().items():
        path = target / filename
        assert path.exists(), f"missing {path}; run `uv run hark-contracts`"
        assert path.read_text(encoding="utf-8") == expected, (
            f"{filename} out of date; run `uv run hark-contracts`"
        )
