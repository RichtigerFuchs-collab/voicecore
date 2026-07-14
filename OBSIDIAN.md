# VoiceCore → Obsidian

Jede Sprachnotiz landet ab v0.8.0 **parallel** in zwei Zielen:

1. **Google Doc** (wie bisher) — für unterwegs, für Kathrin, geräteübergreifend
2. **Obsidian-Vault** — als Markdown, angehängt an eine von drei Sammel-Dateien

| Vorlage | Obsidian-Zieldatei | Einfügeposition |
|---|---|---|
| Tagebuch | `Tagebuch & Reiseberichte/K&K Tagebuch.md` | oben (neueste zuerst) |
| Quick Note | `00_Inbox/inbox.md` | oben (neueste zuerst) |
| Restaurant Review | `Reviews/Restaurant-Reviews.md` | vor dem `## 🔗 Verknüpft`-Block |

---

## Wie es funktioniert

```
Handy (PWA)  →  Render-Backend  →  Gemini (1 Call, 3 Felder)
                                     ├── formatted  →  Google Doc      (sofort)
                                     └── markdown   →  Postfach-Doc    (sofort)

PC (Aufgabenplanung, alle 15 Min)
   tools/obsidian_sync.py  →  liest Postfach-Doc
                           →  hängt Einträge an die 3 Vault-Dateien
                           →  leert das Postfach
```

### Warum ein Google Doc als Postfach — und keine .md-Datei in Google Drive?

Weil es nicht ginge. **Service Accounts haben kein eigenes Drive-Speicherkontingent** und können in einem normalen (Consumer-)Google-Drive keine Dateien anlegen — jeder Upload scheitert mit `storageQuotaExceeded`. In ein Doc, das *dir* gehört, dürfen sie aber Text einfügen. Genau das tun sie bei den drei Ziel-Docs ja schon.

Das Postfach ist also ein ganz normales Google Doc, in das die Markdown-Blöcke zwischengeparkt werden, bis der PC sie abholt. Format:

```
<<<VOICECORE|tagebuch|Kim|2026-07-14T18:30:00>>>
## 14. Juli 2026 – Titel (Kim)
### Was war los?
...
<<<ENDE>>>
```

### Warum kein YAML-Frontmatter pro Eintrag?

Dein ursprüngliches Konzept sah `---`-Frontmatter je Eintrag vor. Das funktioniert nur bei *einer Datei pro Notiz*. Da die Einträge an **bestehende Sammel-Dateien** angehängt werden (die schon ein Frontmatter am Dateianfang haben), würde ein zweites `---` mitten im Dokument von Obsidian als Trennlinie gerendert. Stattdessen: jeder Eintrag beginnt mit einer `##`-Überschrift, Metadaten stehen als Hashtags (`#restaurant`, `#idee`) am Ende — in Obsidian genauso durchsuchbar.

---

## Einrichtung (einmalig)

### 1. Postfach-Doc anlegen
- Neues, leeres Google Doc erstellen, z.B. **„VoiceCore Postfach"**
- Mit der Service-Account-E-Mail als **Editor** teilen (dieselbe wie bei den anderen Docs — steht im JSON-Key unter `client_email`)
- Link kopieren

### 2. In der App eintragen
- ⚙ öffnen → Feld **„Obsidian-Postfach"** → Link einfügen
- Leer lassen = kein Obsidian-Export (die App funktioniert dann wie vorher)

### 3. Service-Account-Key lokal ablegen
Der Abholer braucht denselben Key, der auf Render liegt. Lege die JSON-Datei irgendwo **außerhalb des Repos** ab, z.B. `C:\Users\Kim\Secrets\voicecore-service-account.json`.

> ⚠️ Der Key darf **nie** ins Git-Repo. `.gitignore` schließt `*service-account*.json` und die Config bereits aus.

### 4. Abholer konfigurieren
```bash
cd voicecore/tools
copy obsidian_sync.config.example.json obsidian_sync.config.json
```
Dann in `obsidian_sync.config.json` eintragen:
```json
{
  "service_account_file": "C:/Users/Kim/Secrets/voicecore-service-account.json",
  "queue_doc_url": "https://docs.google.com/document/d/DEIN_POSTFACH_DOC/edit",
  "vault_path": "C:/Users/Kim/Proton Drive/My files/Claude/Obsidian"
}
```

### 5. Testlauf
```bash
cd voicecore
backend/.venv/Scripts/python.exe tools/obsidian_sync.py
```
Ausgabe bei leerem Postfach: `Postfach ist leer – nichts zu tun.`

