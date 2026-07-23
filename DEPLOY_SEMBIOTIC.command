#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
REMOTE="git@github.com:ziolndr/sembiotic.git"
HOSTNAME="sembiotic.actualgeneralintelligence.com"
FIELD_LABEL="com.actualgeneralintelligence.arbiter.biology-field"
cd "$ROOT"

print "SEMBIOTIC — FIELD GALLERY DEPLOY"
print "────────────────────────────────────────────────────────"

print "\n1) Validate the production build"
python3 - <<'PY'
from pathlib import Path
p=Path('public/index.html')
s=p.read_text()
required=[
  '<title>Sembiotic — The Biological Meaning Platform</title>',
  "'Instrument Sans'", "'Fragment Mono'",
  'id="queryForm"', 'id="resultLayer"', 'id="fieldCanvas"',
  'id="modes"', 'Choose the layer of biology that matters.',
  'Powered by <b>ARBITER</b>',
  "const FIELD_BASE=window.ARBITER_BIOLOGY_FIELD_URL||window.location.origin;"
]
missing=[x for x in required if x not in s]
if missing:
    raise SystemExit('Missing production markers: '+', '.join(missing))
for name in ['og-sembiotic.jpg','favicon.png']:
    q=Path('public/assets')/name
    if not q.exists() or q.stat().st_size < 1000:
        raise SystemExit(f'Missing asset: {q}')
for retired in ['hero-01-coast.jpg','hero-02-coast-group.jpg','hero-03-researchers.jpg','hero-04-figure.jpg']:
    if (Path('public/assets')/retired).exists():
        raise SystemExit(f'Retired casual asset is still present: {retired}')
print('HTML and brand system: PASS')
PY

python3 - <<'PY'
from pathlib import Path
s=Path('public/index.html').read_text()
script=s.split('<script>',1)[1].split('</script>',1)[0]
Path('/tmp/sembiotic-production.js').write_text(script)
PY
if command -v node >/dev/null 2>&1; then
  node --check /tmp/sembiotic-production.js
  print "JavaScript: PASS"
fi

print "\n2) Commit and push to GitHub"
if [[ ! -d .git ]]; then
  git init -b main
  git remote add origin "$REMOTE"
  git fetch origin main >/dev/null 2>&1 || true
else
  git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"
fi

git checkout -B main
# Pull only when the remote exists; local production files win conflicts.
git pull --rebase --autostash origin main 2>/dev/null || true

git add -A
if ! git diff --cached --quiet; then
  git commit -m "Redesign Sembiotic as biological field platform"
else
  print "Git working tree already current."
fi
git push -u origin main

print "\n3) Restart the persistent field server"
chmod +x ./*.command
if launchctl print "gui/$(id -u)/$FIELD_LABEL" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/$FIELD_LABEL"
else
  ./INSTALL_AUTOSTART.command
  launchctl kickstart -k "gui/$(id -u)/$FIELD_LABEL" 2>/dev/null || true
fi

print "\n4) Verify local field"
LOCAL_OK=""
for i in {1..100}; do
  if curl -fsS http://127.0.0.1:8799/field/v1/health >/tmp/sembiotic-local-health.json 2>/dev/null; then
    LOCAL_OK=yes
    break
  fi
  sleep .5
done
if [[ "$LOCAL_OK" != yes ]]; then
  print "Local field failed to return healthy."
  tail -n 100 logs/launchd.err.log 2>/dev/null || true
  tail -n 100 logs/server.log 2>/dev/null || true
  exit 1
fi
cat /tmp/sembiotic-local-health.json | python3 -m json.tool

print "\n5) Verify the production hostname"
PUBLIC_OK=""
for i in {1..100}; do
  if curl -fsS "https://$HOSTNAME/field/v1/health" >/tmp/sembiotic-public-health.json 2>/dev/null; then
    PUBLIC_OK=yes
    break
  fi
  sleep .75
done

print "\nSEMBIOTIC DEPLOY RESULT"
print "────────────────────────────────────────────────────────"
print "GitHub: https://github.com/ziolndr/sembiotic"
print "Local:  http://127.0.0.1:8799"
if [[ "$PUBLIC_OK" == yes ]]; then
  print "Live:   https://$HOSTNAME"
  cat /tmp/sembiotic-public-health.json | python3 -m json.tool
  open "https://$HOSTNAME"
else
  print "Code is pushed and the local field is live, but the public tunnel did not answer yet:"
  print "https://$HOSTNAME"
  print "Restart the dedicated Sembiotic Cloudflare tunnel, then rerun this command."
  open "http://127.0.0.1:8799"
  exit 1
fi
