# VoiceCore V1

Voice → Whisper → GPT → Google Docs

## Phase 1: Das Rohr (aktuell)
Mikrofon → Upload → FastAPI. Whisper kommt in Phase 2.

## Setup

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

### iPhone testen (lokales WLAN)
```bash
# Mac-IP ermitteln
ipconfig getifaddr en0

# .env.local anpassen:
# VITE_API_URL=http://192.168.x.x:8000

# Frontend mit Netzwerk-Zugriff starten:
cd frontend && npx vite --host
# → Safari auf iPhone: http://192.168.x.x:5173
```

## Deployment
- **Backend:** Render.com → Repository verbinden → `backend/` als Root → render.yaml wird automatisch erkannt
- **Frontend:** `npm run build` → `dist/` Ordner auf Netlify deployen
