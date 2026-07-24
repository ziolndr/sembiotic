#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && /bin/pwd)"
test -s "$ROOT/public/index.html"
test -s "$ROOT/public/assets/media_catalog.json"
/usr/bin/grep -Fq '<title>Sembiotic — Search Biology by Meaning</title>' "$ROOT/public/index.html"
/usr/bin/grep -Fq '<div class="brand"><button id="brand">Sembiotic</button></div>' "$ROOT/public/index.html"
/usr/bin/grep -Fq 'id="mediaPanel"' "$ROOT/public/index.html"
/usr/bin/grep -Fq 'id="rail"' "$ROOT/public/index.html"
test -s "$ROOT/api/field/v1/search.js"
test -s "$ROOT/api/field/v1/manifest.js"
test -s "$ROOT/api/field/v1/health.js"
test -s "$ROOT/api/field/v1/media-manifest.js"
echo "Sembiotic actual latest field UI and four field proxies ready"
