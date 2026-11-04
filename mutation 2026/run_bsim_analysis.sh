#!/usr/bin/env bash
# Regenerate BSim clustering results for the Mutation 2026 paper.
#
# Usage (from this folder):
#   ./run_bsim_analysis.sh
#   ./run_bsim_analysis.sh triangle-example jra
#   ./run_bsim_analysis.sh --clear-cache --verbose triangle-example
#
# Windows: use Git Bash or WSL from this directory:
#   bash run_bsim_analysis.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/logs"
RESULTS_DIR="$ROOT/results"
mkdir -p "$LOG_DIR" "$RESULTS_DIR"
LOG_FILE="$LOG_DIR/bsim_analysis.log"

VERBOSE=false
NO_CACHE=false
CLEAR_CACHE=false
SKIP_DOWNLOAD=false
PROJECTS=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [options] [project ...]

Run BSim clustering analysis for Mutation 2026 paper projects.

Options:
  --verbose       Print per-HOM details during analysis
  --no-cache      Recompute every HOM (ignore cache)
  --clear-cache   Delete HOM cache before running
  --skip-download Skip Google Drive database download
  -h, --help      Show this help and exit

Examples:
  $(basename "$0")
  $(basename "$0") triangle-example
  $(basename "$0") --clear-cache --no-cache --verbose triangle-example jra

Projects default to all entries in projects.json when none are given.
EOF
}

add_project() {
  local name="${1// /}"
  [[ -n "$name" ]] || return 0
  PROJECTS+=("$name")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verbose) VERBOSE=true; shift ;;
    --no-cache) NO_CACHE=true; shift ;;
    --clear-cache) CLEAR_CACHE=true; shift ;;
    --skip-download) SKIP_DOWNLOAD=true; shift ;;
    -h|--help) usage; exit 0 ;;
    --projects)
      shift
      if [[ $# -eq 0 ]]; then
        echo "error: --projects requires at least one project name" >&2
        exit 1
      fi
      while [[ $# -gt 0 && "$1" != --* ]]; do
        IFS=',' read -ra names <<< "$1"
        for name in "${names[@]}"; do
          add_project "$name"
        done
        shift
      done
      ;;
    --*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      IFS=',' read -ra names <<< "$1"
      for name in "${names[@]}"; do
        add_project "$name"
      done
      shift
      ;;
  esac
done

# UTF-8 Python I/O (Linux/macOS/Windows Git Bash)
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

find_python() {
  local candidate
  for candidate in "$@"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  case "${OSTYPE:-}" in
    msys*|mingw*|cygwin*)
      # Git Bash / MSYS: prefer Windows Python on PATH over WSL-style python3.
      PYTHON="$(find_python python py python3 || true)"
      ;;
    *)
      PYTHON="$(find_python python3 python || true)"
      ;;
  esac
fi
if [[ -z "$PYTHON" ]]; then
  echo "error: Python not found on PATH (set PYTHON=/path/to/python or install python3)" >&2
  exit 1
fi

if ! "$PYTHON" -c "import community, scipy, networkx, matplotlib, numpy, tqdm, gdown" 2>/dev/null; then
  echo "Installing Python dependencies with $PYTHON ..."
  if ! "$PYTHON" -m pip install -r "$ROOT/requirements.txt"; then
    cat >&2 <<EOF
error: failed to install requirements.txt with $PYTHON

Try one of:
  pip install -r requirements.txt
  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  PYTHON=/path/to/python $0 "$@"
EOF
    exit 1
  fi
fi

if ! $SKIP_DOWNLOAD; then
  DOWNLOAD_ARGS=("$ROOT/download_databases.py")
  if ((${#PROJECTS[@]})); then
    DOWNLOAD_ARGS+=(--projects "${PROJECTS[@]}")
  fi
  "$PYTHON" "${DOWNLOAD_ARGS[@]}"
fi

RUNNER_ARGS=(
  "$ROOT/run_all_projects.py"
  --output-dir "$RESULTS_DIR"
  --log-file "$LOG_FILE"
)
if ((${#PROJECTS[@]})); then
  RUNNER_ARGS+=(--projects "${PROJECTS[@]}")
fi
if $NO_CACHE; then
  RUNNER_ARGS+=(--no-cache)
fi
if $CLEAR_CACHE; then
  RUNNER_ARGS+=(--clear-cache)
fi
if $VERBOSE; then
  RUNNER_ARGS+=(--verbose)
fi

# Python writes the log file; console keeps live tqdm bars when attached to a TTY.
"$PYTHON" "${RUNNER_ARGS[@]}"
exit_code=$?
if ((exit_code != 0)); then
  echo "error: analysis pipeline failed (exit $exit_code)" >&2
  exit "$exit_code"
fi

echo ""
echo "Done. Results in $RESULTS_DIR"
echo "Log file: $LOG_FILE"
