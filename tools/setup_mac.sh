#!/bin/bash
# VoiceCore → Obsidian: Abholer auf dem Mac einrichten.
#
#   chmod +x tools/setup_mac.sh
#   ./tools/setup_mac.sh
#
# Das Skript sucht das Obsidian-Vault und den Service-Account-Key selbst,
# schreibt die Konfiguration, macht einen Testlauf und richtet einen
# launchd-Job ein (alle 15 Min + beim Anmelden, ohne Fenster).

set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/.venv-mac"
CFG="$REPO/tools/obsidian_sync.config.darwin.json"
PLIST="$HOME/Library/LaunchAgents/com.voicecore.obsidian-sync.plist"
QUEUE_URL="https://docs.google.com/document/d/14BXLwIDktrUqTqPggkF8io8qj9Z8QkJmUilBaNjCmSA/edit"

echo "═══════════════════════════════════════════════"
echo "  VoiceCore → Obsidian: Mac-Einrichtung"
echo "═══════════════════════════════════════════════"
echo "Repo: $REPO"
echo

# ── 1. Obsidian-Vault suchen ─────────────────────────────────────────────────
echo "▸ Suche das Obsidian-Vault ..."
VAULT=""
MARKER="Tagebuch & Reiseberichte/K&K Tagebuch.md"

for base in "$HOME/Proton Drive" "$HOME/Library/CloudStorage" "$HOME/Documents" "$HOME"; do
  [ -d "$base" ] || continue
  found=$(find "$base" -maxdepth 6 -name "K&K Tagebuch.md" -not -path "*/.*" 2>/dev/null | head -1)
  if [ -n "$found" ]; then
    VAULT="$(cd "$(dirname "$(dirname "$found")")" && pwd)"
    break
  fi
done

if [ -z "$VAULT" ] || [ ! -f "$VAULT/$MARKER" ]; then
  echo "  Vault nicht automatisch gefunden."
  read -r -p "  Pfad zum Obsidian-Ordner eingeben: " VAULT
  VAULT="${VAULT/#\~/$HOME}"
  if [ ! -f "$VAULT/$MARKER" ]; then
    echo "  FEHLER: '$MARKER' liegt nicht in '$VAULT'."
    exit 1
  fi
fi
echo "  ✓ Vault: $VAULT"
echo

# ── 2. Service-Account-Key finden ────────────────────────────────────────────
echo "▸ Suche den Service-Account-Key ..."
KEY=""
for cand in "$HOME/Secrets/voicecore-service-account.json" \
            "$HOME/Downloads"/*service-account*.json \
            "$HOME/Downloads"/*astute-maxim*.json; do
  if [ -f "$cand" ] && grep -q '"type": *"service_account"' "$cand" 2>/dev/null; then
    KEY="$cand"; break
  fi
done

if [ -z "$KEY" ]; then
  echo "  Key nicht gefunden."
  echo
  echo "  Der Key ist dieselbe JSON-Datei wie auf dem Windows-PC"
  echo "  (dort: C:\\Users\\Kim\\Secrets\\voicecore-service-account.json)."
  echo "  Kopiere sie auf den Mac – per USB-Stick oder AirDrop, NICHT per Chat/Cloud."
  echo "  Empfohlener Ort: ~/Secrets/voicecore-service-account.json"
  echo
  read -r -p "  Pfad zur JSON-Datei: " KEY
  KEY="${KEY/#\~/$HOME}"
fi

if [ ! -f "$KEY" ] || ! grep -q '"type": *"service_account"' "$KEY" 2>/dev/null; then
  echo "  FEHLER: '$KEY' ist keine gültige Service-Account-Datei."
  exit 1
fi
chmod 600 "$KEY"
echo "  ✓ Key: $KEY"
echo

# ── 3. Konfiguration schreiben ───────────────────────────────────────────────
cat > "$CFG" <<EOF
{
  "service_account_file": "$KEY",
  "queue_doc_url": "$QUEUE_URL",
  "vault_path": "$VAULT"
}
EOF
echo "▸ Konfiguration geschrieben: $(basename "$CFG")"
echo

# ── 4. Python-Umgebung ───────────────────────────────────────────────────────
echo "▸ Python-Umgebung ..."
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q google-auth google-api-python-client
echo "  ✓ bereit"
echo

# ── 5. Testlauf ──────────────────────────────────────────────────────────────
echo "▸ Testlauf ..."
"$VENV/bin/python" "$REPO/tools/obsidian_sync.py"
echo

# ── 6. launchd-Job ───────────────────────────────────────────────────────────
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
echo "▸ Hintergrund-Job eingerichtet: alle 15 Minuten + beim Anmelden"
echo

echo "═══════════════════════════════════════════════"
echo "  Fertig."
echo "═══════════════════════════════════════════════"
echo
echo "Nützlich:"
echo "  Log ansehen:      tail -f /tmp/voicecore-obsidian-sync.log"
echo "  Sofort ausführen: launchctl start com.voicecore.obsidian-sync"
echo "  Abschalten:       launchctl unload $PLIST"
