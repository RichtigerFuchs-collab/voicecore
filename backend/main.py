import os
import uuid
import shutil
from pathlib import Path

import google.generativeai as genai
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="VoiceCore API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("/tmp/voicecore_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "gemini": bool(GEMINI_API_KEY), "model": GEMINI_MODEL}


@app.post("/upload")
async def upload_audio(
    audio: UploadFile = File(...),
    template: str = Form(...),
):
    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Audio-Datei erwartet, erhalten: {content_type}"
        )

    job_id    = str(uuid.uuid4())
    suffix    = Path(audio.filename or "recording.webm").suffix or ".webm"
    save_path = UPLOAD_DIR / f"{job_id}{suffix}"

    with save_path.open("wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    file_size_kb = round(save_path.stat().st_size / 1024, 1)

    print(f"[VoiceCore] Job: {job_id} | Template: {template} | {file_size_kb} KB | {content_type}")

    # ── Transkription via Gemini ───────────────────────────────────────────
    if not GEMINI_API_KEY:
        transcript = "[GEMINI_API_KEY fehlt – bitte in Render setzen]"
    else:
        try:
            uploaded_file = genai.upload_file(path=str(save_path), mime_type=content_type)
            model         = genai.GenerativeModel(GEMINI_MODEL)
            response      = model.generate_content([
                uploaded_file,
                "Transkribiere dieses Audio exakt. Gib nur den gesprochenen Text zurück, ohne Kommentare oder Erklärungen.",
            ])
            transcript = response.text.strip()
            genai.delete_file(uploaded_file.name)
            print(f"  Transkript: {transcript[:80]}...")
        except Exception as e:
            print(f"  Fehler: {e}")
            transcript = f"[Fehler bei Transkription: {e}]"

    save_path.unlink(missing_ok=True)
    # ─────────────────────────────────────────────────────────────────────

    return JSONResponse({
        "job_id":      job_id,
        "template":    template,
        "file_size_kb": file_size_kb,
        "transcript":  transcript,
    })
