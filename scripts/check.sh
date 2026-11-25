#!/usr/bin/env bash
# Run every lint + test of the repo. Used locally and in CI.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

echo "== engine (python) =="
cd "$root/engine"
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q

echo "== app (typescript) =="
cd "$root/app"
pnpm lint
pnpm typecheck
pnpm test
echo "All checks passed."
