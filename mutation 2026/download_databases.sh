#!/usr/bin/env bash
# Download Mutation 2026 SQLite databases from Google Drive.
# Usage:
#   ./download_databases.sh
#   ./download_databases.sh triangle-example jra
#   ./download_databases.sh --force

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON=python
  fi
fi
if [[ -z "$PYTHON" ]]; then
  echo "error: Python not found on PATH" >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/download_databases.py" "$@"
