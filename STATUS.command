#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}";cd "$ROOT";PORT="${ARBITER_BIOLOGY_PORT:-8799}";PYTHON="${ARBITER_PYTHON:-$(command -v python3)}"
echo "ARBITER BIOLOGY FIELD STATUS"
echo "────────────────────────────────────────────────────────"
if [[ -s logs/server.pid ]]; then PID="$(cat logs/server.pid)";ps -p "$PID" -o pid=,etime=,command= || true;else echo "server pid: none";fi
curl -fsS "http://127.0.0.1:$PORT/field/v1/health" | "$PYTHON" -m json.tool || true
[[ -s field/manifest.json ]] && "$PYTHON" - <<'PY'
import json
m=json.load(open('field/manifest.json'))
print('objects: {:,}'.format(int(m.get('count',0))))
print('dimensions:',m.get('dimension'))
print('version:',m.get('version'))
print('domains:',m.get('domains'))
PY
