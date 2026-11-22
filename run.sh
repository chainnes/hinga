#!/usr/bin/env bash
# One command for the demo, and the same command with "test" for the suite.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  "$PY" -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -e ".[dev]"
fi

if [[ "${1:-}" == "test" ]]; then
  exec .venv/bin/pytest -q
fi

mkdir -p data
exec .venv/bin/python -m hinga
