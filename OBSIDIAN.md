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

## Sicherheitsnetz

Der Abholer leert das Postfach **erst, wenn alle Einträge erfolgreich ins Vault geschrieben wurden**. Schlägt etwas fehl (Vault-Pfad weg, Datei gesperrt), bleibt das Postfach unangetastet — kein Eintrag geht verloren, der nächste Lauf holt sie nach. Bereits vorhandene Einträge werden erkannt und nicht doppelt eingefügt.

## Wenn etwas nicht klappt

| Symptom | Ursache |
|---|---|
| App zeigt „⚠ Obsidian-Postfach nicht erreichbar" | Postfach-Doc nicht mit dem Service Account als **Editor** geteilt |
| Abholer: „Keine Konfiguration gefunden" | `obsidian_sync.config.json` fehlt (Schritt 4) |
| Abholer: „Vault-Pfad nicht gefunden" | `vault_path` in der Config falsch |
| Einträge kommen nicht an | Läuft die Aufgabenplanung? Testlauf manuell ausführen (Schritt 5) |
