#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}";cd "$ROOT"
PYTHON="${ARBITER_PYTHON:-$(command -v python3)}";EMBED_URL="${ARBITER_EMBED_URL:-http://127.0.0.1:8000/v1/embed}"
"$PYTHON" scripts/build_field.py --corpus corpus --field field --embed-url "$EMBED_URL" --fresh
"$ROOT/START_FIELD.command"
