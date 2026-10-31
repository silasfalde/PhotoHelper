#!/usr/bin/env bash
# Recreate the repository .venv. Usage: rebuild-venv.sh [python-executable]
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${1:-python3}"

if ! "$PYTHON" -c 'import ensurepip, venv' 2>/dev/null; then
    printf 'Error: %s cannot create virtual environments (ensurepip/venv missing).\n' "$PYTHON" >&2
    printf 'Install the matching venv package (e.g. sudo apt install python3-venv)\n' >&2
    printf 'or pass another interpreter: %s /usr/bin/python3.12\n' "$0" >&2
    exit 1
fi

rm -rf -- "$ROOT/.venv"
"$PYTHON" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt" -e "$ROOT"
printf 'Rebuilt %s/.venv with %s\n' "$ROOT" "$("$ROOT/.venv/bin/python" --version)"
