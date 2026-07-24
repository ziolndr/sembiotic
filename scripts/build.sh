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
  'sembiotic-editorial-refactor-v1' \
  "$OUTPUT" || {
    echo "Editorial frontend marker is missing." >&2
    exit 1
  }

grep -Fq \
  'sembiotic-editorial-runtime-v1' \
  "$OUTPUT" || {
    echo "Editorial runtime marker is missing." >&2
    exit 1
  }

echo "SEMBIOTIC FRONTEND BUILD"
echo "editorial source → public/index.html · PASS"
