#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SOURCE="$ROOT/public/index.base.html"
OUTPUT="$ROOT/public/index.html"

[ -s "$SOURCE" ] || {
  echo "Missing frontend source: $SOURCE" >&2
  exit 1
}

cp "$SOURCE" "$OUTPUT"

grep -Fq \
  'sembiotic-brutalist-apple-v1' \
  "$OUTPUT" || {
    echo "Frontend marker missing." >&2
    exit 1
  }

grep -Fq \
  'sembiotic-brutalist-runtime-v1' \
  "$OUTPUT" || {
    echo "Runtime marker missing." >&2
    exit 1
  }

echo "SEMBIOTIC FRONTEND BUILD · PASS"
