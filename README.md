# VoiceCore

**Sprachnotiz einsprechen → Gemini transkribiert & formatiert → Eintrag landet im richtigen Google Doc *und* im Obsidian-Vault.**

Eine bewusst leichte One-Click-PWA für Kim & Kathrin. Ein Tap auf den Record-Button, sprechen, fertig — der formatierte Eintrag steht Sekunden später im Tagebuch-, Notiz- oder Restaurant-Doc.

- **Live-App:** https://voicecore.onrender.com
- **Version:** 0.8.0 (Stand 15.07.2026) — `/health` zeigt die live laufende Version
- **Status:** Produktionsreif, produktiv im Einsatz
- **Obsidian-Anbindung:** siehe [OBSIDIAN.md](OBSIDIAN.md)

---

## Features (Was kann die App?)

### Aufnahme mit einem Tap
Großer Record-Button, Tap startet, Tap stoppt. Funktioniert als PWA auf dem Homescreen. Safari (iOS), Chrome (Android) und Firefox werden automatisch mit dem passenden Audioformat bedient.

### Sprecher-Auswahl: Kim / Kathrin
Umschalter über der Template-Auswahl. Die Wahl wird **pro Gerät gespeichert** — einmal einstellen, danach immer richtig. Der Name erscheint im Tagebuch-Titel. Wichtig und im Code verankert: **Kathrin immer mit „th“** — die Schreibweise wird Gemini für Transkript UND formatierten Text vorgegeben (`NAME_SPELLING_RULE` in `backend/main.py`).

### Drei Templates

| Template | Was passiert |
|----------|--------------|
| **Tagebuch** | Persönlicher Eintrag in 3 Abschnitten (Was war los? / Wie war es? / Gedanken danach). Titelzeile: `8. Juli 2026 – Kreativer Titel (Kathrin)` — **Datum zuerst**, Name in Klammern. Bleibt nah an den **emotionalen Originalformulierungen** der sprechenden Person. |
| **Quick Note** | TL;DR, Kernaussagen als Stichpunkte, Action Items, 3–5 Hashtags. |
| **Restaurant Review** | Folgt exakt dem Standardlayout des bestehenden Docs: Essens-Emoji + `Name – Stadt (Monat Jahr)`, 5 nummerierte Kategorien (Essen, Ambiente, Service, Preis-Leistung, Besonderheit), ⭐️-Sterne mit ½ für halbe Sterne, keine Gesamtbewertung. |

### Intelligente Datumserkennung (Tagebuch)
Wird im Audio ein Datum genannt („das war am 8. Juli“, „gestern“, „letzten Samstag“), rechnet Gemini es vom heutigen Datum aus um und setzt **dieses** Datum in die Titelzeile. Ohne Angabe (oder bei „heute“) gilt das heutige Datum. Datumsformat immer deutsch („8. Juli 2026“), unabhängig vom Server-Locale.

### Google-Docs-Anbindung
Im ⚙-Settings-Panel wird pro Template eine Google-Docs-URL hinterlegt (gespeichert im Browser). Neue Einträge werden **oben** ins Doc geschrieben (prepend) mit Trennlinie und Kopfzeile (Template · Datum · Uhrzeit). Der Output ist bewusst **reiner Text ohne Markdown** — `##` und `**` würden im Doc als sichtbare Zeichen landen. Feedback in der App: `✓ Gespeichert in Google Doc` (grün) oder `⚠ konnte nicht beschrieben werden` (amber).

### Obsidian-Anbindung (seit v0.8.0)
Parallel zum Google Doc wandert jede Notiz als Markdown in eine von drei Sammel-Dateien des Vaults: Tagebuch → `K&K Tagebuch.md`, Quick Note → `00_Inbox/inbox.md`, Review → `Restaurant-Reviews.md`. Gemini liefert dafür ein drittes Feld (`markdown`) im selben Aufruf. Die Brücke ist ein **Postfach-Doc**, das ein lokaler Abholer (`tools/obsidian_sync.py`) alle 15 Minuten leert — auf PC **und** Mac. Vollständige Erklärung und Einrichtung: **[OBSIDIAN.md](OBSIDIAN.md)**.

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
   │  EIN Gemini-Call: Audio inline + kombinierter Prompt
   │  → JSON {transcript, formatted} (per response_schema erzwungen)
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
| `frontend/src/App.jsx` | Gesamtes Frontend: Aufnahme, Sprecher-Toggle, Settings, Ergebnis |
| `main.py` (Root) | Einstiegspunkt für Render (importiert `backend.main`) |
| `requirements.txt` (Root) | **Muss identisch mit `backend/requirements.txt` sein** — Render installiert die Root-Datei! |
| `render.yaml` | Render-Konfiguration inkl. Env-Var-Deklaration |
| `.github/workflows/keepalive.yml` | Cold-Start-Verhinderung |

### API

**`GET /health`** → `{"status": "ok", "version": "0.6.0", "gemini": true, "model": "gemini-3.1-flash-lite"}`
Dient auch der Deploy-Verifikation: Nach einem Push zeigt die Versionsnummer, ob der neue Stand live ist.

**`POST /upload`** (multipart/form-data)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `audio` | File | Audiodatei, Content-Type muss `audio/*` sein |
| `template` | Form | `tagebuch` \| `quick_note` \| `restaurant_review` |
| `speaker` | Form | `Kim` \| `Kathrin` (Fallback: „unbekannt“) |
| `destination_url` | Form | Google-Docs-URL (optional; leer = kein Docs-Write) |

Antwort: `{job_id, template, file_size_kb, transcript, formatted, doc_written}`

### Design-Entscheidungen (Warum ist das so gebaut?)

- **Ein Gemini-Call statt zwei:** Transkription + Formatierung in einer Anfrage, Audio geht inline mit (kein File-Upload zu Gemini, keine Temp-Dateien). JSON-Antwort per `response_schema` (Pydantic `VoiceResult`) erzwungen. Halbiert Latenz und API-Verbrauch.
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
