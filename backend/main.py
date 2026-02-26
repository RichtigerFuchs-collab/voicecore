import os
import uuid
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="VoiceCore API", version="0.1.0")

# CORS: alle Origins erlaubt (Phase 2: auf Frontend-Domain einschränken)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # muss False sein wenn allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# /tmp ist auf Render.com beschreibbar. Lokal ebenfalls.
UPLOAD_DIR = Path("/tmp/voicecore_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Render.com ruft diesen Endpoint auf um zu prüfen ob der Service läuft."""
    return {"status": "ok"}


@app.post("/upload")
async def upload_audio(
    audio: UploadFile = File(...),
    template: str = Form(...),
):
    """
    Nimmt eine Audio-Datei und einen Template-Namen entgegen.

    Phase 1: Datei speichern, Stub-Antwort zurückgeben.
    Phase 2: Hier wird Whisper aufgerufen (siehe Marker unten).
    """

    # Sicherstellen dass wirklich eine Audio-Datei angekommen ist
    # Safari sendet audio/mp4, Chrome sendet audio/webm — beide beginnen mit "audio/"
    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Audio-Datei erwartet, erhalten: {content_type}"
        )

    # Eindeutige Job-ID generieren
    job_id = str(uuid.uuid4())

    # Dateiendung aus dem Original-Dateinamen ableiten
    original_name = audio.filename or "recording.webm"
    suffix = Path(original_name).suffix or ".webm"
    save_path = UPLOAD_DIR / f"{job_id}{suffix}"

    # Datei speichern (streaming – kein RAM-Problem bei großen Dateien)
    with save_path.open("wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    file_size_kb = round(save_path.stat().st_size / 1024, 1)

    print(f"[VoiceCore] Job empfangen: {job_id}")
    print(f"  Template : {template}")
    print(f"  Datei    : {save_path.name} ({file_size_kb} KB)")
    print(f"  MIME     : {content_type}")

    # ── Phase 2 Einstiegspunkt ────────────────────────────────────────────
    # Ersetze diesen Block wenn Whisper + GPT bereit sind:
    #
    #   transcript = await run_whisper(save_path)
    #   result     = await run_gpt(transcript, template)
    #   await send_to_google_docs(result)
    #
    stub_response = (
        f"[Phase 1] Audio empfangen ✓ — "
        f"Template '{template}' ausgewählt. "
        f"Whisper kommt in Phase 2."
    )
    # ─────────────────────────────────────────────────────────────────────

    return JSONResponse({
        "job_id":        job_id,
        "template":      template,
        "file_size_kb":  file_size_kb,
        "stub_response": stub_response,
    })
