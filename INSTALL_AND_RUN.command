#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}"
cd "$ROOT"
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
PORT="${ARBITER_BIOLOGY_PORT:-8799}"
mkdir -p logs field corpus

echo "ARBITER BIOLOGY — LOCAL 72D FIELD"
echo "────────────────────────────────────────────────────────"
echo "package: $ROOT"
echo "python:  $PYTHON"
echo "embed:   $EMBED_URL"
echo "field:   http://127.0.0.1:$PORT"
echo

"$PYTHON" - <<PY
import sys
try:
 import numpy
 print('NumPy:   PASS · '+numpy.__version__)
except Exception as exc:
 print('NumPy:   FAIL · '+repr(exc))
 sys.exit(1)
PY

if [[ ! -s corpus/structured_seed.jsonl ]]; then
  "$PYTHON" scripts/generate_corpus.py --output corpus/structured_seed.jsonl --count 12000
fi

"$PYTHON" - <<PY
import sys
sys.path.insert(0,'scripts')
from embed_client import embed_texts
rows=embed_texts('$EMBED_URL',['ARBITER biology local field readiness probe'],30)
print('ARBITER embed: PASS · {}D'.format(len(rows[0])))
if len(rows[0]) != 72:
 print('WARNING: expected 72 dimensions, received {}'.format(len(rows[0])))
PY

if [[ ! -s field/manifest.json || "${ARBITER_REBUILD:-0}" == "1" ]]; then
  echo
  echo "Embedding the biological corpus once..."
  "$PYTHON" scripts/build_field.py --corpus corpus --field field --embed-url "$EMBED_URL"
else
  "$PYTHON" - <<'PY'
import json
m=json.load(open('field/manifest.json'))
print('Existing field: {:,} objects · {}D · {}'.format(int(m.get('count',0)),m.get('dimension'),m.get('version')))
PY
fi

if [[ -s logs/server.pid ]]; then
  OLD="$(cat logs/server.pid 2>/dev/null || true)"
  [[ -n "$OLD" ]] && kill "$OLD" 2>/dev/null || true
fi
nohup "$PYTHON" -u scripts/serve_field.py --host 127.0.0.1 --port "$PORT" --field field --public public --embed-url "$EMBED_URL" > logs/server.log 2>&1 &
echo $! > logs/server.pid

for i in {1..60}; do
  if curl -fsS "http://127.0.0.1:$PORT/field/v1/health" >/tmp/arbiter-biology-health.json 2>/dev/null; then break; fi
  sleep .25
done
curl -fsS "http://127.0.0.1:$PORT/field/v1/manifest" | "$PYTHON" -m json.tool
open "http://127.0.0.1:$PORT/"
echo
echo "ARBITER BIOLOGY FIELD LIVE"
echo "Log: $ROOT/logs/server.log"
