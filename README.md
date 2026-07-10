# VoiceCore V1

Voice → Gemini → Formatierung → Google Docs

---

## Status

| Phase | Beschreibung | Status |
|-------|-------------|--------|
| 1 | Das Rohr: Mikrofon → Upload → Transkription | ✅ Fertig |
| 2 | Template-Verarbeitung: Transkript → formatierter Text | ✅ Fertig |
| 3 | Google Docs Integration (Code) | ✅ Fertig (noch nicht live) |
| 4 | Deployment live schalten | 🔜 Nächster Schritt |

---

## Was bisher gebaut wurde

### Phase 1 – Das Rohr
- **Frontend** (React + Vite): Aufnahme-UI mit großem Record-Button, Template-Auswahl, Statusanzeige
- **Backend** (FastAPI): nimmt Audiodatei entgegen, lädt sie zu Gemini, gibt Transkript zurück
- **Gemini-Transkription**: Audio → exaktes Transkript via `gemini-3.1-flash-lite`
- **Browser-Kompatibilität**: Safari (iOS/mp4), Chrome (webm/opus), Firefox (ogg) automatisch erkannt

### Phase 2 – Template-Verarbeitung
- Transkription + Formatierung in **einem** Gemini-Call (JSON-Antwort mit `transcript` + `formatted`) – halbiert Latenz und API-Calls
- **3 Templates** mit maßgeschneiderten Prompts:
  - **Tagebuch** – persönlicher Stil, 3 Abschnitte (Was war los / Wie war es / Gedanken danach), kreativer Titel, Füllwörter raus
  - **Quick Note** – TL;DR, Kernaussagen als Stichpunkte, Action Items, Hashtags
  - **Restaurant Review** – 5 Kategorien (Essen, Ambiente, Service, Preis-Leistung, Besonderheit) mit Sternebewertung ★, Gesamtbewertung
- **Frontend**: Formatiertes Ergebnis als Hauptanzeige, rohes Transkript einklappbar

### Phase 3 – Google Docs Integration
- **Service Account Authentifizierung**: JSON-Key als Env-Var `GOOGLE_SERVICE_ACCOUNT_JSON`
- **`extract_doc_id()`**: parst Doc-ID aus jeder Google Docs URL per Regex
- **`write_to_google_doc()`**: prepend-Eintrag mit Header (Template-Name, Datum, Uhrzeit) via Docs API `batchUpdate`
- **Frontend Settings-Panel**: ⚙-Button öffnet Panel mit URL-Eingabe pro Template, wird in `localStorage` gespeichert
- **Feedback**: `✓ Gespeichert in Google Doc` (grün) oder `⚠ konnte nicht beschrieben werden` (amber)
- **`render.yaml`**: Env-Var `GOOGLE_SERVICE_ACCOUNT_JSON` vorbereitet

### Modell & SDK (Stand 10.07.2026)
- `gemini-3.1-flash-lite` (stabile GA-Version, Nachfolger des Preview-Modells)
- SDK: `google-genai` (das alte `google-generativeai` ist deprecated, Support-Ende Aug 2025)
- Audio geht inline im Request zu Gemini (kein separater Datei-Upload, keine Temp-Dateien mehr)
- Datum wird locale-unabhängig auf Deutsch formatiert (fixt `%-d`-Crash unter Windows und englische Monatsnamen auf Render)

### Cold-Start-Fix
- `.github/workflows/keepalive.yml` pingt alle 10 Min `/health` → Render Free Tier schläft nie ein (sonst ~50 s Wartezeit nach 15 Min Inaktivität)
- Voraussetzung: GitHub-Repo ist public (sonst verbraucht der Actions-Cron Minuten-Kontingent)

---

## Offene Punkte (nächste Session)

### 1. Deployment live schalten
Die Änderungen aus Phase 2 + 3 sind noch nicht live. Backend läuft auf `https://voicecore.onrender.com`.

**To-Do:**
- [ ] Frontend neu bauen: `npm run build --prefix frontend` (dist/ ist eingecheckt und wird von Render mit ausgeliefert – kein Netlify)
- [ ] Änderungen in GitHub pushen → Render deployed automatisch (Frontend + Backend, ein Service)
- [ ] PWA auf dem Handy neu laden / Cache leeren

### 2. Google Cloud Setup (einmalig, vor erstem Test)
- [ ] Google Cloud Projekt erstellen (z.B. `voicecore`)
- [ ] Google Docs API aktivieren
- [ ] Service Account `voicecore-writer` erstellen + JSON-Key herunterladen
- [ ] Auf Render: `GOOGLE_SERVICE_ACCOUNT_JSON` = JSON-Inhalt als Env-Var setzen
- [ ] 3 Ziel-Google-Docs mit der `client_email` aus dem JSON als Editor teilen
- [ ] In der App: ⚙ öffnen → Google Docs URLs pro Template eintragen

### 3. Nach erstem Live-Test
- [ ] Prüfen ob Datumsformat auf Render korrekt (`%-d` funktioniert auf Linux)
- [ ] Prüfen ob Monatsname auf Render englisch oder deutsch ausgegeben wird

---

## Infrastruktur

| Dienst | URL | Zweck |
|--------|-----|-------|
| Render.com | `https://voicecore.onrender.com` | Frontend + Backend (ein Service) |
| GitHub Actions | `.github/workflows/keepalive.yml` | Keep-alive-Ping gegen Cold Starts |
| Google Cloud | Projekt noch zu erstellen | Docs API Service Account |

---

## Setup lokal

### Backend (Terminal 1)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend (Terminal 2)
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Umgebungsvariablen (backend/.env)
```
GEMINI_API_KEY=...
GOOGLE_SERVICE_ACCOUNT_JSON=...   # ganzes JSON als String
GEMINI_MODEL=gemini-3.1-flash-lite-preview   # optional, das ist der Default
```
