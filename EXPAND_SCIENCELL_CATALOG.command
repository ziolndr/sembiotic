#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}";cd "$ROOT"
PYTHON="${ARBITER_PYTHON:-$(command -v python3)}";EMBED_URL="${ARBITER_EMBED_URL:-http://127.0.0.1:8000/v1/embed}"
MAX_PAGES="${SCIEN_CELL_MAX_PAGES:-2000}"
"$PYTHON" scripts/ingest_sciencell.py --output corpus/sciencell_public.jsonl --max-pages "$MAX_PAGES"
"$PYTHON" scripts/build_field.py --corpus corpus --field field --embed-url "$EMBED_URL" --fresh
"$ROOT/START_FIELD.command"
