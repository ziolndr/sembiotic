#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}";cd "$ROOT"
PYTHON="${ARBITER_PYTHON:-}"
if [[ -n "$PYTHON" ]] && ! "$PYTHON" -c 'import numpy' >/dev/null 2>&1; then PYTHON=""; fi
if [[ -z "$PYTHON" ]]; then
  for candidate in \
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" \
    "$ROOT/venv/bin/python3" \
    "$ROOT/.venv/bin/python3" \
    "$HOME/Downloads/venv/bin/python3" \
    "$HOME/venv/bin/python3" \
    "$(command -v python3 2>/dev/null || true)"
  do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c 'import numpy' >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi
if [[ -z "$PYTHON" ]]; then echo "No NumPy-capable Python installation was found."; exit 1; fi
export ARBITER_PYTHON="$PYTHON"
EMBED_URL="${ARBITER_EMBED_URL:-http://127.0.0.1:8000/v1/embed}"
"$PYTHON" scripts/build_field.py --corpus corpus --field field --embed-url "$EMBED_URL" --fresh
"$ROOT/START_FIELD.command"
