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
EMBED_URL="${ARBITER_EMBED_URL:-http://127.0.0.1:8000/v1/embed}";PORT="${ARBITER_BIOLOGY_PORT:-8799}"
mkdir -p logs
if [[ -s logs/server.pid ]]; then OLD="$(cat logs/server.pid 2>/dev/null || true)";[[ -n "$OLD" ]] && kill "$OLD" 2>/dev/null || true;fi
nohup "$PYTHON" -u scripts/serve_field.py --host 127.0.0.1 --port "$PORT" --field field --public public --embed-url "$EMBED_URL" > logs/server.log 2>&1 &
echo $! > logs/server.pid
for i in {1..40}; do curl -fsS "http://127.0.0.1:$PORT/field/v1/health" >/dev/null 2>&1 && break;sleep .25;done
open "http://127.0.0.1:$PORT/"
echo "ARBITER Biology field started · http://127.0.0.1:$PORT"
