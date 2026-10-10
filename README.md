# VoiceCore

**Sprachnotiz einsprechen → Gemini transkribiert & formatiert → Eintrag landet im richtigen Google Doc *und* im Obsidian-Vault.**

Eine bewusst leichte One-Click-PWA für Kim & Kathrin. Ein Tap auf den Record-Button, sprechen, fertig — der formatierte Eintrag steht Sekunden später im Tagebuch-, Notiz- oder Restaurant-Doc.

**Release v0.10.2 vom 10.10.2026.** Tagebücher werden getrennt transkribiert, ausformuliert und gegen das Referenztranskript geprüft. Die laufende Version zeigt `/health`. Die Abnahme mit echten Aufnahmen steht noch aus.

- **Live-App:** https://voicecore.onrender.com
- **Release:** 0.10.2 — `/health` zeigt die live laufende Version
- **Hosting:** Bestehender Render-Free-Service in Frankfurt; Modell weiterhin `gemini-3.1-flash-lite`.
- **Obsidian-Anbindung:** siehe [OBSIDIAN.md](OBSIDIAN.md)

> ⚠️ **Historischer Fehlerbericht vom 26.07.2026, aktuell nicht erneut verifiziert:** Googles **kostenloser** Gemini-Tarif ist für Server in der **EU** gesperrt (`400 User location is not supported`). Render läuft in Frankfurt → Transkription scheitert derzeit. Nicht verarbeitete Aufnahmen bleiben in der App gesichert (nichts geht verloren). Lösung: Render in US-Region umziehen (bleibt 0 €) **oder** Google-Billing aktivieren (in der EU nutzbar, Kosten ~Cent). Details in [FORTSCHRITT.txt](FORTSCHRITT.txt).

---

## Fehlerkorrekturen v0.10.1 und v0.10.2

Ein formal ungültiger Tagebuchentwurf erhält einmal eine Strukturkorrektur aus dem vollständigen Transkript und wird anschließend weiterhin auf Inhaltstreue geprüft. Maximal sechs erfolgreiche Modellaufrufe bei Struktur- und Inhaltskorrektur.

Am 10.10.2026 lieferte Gemini bei einem echten Upload in der Inhaltsprüfung HTTP 503. Der verwendete SDK-Stand 1.55.0 wiederholt ohne explizite Retry-Konfiguration nicht automatisch. Jede Tagebuchstufe verwendet jetzt höchstens drei HTTP-Versuche mit exponentieller Wartezeit und Jitter für 408, 429, 500, 502, 503 und 504. Nur der betroffene Aufruf wird wiederholt; Export erfolgt erst nach bestandener Prüfung. Ein HTTP-Versuch hat ein Timeout von 90 Sekunden. Bei ausgeschöpften Wiederholungen nennt die sichere App-Meldung Stufe und HTTP-Code. Providertexte werden nicht protokolliert. Die lokale Aufnahme bleibt erhalten; serverseitig werden Audio oder Transkript nicht dauerhaft gespeichert.

