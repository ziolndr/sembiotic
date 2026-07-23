#!/bin/zsh
set -euo pipefail

export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export OMP_NUM_THREADS=1

ROOT="${0:A:h}"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

exec "$PYTHON" \
  "$ROOT/scripts/serve_field_fast.py" \
  --root "$ROOT" \
  --embed-url "http://127.0.0.1:8000/v1/embed" \
  --host 127.0.0.1 \
  --port 8799
