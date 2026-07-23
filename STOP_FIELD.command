#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}";cd "$ROOT"
if [[ -s logs/server.pid ]]; then
  PID="$(cat logs/server.pid)";kill "$PID" 2>/dev/null || true;rm -f logs/server.pid;echo "Stopped ARBITER Biology field · PID $PID"
else
  echo "No recorded ARBITER Biology field process."
fi
