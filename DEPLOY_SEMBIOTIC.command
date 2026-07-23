#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}"
REMOTE="git@github.com:ziolndr/sembiotic.git"
HOSTNAME="sembiotic.actualgeneralintelligence.com"
FIELD_LABEL="com.actualgeneralintelligence.arbiter.biology-field"
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
if [[ -z "$PYTHON" ]]; then print "No NumPy-capable Python installation was found."; exit 1; fi
export ARBITER_PYTHON="$PYTHON"

print "SEMBIOTIC — CLEAN RECORD-MEDIA FIELD DEPLOY"
print "────────────────────────────────────────────────────────"
print "python: $PYTHON"
"$PYTHON" -c 'import numpy; print("numpy:  "+numpy.__version__)'

print "\n1) Validate clean production interface and record-only media"
"$PYTHON" - <<'PY'
from pathlib import Path
html=Path('public/index.html').read_text(encoding='utf-8')
required=[
  '<title>Sembiotic — Search Biology by Meaning</title>',
  'Runs on ARBITER · 26MB · 72D',
  '/field/v1/search','/field/v1/manifest',
  'id="mediaPanel"','id="rail"','id="buckets"','id="openRecord"',
  'Real media only.','No source image attached',
  'const FIELD_BASE=window.ARBITER_BIOLOGY_FIELD_URL||window.location.origin;'
]
missing=[x for x in required if x not in html]
if missing: raise SystemExit('Missing production markers: '+', '.join(missing))
for retired in ('DEFAULT_IMAGE','bg-next','class="bg"','Warhol%27s_Neuron','media_catalog.json','Powered by ARBITER'):
    if retired in html: raise SystemExit('Retired decorative media marker remains: '+retired)
server=Path('scripts/serve_field.py').read_text(encoding='utf-8')
if '_catalog_matches' in server or 'curated real microscopy library' in server:
    raise SystemExit('Generic media fallback remains in server')
if 'source-record images only' not in server:
    raise SystemExit('Record-only media mode missing')
print('HTML structure and source-record-only media policy: PASS')
PY
"$PYTHON" - <<'PY'
from pathlib import Path
s=Path('public/index.html').read_text()
Path('/tmp/sembiotic-clean-field.js').write_text(s.split('<script>',1)[1].split('</script>',1)[0])
PY
if command -v node >/dev/null 2>&1; then node --check /tmp/sembiotic-clean-field.js; print "JavaScript: PASS"; fi
"$PYTHON" -m py_compile scripts/serve_field.py scripts/ingest_sciencell.py scripts/build_field.py
"$PYTHON" - <<'PY'
import importlib.util,sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
spec=importlib.util.spec_from_file_location('serve_field',Path('scripts/serve_field.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=m.MediaResolver(Path('public/assets/media_catalog.json'))
plain=r.hydrate({'id':'a','title':'Human iPSC-derived motor neurons','category':'Cell Model'})
assert plain.get('image_candidates') == [] and not plain.get('image_url'), plain
explicit=r.hydrate({'id':'b','title':'Source imaged neuron','image_url':'https://example.org/neuron.jpg','source_url':'https://example.org/record'})
assert explicit.get('image_url') == 'https://example.org/neuron.jpg' and explicit.get('image_source') == 'record', explicit
print('Record-only media resolver: PASS')
PY

print "\n2) Commit and push to GitHub"
if [[ ! -d .git ]]; then
  git init -b main
  git remote add origin "$REMOTE"
  git fetch origin main >/dev/null 2>&1 || true
else
  git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"
fi
git checkout -B main
git pull --rebase --autostash origin main 2>/dev/null || true
git add -A
if ! git diff --cached --quiet; then git commit -m "Clean Sembiotic layout and require source-record media"; else print "Git working tree already current."; fi
git push -u origin main

print "\n3) Reinstall and restart persistent Sembiotic field"
chmod +x ./*.command
./INSTALL_AUTOSTART.command
launchctl kickstart -k "gui/$(id -u)/$FIELD_LABEL" 2>/dev/null || true

print "\n4) Verify local field"
LOCAL_OK=""
for i in {1..120}; do
  if curl -fsS http://127.0.0.1:8799/field/v1/health >/tmp/sembiotic-local-health.json 2>/dev/null; then LOCAL_OK=yes; break; fi
  sleep .5
done
if [[ "$LOCAL_OK" != yes ]]; then
  print "Local field failed to return healthy."
  tail -n 120 logs/launchd.err.log 2>/dev/null || true
  tail -n 120 logs/server.log 2>/dev/null || true
  exit 1
fi
curl -fsS -X POST http://127.0.0.1:8799/field/v1/search \
  -H 'Content-Type: application/json' \
  --data '{"query":"human motor neuron model for early ALS pathology and mitochondrial dysfunction","limit":12,"mode":"unified"}' \
  >/tmp/sembiotic-clean-search.json
"$PYTHON" - <<'PY'
import json
h=json.load(open('/tmp/sembiotic-local-health.json'))
s=json.load(open('/tmp/sembiotic-clean-search.json'))
assert h.get('ok') is True,h
rows=s.get('results') or []
assert rows,s
assert all(r.get('image_source') in ('record','none',None) for r in rows),rows[:2]
attached=sum(bool(r.get('image_url')) for r in rows)
print(f"LOCAL PASS · {h.get('count',0):,} objects · {len(rows)} ranked objects · {attached} with attached source media · {s.get('latency_ms')}ms")
print('TOP:',rows[0].get('title') or rows[0].get('name'),'·',round(float(rows[0].get('score',0)),3))
PY

print "\n5) Verify production"
PUBLIC_OK=""
for i in {1..120}; do
  if curl -fsS "https://$HOSTNAME/field/v1/health" >/tmp/sembiotic-public-health.json 2>/dev/null; then PUBLIC_OK=yes; break; fi
  sleep .75
done

print "\nSEMBIOTIC DEPLOY RESULT"
print "────────────────────────────────────────────────────────"
print "GitHub: https://github.com/ziolndr/sembiotic"
print "Local:  http://127.0.0.1:8799"
if [[ "$PUBLIC_OK" == yes ]]; then
  print "Live:   https://$HOSTNAME"
  cat /tmp/sembiotic-public-health.json | "$PYTHON" -m json.tool
  open "https://$HOSTNAME"
else
  print "Code is pushed and local field is live, but the production tunnel did not answer yet."
  open "http://127.0.0.1:8799"
  exit 1
fi
