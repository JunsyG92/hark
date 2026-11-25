"""Export the shared model as JSON Schema files into /contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .models import CONTRACT_MODELS

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def render_all() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, (model, mode) in CONTRACT_MODELS.items():
        schema = model.model_json_schema(mode=mode)
        schema = {"$schema": SCHEMA_DRAFT, "$id": f"hark://contracts/{name}.json", **schema}
        out[f"{name}.schema.json"] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    out["openapi.json"] = json.dumps(_openapi(), indent=2, ensure_ascii=False) + "\n"
    return out


def _openapi() -> dict[str, object]:
    from .api import create_app
    from .store import Database

    db = Database(":memory:")
    try:
        return create_app(db, master_token="unused").openapi()  # noqa: S106
    finally:
        db.close()


def default_contracts_dir() -> Path:
    # engine/src/hark_engine/contracts.py -> repo root /contracts
    return Path(__file__).resolve().parents[3] / "contracts"


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default_contracts_dir()
    target.mkdir(parents=True, exist_ok=True)
    for filename, content in render_all().items():
        (target / filename).write_text(content, encoding="utf-8")
        print(f"wrote {target / filename}")
