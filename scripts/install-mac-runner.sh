#!/bin/bash
# Install (or with --uninstall, remove) the Mac runner: a background task that
# starts scraper/worker.py once a minute and at login. It reads the stores that
# refuse cloud servers (Dis-Chem, Checkers, Amazon.co.za).
#
#   scripts/install-mac-runner.sh              install and start
#   scripts/install-mac-runner.sh --uninstall  stop and remove
set -euo pipefail

LABEL="co.nappypricewatch.worker"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/NappyPriceWatch"
PYTHON="$PROJECT/.venv/bin/python"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$PLIST"
  echo "Mac runner removed."
  exit 0
fi

[ -x "$PYTHON" ] || { echo "No virtual environment at $PROJECT/.venv. Run 'uv sync' first."; exit 1; }
[ -f "$PROJECT/.env" ] || { echo "No .env in $PROJECT. The runner needs SUPABASE_URL and SUPABASE_SERVICE_KEY."; exit 1; }

mkdir -p "$LOGS" "$(dirname "$PLIST")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-m</string>
    <string>scraper.worker</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>EnvironmentVariables</key>
  <dict><key>RUNNER</key><string>home</string></dict>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOGS/worker.log</string>
  <key>StandardErrorPath</key><string>$LOGS/worker.log</string>
</dict>
</plist>
PLIST

launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Mac runner installed. It starts once a minute and at login."
echo "Log: $LOGS/worker.log"
echo "Remove with: scripts/install-mac-runner.sh --uninstall"
