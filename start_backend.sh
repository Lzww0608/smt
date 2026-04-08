#!/usr/bin/env bash
set -euo pipefail

BIND_HOST="${1:-127.0.0.1}"
PORT="${2:-8000}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: $PYTHON_BIN not found in PATH." >&2
  exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
MAJOR="${PYTHON_VERSION%%.*}"
MINOR="${PYTHON_VERSION##*.}"

if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
  echo "Error: Python 3.10+ is required. Current version: $PYTHON_VERSION" >&2
  exit 1
fi

"$PYTHON_BIN" -m uvicorn app.main:app --host "$BIND_HOST" --port "$PORT" --reload
