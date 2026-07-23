#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
REMOTE="git@github.com:ziolndr/sembiotic.git"
HOSTNAME="sembiotic.actualgeneralintelligence.com"
LABEL="com.actualgeneralintelligence.arbiter.biology-field"
cd "$ROOT"

print "SEMBIOTIC — BRAND DEPLOY"
print "────────────────────────────────────────────────────────"

print "\n1) Validate production HTML and assets"
python3 - <<'PY'
from pathlib import Path
p=Path('public/index.html')
s=p.read_text()
required=[
  '<title>Sembiotic — The Biological Meaning Platform</title>',
  'id="queryForm"', 'id="resultLayer"', 'id="fieldCanvas"',
  'assets/hero-01-coast.jpg', 'Powered by ARBITER'
]
missing=[x for x in required if x not in s]
if missing:
    raise SystemExit('Missing production markers: '+', '.join(missing))
for name in ['hero-01-coast.jpg','hero-02-coast-group.jpg','hero-03-researchers.jpg','hero-04-figure.jpg','og-sembiotic.jpg','favicon.png']:
    q=Path('public/assets')/name
    if not q.exists() or q.stat().st_size < 1000:
        raise SystemExit(f'Missing asset: {q}')
print('production HTML: PASS')
PY

if command -v node >/dev/null 2>&1; then
  python3 - <<'PY'
from pathlib import Path
s=Path('public/index.html').read_text().split('<script>',1)[1].split('</script>',1)[0]
Path('/tmp/sembiotic-production.js').write_text(s)
PY
  node --check /tmp/sembiotic-production.js
  print "JavaScript: PASS"
fi

print "\n2) Commit Sembiotic to GitHub"
if [[ ! -d .git ]]; then
  git init -b main
  git remote add origin "$REMOTE"
  if git fetch origin main >/dev/null 2>&1; then
    git reset --mixed origin/main
  fi
else
  git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"
  git checkout -B main
  git pull --rebase --autostash origin main 2>/dev/null || true
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -m "Launch Sembiotic biological meaning platform"
else
  print "Git working tree already current."
fi
git push -u origin main

print "\n3) Restart the persistent field server"
chmod +x ./*.command
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
else
  ./INSTALL_AUTOSTART.command
  launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || true
fi

print "\n4) Verify local field"
LOCAL_OK=""
for i in {1..80}; do
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

print "\n5) Verify production hostname"
PUBLIC_OK=""
for i in {1..80}; do
  if curl -fsS "https://$HOSTNAME/field/v1/health" >/tmp/sembiotic-public-health.json 2>/dev/null; then
    PUBLIC_OK=yes
    break
  fi
  sleep .75
done

print "\nSEMBIOTIC DEPLOYED"
print "────────────────────────────────────────────────────────"
print "GitHub: https://github.com/ziolndr/sembiotic"
print "Local:  http://127.0.0.1:8799"
if [[ "$PUBLIC_OK" == yes ]]; then
  print "Live:   https://$HOSTNAME"
  cat /tmp/sembiotic-public-health.json | python3 -m json.tool
  open "https://$HOSTNAME"
else
  print "The code is pushed and the local site is live, but the public tunnel did not answer yet:"
  print "https://$HOSTNAME"
  print "Check the dedicated Sembiotic Cloudflare tunnel service."
  open "http://127.0.0.1:8799"
  exit 1
fi
