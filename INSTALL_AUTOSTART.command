#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}";PYTHON="${ARBITER_PYTHON:-$(command -v python3)}";PORT="${ARBITER_BIOLOGY_PORT:-8799}";EMBED_URL="${ARBITER_EMBED_URL:-http://127.0.0.1:8000/v1/embed}"
PLIST="$HOME/Library/LaunchAgents/com.actualgeneralintelligence.arbiter.biology-field.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.actualgeneralintelligence.arbiter.biology-field</string>
<key>ProgramArguments</key><array><string>$PYTHON</string><string>-u</string><string>$ROOT/scripts/serve_field.py</string><string>--host</string><string>127.0.0.1</string><string>--port</string><string>$PORT</string><string>--field</string><string>$ROOT/field</string><string>--public</string><string>$ROOT/public</string><string>--embed-url</string><string>$EMBED_URL</string></array>
<key>WorkingDirectory</key><string>$ROOT</string><key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>$ROOT/logs/launchd.out.log</string><key>StandardErrorPath</key><string>$ROOT/logs/launchd.err.log</string>
</dict></plist>
EOF
launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"
launchctl enable gui/$(id -u)/com.actualgeneralintelligence.arbiter.biology-field
plutil -lint "$PLIST"
echo "Autostart installed · $PLIST"
