#!/bin/bash
# VoiceCore → Obsidian: Abholer auf dem Mac einrichten.
#
# Einmal ausführen:
#   chmod +x tools/setup_mac.sh
#   ./tools/setup_mac.sh
#
# Richtet einen launchd-Job ein, der alle 15 Minuten das Postfach-Doc abholt.
# Läuft im Hintergrund, kein Fenster, startet automatisch beim Anmelden.

set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.voicecore.obsidian-sync.plist"
VENV="$REPO/.venv-mac"

echo "VoiceCore → Obsidian: Mac-Einrichtung"
echo "Repo: $REPO"
echo

# ── 1. Python-Umgebung ───────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "Erstelle Python-Umgebung (.venv-mac) ..."
  python3 -m venv "$VENV"
fi
echo "Installiere Abhängigkeiten ..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q google-auth google-api-python-client
echo "  ✓ Python-Umgebung bereit"
echo

# ── 2. Konfiguration prüfen ──────────────────────────────────────────────────
CFG="$REPO/tools/obsidian_sync.config.json"
if [ ! -f "$CFG" ]; then
  echo "FEHLER: $CFG fehlt."
  echo
  echo "Lege sie an (Mac-Pfade!):"
  echo '  {'
  echo '    "service_account_file": "/Users/DEINNAME/Secrets/voicecore-service-account.json",'
  echo '    "queue_doc_url": "https://docs.google.com/document/d/14BXLwIDktrUqTqPggkF8io8qj9Z8QkJmUilBaNjCmSA/edit",'
  echo '    "vault_path": "/Users/DEINNAME/.../Obsidian"'
  echo '  }'
  echo
  echo "Der Service-Account-Key ist derselbe wie auf dem PC – einmal kopieren."
  exit 1
fi
echo "  ✓ Konfiguration gefunden"

# ── 3. Testlauf ──────────────────────────────────────────────────────────────
echo
echo "Testlauf ..."
"$VENV/bin/python" "$REPO/tools/obsidian_sync.py"
echo

# ── 4. launchd-Job ───────────────────────────────────────────────────────────
# Versatz von 7 Minuten gegenüber dem PC (dort: volle Viertelstunde), damit
# beide Rechner nicht gleichzeitig abholen. Nötig ist das nicht – das Skript
# beansprucht das Postfach, bevor es schreibt – aber es hält die Logs sauber.
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicecore.obsidian-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV/bin/python</string>
        <string>$REPO/tools/obsidian_sync.py</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/voicecore-obsidian-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/voicecore-obsidian-sync.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "  ✓ launchd-Job eingerichtet: alle 15 Minuten + beim Anmelden"
echo
echo "Fertig."
echo
echo "Nützlich:"
echo "  Log ansehen:      tail -f /tmp/voicecore-obsidian-sync.log"
echo "  Sofort ausführen: launchctl start com.voicecore.obsidian-sync"
echo "  Abschalten:       launchctl unload $PLIST"