23 Backend-Tests bestanden, darunter echte SDK-Aufrufe mit synthetischem HTTP-Transport für vorübergehendes 503, dauerhaftes 503 und nicht wiederholtes 400. Live-Health und Render-Status separat prüfen. Diese Tests bestätigen keine dauerhafte Verfügbarkeit des Gemini-Dienstes. Vorgehen entspricht der [Gemini-Retry-Empfehlung](https://ai.google.dev/gemini-api/docs/troubleshooting#retry-strategy).

## Features (Was kann die App?)

### Aufnahme mit einem Tap
Großer Record-Button, Tap startet, Tap stoppt. Funktioniert als PWA auf dem Homescreen. Safari (iOS), Chrome (Android) und Firefox werden automatisch mit dem passenden Audioformat bedient.

### Sprecher-Auswahl: Kim / Kathrin
Umschalter über der Template-Auswahl. Die Wahl wird **pro Gerät gespeichert** — einmal einstellen, danach immer richtig. Der Name erscheint im Tagebuch-Titel. Wichtig und im Code verankert: **Kathrin immer mit „th“** — die Schreibweise wird Gemini für Transkript UND formatierten Text vorgegeben (`NAME_SPELLING_RULE` in `backend/main.py`).

### Drei Templates

| Template | Was passiert |
|----------|--------------|
| **Tagebuch** | Inhaltstreuer persönlicher Eintrag mit passenden Abschnitten (Was war los? / Wie war es? / Gedanken danach). Abschnitte ohne erzählten Inhalt entfallen. Titelzeile: `8. Juli 2026 – Kreativer Titel (Kathrin)`. **Datum zuerst**, Name in Klammern. Bleibt nah an den **emotionalen Originalformulierungen** der sprechenden Person. |
| **Quick Note** | TL;DR, Kernaussagen als Stichpunkte, Action Items, 3–5 Hashtags. |
| **Restaurant Review** | Folgt exakt dem Standardlayout des bestehenden Docs: Essens-Emoji + `Name – Stadt (Monat Jahr)`, 5 nummerierte Kategorien (Essen, Ambiente, Service, Preis-Leistung, Besonderheit), ⭐️-Sterne mit ½ für halbe Sterne, keine Gesamtbewertung. |

### Intelligente Datumserkennung (Tagebuch)
Wird im Audio ein Datum genannt („das war am 8. Juli“, „gestern“, „letzten Samstag“), rechnet Gemini es vom heutigen Datum aus um und setzt **dieses** Datum in die Titelzeile. Ohne Angabe (oder bei „heute“) gilt das heutige Datum. Datumsformat immer deutsch („8. Juli 2026“), unabhängig vom Server-Locale.

### Inhaltstreue Tagebucheinträge (v0.10.0)

Tagebücher werden sprachlich geglättet und strukturiert. Alle eigenständigen Erlebnisse, Szenen, Details, Gefühle und Gedankengänge sollen erhalten bleiben. Es gibt keine feste Ziellänge und keine Kürzungsquote. Nur Füllwörter, Versprecher und echte Dopplungen dürfen entfallen. Abschnitte ohne erzählten Inhalt entfallen, statt mit erfundenen Gefühlen oder Reflexionen gefüllt zu werden.

Die Vorlage `tagebuch` verwendet einen eigenen Verarbeitungspfad:

1. Audio vollständig transkribieren.
2. Den ganzen Tagebucheintrag aus dem Transkript erstellen.
3. In einem separaten Aufruf gegen das vollständige Transkript auf Auslassungen, Bedeutungsveränderungen und erfundene Inhalte prüfen.
4. Bei Beanstandungen genau einmal korrigieren und erneut prüfen. Besteht der Eintrag die Prüfung weiterhin nicht, wird nichts exportiert.
5. Obsidian-Markdown aus dem geprüften Plaintext ableiten. Dabei werden ausschließlich Überschriftenmarker ergänzt. Beide Exporte enthalten denselben Eintrag.

Jede Stufe erhält ein eigenes Ausgabebudget von 32.768 Tokens. `MAX_TOKENS`, andere Abbrüche, leere oder ungültige Ergebnisse werden als Fehler behandelt, auch wenn eine JSON-Antwort teilweise lesbar ist. Die App zeigt eine sichere Fehlerursache und bietet erneutes Senden an. Die Aufnahme wird **vor** dem Upload lokal gesichert. Solange eine Sicherung offen ist, wird in derselben Appinstanz keine neue Aufnahme gestartet. Eine bereits verarbeitete Aufnahme wird bei einem lokalen Löschfehler nur lokal entfernt und nicht erneut exportiert.

Der Normalfall benötigt drei Gemini-Aufrufe, der Korrekturfall fünf. Das erhöht Wartezeit und API-Verbrauch. `quick_note` und `restaurant_review` behalten ihren bisherigen kombinierten Aufruf. Kein Modellwechsel und keine neue Runtime-Abhängigkeit.

Die Inhaltsprüfung ist eine zusätzliche KI-Prüfung, keine Garantie. Sie kann übersehene Informationen im Transkript nicht aus dem Audio rekonstruieren und selbst Fehler übersehen. Geht die HTTP-Erfolgsantwort nach einem Export verloren, kann ein Retry weiterhin doppelte Einträge erzeugen; serverseitige Idempotenz ist nicht Teil dieser Änderung. Ebenso ist der einzelne Aufnahmeslot nicht gegen mehrere gleichzeitig geöffnete Appinstanzen abgesichert.

API-Grundlage für Abbrucherkennung und Ausgabebudgets: [GenerateContent / FinishReason](https://ai.google.dev/api/generate-content#FinishReason), [Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite).

Abnahmefälle und lokale Prüfbefehle: [tests/README.md](tests/README.md).

### Google-Docs-Anbindung
Im ⚙-Settings-Panel wird pro Template eine Google-Docs-URL hinterlegt (gespeichert im Browser). Neue Einträge werden **oben** ins Doc geschrieben (prepend) mit Trennlinie und Kopfzeile (Template · Datum · Uhrzeit). Der Output ist bewusst **reiner Text ohne Markdown** — `##` und `**` würden im Doc als sichtbare Zeichen landen. Feedback in der App: `✓ Gespeichert in Google Doc` (grün) oder `⚠ konnte nicht beschrieben werden` (amber).

### Obsidian-Anbindung (seit v0.8.0)
Parallel zum Google Doc wandert jede Notiz als Markdown in eine von drei Sammel-Dateien des Vaults: Tagebuch → `K&K Tagebuch.md`, Quick Note → `00_Inbox/inbox.md`, Review → `Restaurant-Reviews.md`. Bei Tagebüchern leitet das Backend Markdown aus dem geprüften Plaintext ab; bei den anderen Vorlagen liefert Gemini das Feld `markdown` im kombinierten Aufruf. Die Brücke ist ein **Postfach-Doc**, das ein lokaler Abholer (`tools/obsidian_sync.py`) alle 15 Minuten leert — auf PC **und** Mac. Vollständige Erklärung und Einrichtung: **[OBSIDIAN.md](OBSIDIAN.md)**.

### Kein Warten auf Cold Starts
Dreistufig, weil GitHub-Cron allein nachweislich versagt (gemessen: Läufe nur alle 1–3,5 Stunden statt alle 10 Minuten):
1. **Service Worker** — die App öffnet sofort aus dem Cache, auch wenn der Server noch schläft
2. **Weck-Ping** auf `/health` beim App-Start — der Server wacht auf, während man einspricht
3. **Externer Ping-Dienst** (UptimeRobot, alle 5 Min) als primärer Keep-alive; `.github/workflows/keepalive.yml` läuft nur noch als Backup

---

## Technische Dokumentation

### Architektur

```
Browser (React-PWA, MediaRecorder)
   │  POST /upload  (audio, template, speaker, destination_url)
   ▼
FastAPI auf Render (ein Service, liefert auch das Frontend aus)
   │  Tagebuch: Transkript → Eintrag → Inhaltsprüfung (ggf. Korrektur + Prüfung)
   │  Andere Vorlagen: EIN Gemini-Call mit kombiniertem Prompt
   │  → {transcript, formatted, markdown}
   ▼
Google Docs API (Service Account, batchUpdate/insertText an Index 1)
```

### Stack

| Ebene | Technologie |
|-------|-------------|
| Frontend | React 18 + Vite, Inline-Styles, PWA. `dist/` ist **eingecheckt** — Render braucht kein Node |
| Backend | FastAPI (Python 3.11), Uvicorn |
| KI | `google-genai` SDK (das alte `google-generativeai` ist deprecated!), Modell `gemini-3.1-flash-lite` (stabil, per Env `GEMINI_MODEL` überschreibbar) |
| Docs | `google-api-python-client` mit Service-Account-Credentials |
| Hosting | Render.com Free Tier, Region Frankfurt, ein Web-Service für alles |
| Keep-alive | GitHub Actions Cron (alle 10 Min) |

### Schlüsseldateien

| Datei | Inhalt |
|-------|--------|
| `backend/main.py` | Gesamtes Backend: Template-Prompts, Gemini-Call, Docs-Write, Routes |
| `backend/diary.py` | Getrennte Tagebuchverarbeitung, Abbrucherkennung, Inhaltsprüfung, Markdown-Ableitung |
| `frontend/src/App.jsx` | Gesamtes Frontend: Aufnahme, Sprecher-Toggle, Settings, Ergebnis |
| `main.py` (Root) | Einstiegspunkt für Render (importiert `backend.main`) |
| `requirements.txt` (Root) | **Muss identisch mit `backend/requirements.txt` sein** — Render installiert die Root-Datei! |
| `render.yaml` | Render-Konfiguration inkl. Env-Var-Deklaration |
| `.github/workflows/keepalive.yml` | Cold-Start-Verhinderung |

### API

**`GET /health`** → `{"status": "ok", "version": "0.10.0", "gemini": true, "model": "gemini-3.1-flash-lite"}`
Dient auch der Deploy-Verifikation: Nach einem Push zeigt die Versionsnummer, ob der neue Stand live ist.

**`POST /upload`** (multipart/form-data)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `audio` | File | Audiodatei, Content-Type muss `audio/*` sein |
| `template` | Form | `tagebuch` \| `quick_note` \| `restaurant_review` |
| `speaker` | Form | `Kim` \| `Kathrin` (Fallback: „unbekannt“) |
| `destination_url` | Form | Google-Docs-URL (optional; leer = kein Docs-Write) |

Antwort: `{job_id, template, file_size_kb, transcript, formatted, markdown, doc_written, queued_for_obsidian, error}`. Bei gescheiterter Tagebuchverarbeitung bleibt die Antwort für den bestehenden Retry-Pfad HTTP 200, aber `formatted` und `markdown` sind `null`, beide Exportflags `false` und `error` enthält eine sichere Meldung. Ein bereits erzeugtes Referenztranskript bleibt im Antwortfeld erhalten.

### Design-Entscheidungen (Warum ist das so gebaut?)

- **Vorlagenspezifische Verarbeitung:** Für Tagebücher haben Inhaltstreue und prüfbare Verarbeitung Vorrang vor minimaler Latenz. Die anderen Vorlagen verwenden weiterhin einen kombinierten Aufruf. Audio geht inline mit, ohne Datei-Upload zu Gemini oder Audio-Tempdateien auf dem Server.
- **Eigenes Datumsformat statt `strftime`:** `%-d` crasht unter Windows, `%B` liefert auf Render englische Monatsnamen. `format_german_date()` + `GERMAN_MONTHS` sind locale-unabhängig.
- **Service Account statt OAuth:** Kein Login-Flow für die Nutzerinnen. Die Ziel-Docs werden einmalig mit der Service-Account-E-Mail als Editor geteilt.
- **`dist/` eingecheckt:** Render muss nur `pip install` ausführen, kein Node-Build im Deploy. Preis dafür: nach Frontend-Änderungen **immer `npm run build` vor dem Commit**.
- **Warum Eigenbau statt Claude/Gemini direkt:** Kein Anbieter kann zuverlässig „ein Tap → Template → bestimmtes bestehendes Google Doc“ (geprüft Juli 2026). Gemini-Workspace erzeugt bevorzugt neue Docs, Claude braucht einen Chat-Flow.

### Environment-Variablen (auf Render gesetzt)

| Variable | Zweck |
|----------|-------|
| `GEMINI_API_KEY` | Gemini API (ohne: App liefert Hinweis statt Transkript) |
| `GEMINI_MODEL` | Optionaler Modell-Override (Default: `gemini-3.1-flash-lite`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Kompletter JSON-Key des Service Accounts (ohne: Docs-Write wird übersprungen) |
| `APP_SECRET` | Shared Secret für `/upload`. Gesetzt → Requests brauchen den Header `X-App-Secret` (Passwortfeld im ⚙-Panel der App). Nicht gesetzt → Prüfung aus (lokale Entwicklung / Rollout) |

### Deploy-Flow

```bash
# Nach Frontend-Änderungen zuerst:
npm run build --prefix frontend

git add -A && git commit -m "..." && git push
# → Render deployed automatisch (2–3 Min)
# Verifikation: curl https://voicecore.onrender.com/health  → version prüfen
```

### Lokal entwickeln

```bash
# Backend (Terminal 1)
cd backend
python -m venv .venv                        # falls .venv fehlt/kaputt
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn main:app --reload --port 8000

# Frontend (Terminal 2)
cd frontend && npm install && npm run dev   # → http://localhost:5173
```

Hinweis: Der `GEMINI_API_KEY` liegt nur auf Render. Lokal ohne Key antwortet `/upload` mit einem Hinweistext — End-to-End-Tests laufen am einfachsten gegen die Live-App (z. B. per `curl` mit einer WAV-Datei, siehe `/upload`-API oben).

### Google Cloud Setup (erledigt — Referenz für Neuaufsetzen)

1. Google-Cloud-Projekt, Google Docs API aktivieren
2. Service Account erstellen, JSON-Key herunterladen
3. Render: `GOOGLE_SERVICE_ACCOUNT_JSON` = kompletter JSON-Inhalt
4. Jedes Ziel-Doc mit der `client_email` aus dem JSON als **Editor** teilen
5. In der App: ⚙ → Google-Docs-URL pro Template eintragen

---

## Iterationshistorie (Wie ist das Projekt gewachsen?)

| # | Zeitraum | Iteration | Ergebnis |
|---|----------|-----------|----------|
| 1 | Feb 2026 | **PoC „Das Rohr“** | Mikrofon → Upload → Gemini-Transkript sichtbar. React+Vite-Frontend, FastAPI-Backend, Browser-Audioformat-Erkennung |
| 2 | Feb 2026 | **Deployment-Härtung** | Frontend + Backend in EINEN Render-Service zusammengeführt, `dist/` eingecheckt, Root-`main.py` + Root-`requirements.txt` als Render-Einstieg (mehrere Fix-Iterationen) |
| 3 | Mär 2026 | **Templates & Docs-Code** | 3 Template-Prompts (Tagebuch, Quick Note, Restaurant Review), Google-Docs-Integration per Service Account, ⚙-Settings-Panel — Code fertig, aber noch nicht deployed |
| 4 | Jul 2026 | **Modernisierung & Live-Gang** | SDK-Migration auf `google-genai` (altes SDK deprecated), stabiles Modell statt Preview, ein Gemini-Call statt zwei, Datums-/Locale-Fix, Requirements-Deploy-Bug gefixt, Keep-alive-Workflow, alles live geschaltet und end-to-end getestet |
| 5 | Jul 2026 | **Personalisierung** | Kim/Kathrin-Umschalter (persistiert pro Gerät), Datum zuerst im Tagebuch-Titel, Restaurant-Review exakt nach Standardlayout des bestehenden Docs, Markdown aus dem Output entfernt |
| 6 | Jul 2026 | **Feinschliff nach echtem Nutzertest** | Emotionalere Tagebuch-Texte (näher an Originalformulierungen), Namensregel „Kathrin mit th” für Transkript + Text, gesprochene Datumsangaben schlagen das heutige Datum, `/health` zeigt Version |
| 7 | Jul 2026 | **Zugriffsschutz (v0.7.0)** | Shared-Secret-Header `X-App-Secret` für `/upload`, Passwortfeld im Settings-Panel, timing-sicherer Vergleich, fail-open ohne konfiguriertes Secret |
| 8 | Jul 2026 | **PWA-Manifest & Icon** | Eigenes App-Icon (Kim & Kathrin, Schallwelle, Google Doc) in 5 Größen inkl. Android-maskable, `manifest.webmanifest`, iOS-Meta-Tags — installiert sich als „echte App” mit eigenem Icon |
| 9 | Jul 2026 | **Aufnahmen überleben Netzprobleme** | Fehlgeschlagene Uploads landen in IndexedDB, Karte „Nicht gesendete Aufnahme” mit Erneut senden / Verwerfen, übersteht App-Neustart |
| 10 | Jul 2026 | **Cold Start wirklich gelöst** | Befund: GitHub-Cron lief nur alle 1–3,5 h statt alle 10 Min. Neu: Service Worker (App öffnet sofort aus dem Cache), Weck-Ping beim Start, GitHub-Cron nur noch als Backup, primär ein externer Ping-Dienst |
| 11 | Jul 2026 | **Obsidian-Export (v0.8.0)** | Jede Notiz geht parallel ins Google Doc **und** ins Obsidian-Vault. Gemini liefert drei Felder in einem Call. Postfach-Doc als Brücke (Service Accounts können keine Drive-Dateien anlegen), lokaler Abholer verteilt auf drei Sammel-Dateien |
| 12 | Jul 2026 | **Abholer auf PC und Mac** | Weniger PC-Abhängigkeit ohne VPS/GitHub. „Sichern → beanspruchen → schreiben” verhindert Syncthing-Konflikte, wenn beide Rechner laufen; plattformspezifische Konfiguration |

**Gelerntes Muster:** Jede Iteration wurde sofort live getestet (per `curl` mit TTS-generierten Testaufnahmen gegen die deployte App) — Fehler fielen dadurch innerhalb von Minuten auf, nicht erst beim nächsten echten Einsprechen.

## Mögliche nächste Schritte (offen, nicht dringend)

- [x] Shared-Secret-Header für `/upload` — v0.7.0
- [x] PWA-Manifest poliert — eigenes App-Icon, `manifest.webmanifest`, Apple-Touch-Icon, maskable-Variante
- [x] Aufnahmen überleben Netzprobleme — IndexedDB + „Erneut senden"-Karte
- [ ] Falls Tagebuch-Texte noch zu glatt wirken: „mindestens ein wörtliches Zitat pro Eintrag“ in den Prompt
- [ ] Falls Render Free irgendwann nicht mehr reicht: Google Cloud Run als Alternative (passt zum Google-Stack, Cold Start 1–3 s)