### 6. Automatisieren (Windows-Aufgabenplanung)
- Aufgabenplanung öffnen → **Einfache Aufgabe erstellen**
- Name: `VoiceCore → Obsidian`
- Trigger: **Täglich**, dann in den Eigenschaften auf „alle 15 Minuten wiederholen, Dauer: unbegrenzt" stellen
  *(oder Trigger „Bei Anmeldung", wenn dir das reicht)*
- Aktion: **Programm starten**
  - Programm: `C:\Users\Kim\Proton Drive\My files\Claude\voicecore\backend\.venv\Scripts\python.exe`
  - Argumente: `tools\obsidian_sync.py`
  - Starten in: `C:\Users\Kim\Proton Drive\My files\Claude\voicecore`

---

## Zweiter Rechner (Mac)

Der Abholer darf auf **beiden** Rechnern laufen — je öfter einer von beiden an ist, desto schneller landen die Notizen im Vault. Kein Konflikt, weil der Abholer das Postfach **beansprucht, bevor** er schreibt (siehe Sicherheitsnetz).

### Einrichtung auf dem Mac

**1. Konfiguration anlegen** — das Repo liegt in Proton Drive und ist auf dem Mac ohnehin da, aber die Pfade darin sind Windows-Pfade. Deshalb bekommt jede Plattform eine eigene Datei:

```
tools/obsidian_sync.config.darwin.json    ← Mac
tools/obsidian_sync.config.win32.json     ← Windows (existiert bereits)
```

Inhalt der Mac-Variante:
```json
{
  "service_account_file": "/Users/DEINNAME/Secrets/voicecore-service-account.json",
  "queue_doc_url": "https://docs.google.com/document/d/14BXLwIDktrUqTqPggkF8io8qj9Z8QkJmUilBaNjCmSA/edit",
  "vault_path": "/Users/DEINNAME/.../Obsidian"
}
```

**2. Service-Account-Key auf den Mac kopieren** — dieselbe JSON-Datei wie auf dem PC, an den Pfad aus der Config. (Nicht über den Chat oder eine Cloud schicken — USB-Stick oder verschlüsselter Transfer.)

**3. Setup-Skript ausführen:**
```bash
cd /pfad/zu/voicecore
chmod +x tools/setup_mac.sh
./tools/setup_mac.sh
```
Das Skript legt eine eigene Python-Umgebung (`.venv-mac`) an, installiert die Abhängigkeiten, macht einen Testlauf und richtet einen **launchd-Job** ein: alle 15 Minuten plus einmal beim Anmelden.

### Nützliche Befehle (Mac)
```bash
tail -f /tmp/voicecore-obsidian-sync.log         # Log mitlesen
launchctl start com.voicecore.obsidian-sync      # sofort ausführen
launchctl unload ~/Library/LaunchAgents/com.voicecore.obsidian-sync.plist   # abschalten
```

---

## Sicherheitsnetz

Der Abholer arbeitet in dieser Reihenfolge: **sichern → beanspruchen → schreiben.**

1. Die Blöcke werden lokal gesichert (`tools/.pending/<rechnername>/`)
2. Das Postfach wird geleert — **das ist der Anspruch**: Wer zuerst leert, verarbeitet die Einträge. Der zweite Rechner findet ein leeres Postfach und tut nichts.
3. Erst dann wird ins Vault geschrieben. Klappt das, verschwindet die Sicherung; klappt es nicht, bleibt sie liegen und der nächste Lauf holt sie nach.

**Warum diese Reihenfolge?** Würden PC und Mac denselben Eintrag verarbeiten, schriebe jeder ihn in *seine* Kopie des Vaults — Syncthing sähe zwei konkurrierende Änderungen und legte `.sync-conflict-…md`-Dateien an. Das Beanspruchen verhindert das.

Zusätzlich prüft der Abholer vor jedem Einfügen, ob der Eintrag schon in der Datei steht. Doppelte Einträge sind damit auch dann ausgeschlossen, wenn etwas schiefgeht.

**Es geht nie etwas verloren:** Selbst wenn der Rechner mitten im Schreiben abstürzt, liegt die Sicherung in `tools/.pending/` und wird beim nächsten Lauf verarbeitet.

## Wenn etwas nicht klappt

| Symptom | Ursache |
|---|---|
| App zeigt „⚠ Obsidian-Postfach nicht erreichbar" | Postfach-Doc nicht mit dem Service Account als **Editor** geteilt |
| Abholer: „Keine Konfiguration gefunden" | `obsidian_sync.config.json` fehlt (Schritt 4) |
| Abholer: „Vault-Pfad nicht gefunden" | `vault_path` in der Config falsch |
| Einträge kommen nicht an | Läuft die Aufgabenplanung? Testlauf manuell ausführen (Schritt 5) |
