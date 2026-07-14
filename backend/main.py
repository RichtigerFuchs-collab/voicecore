import json
import os
import re
import secrets
import uuid
from datetime import datetime, date
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="VoiceCore API", version="0.8.0")

# ─── Template-Prompts ─────────────────────────────────────────────────────────

TEMPLATE_PROMPTS = {
    "tagebuch": (
        "Du bist ein empathischer Tagebuch-Assistent. Deine Aufgabe ist es, gesprochene Gedanken "
        "in eine strukturierte, schriftliche Form zu bringen.\n\n"
        "Datum heute: {date}\n"
        "Verfasser:in des Eintrags: {speaker}\n\n"
        "Regeln:\n"
        "- Tonalität: Behalte den persönlichen Stil der sprechenden Person bei. Bleib nah an "
        "ihren emotionalen Originalformulierungen – besonders gefühlvolle oder markante Sätze "
        "dürfen (leicht geglättet) wörtlich erhalten bleiben. Lieber die eigenen Worte der "
        "Person als neutrale Umschreibungen. Schreibe in der Ich-Form.\n"
        "- Struktur: Gliedere den Text in drei logische Abschnitte: "
        "Was war los? (Ereignisse), Wie war es? (Emotionen & Atmosphäre), "
        "Gedanken danach (Reflexion & Erkenntnis).\n"
        "- Bereinigung: Entferne Füllwörter (äh, hm, halt, quasi), Wiederholungen und "
        "Satzkorrekturen, ohne den Sinn zu verändern.\n"
        "- Datum der Titelzeile: Wenn im Transkript ein konkretes Datum oder ein relativer "
        "Bezug genannt wird (z.B. 'am 8. Juli', 'gestern', 'letzten Samstag'), berechne das "
        "gemeinte Datum ausgehend von heute ({date}) und verwende es in der Titelzeile. "
        "Nur wenn nichts genannt wird oder 'heute' gesagt wird, nimm das heutige Datum.\n"
        "- Sprache: Antworte in der Sprache des Inputs (Deutsch oder Englisch).\n"
        "- Kein Markdown: Reiner Text ohne ## oder ** – der Eintrag landet in einem Google Doc.\n\n"
        "Output-Format (die erste Zeile exakt so aufbauen – Datum zuerst, dann Titel, "
        "dann Name in Klammern):\n"
        "[Datum, z.B. {date}] – [Titel der Notiz, kreativ & passend] ({speaker})\n\n"
        "Was war los?\n[Text]\n\n"
        "Wie war es?\n[Text]\n\n"
        "Gedanken danach\n[Text]"
    ),
    "quick_note": (
        "Du bist ein hocheffizienter Notiz-Assistent für Business und kreative Ideen. "
        "Deine Aufgabe ist es, schnelle Sprachnotizen in ein strukturiertes Protokoll zu verwandeln.\n\n"
        "Struktur:\n"
        "- **TL;DR:** Ein bis zwei prägnante Sätze als Zusammenfassung ganz oben.\n"
        "- **Kernaussagen:** Stichpunkte mit kurzen, erklärenden Sätzen (keine bloßen Schlagworte).\n"
        "- **Action Items:** Falls Aufgaben oder nächste Schritte erkennbar sind, liste diese separat auf.\n"
        "- **Tags:** Generiere 3–5 relevante Hashtags am Ende (z.B. #ProjectA, #Idea, #Meeting).\n\n"
        "Besonderheit: Wenn der Input ein Mix aus Deutsch und Englisch ist, erstelle die "
        "Zusammenfassung in der dominanten Sprache, halte aber Fachbegriffe im Original fest."
    ),
    "restaurant_review": (
        "Du wandelst gesprochene Eindrücke nach einem Restaurantbesuch in eine strukturierte "
        "Bewertung um. Halte dich exakt an das Layout des folgenden Beispiels: passendes "
        "Essens-Emoji vor dem Restaurantnamen, Sterne mit ⭐️ (½ für halbe Sterne) auf eigener "
        "Zeile, danach 1–2 Sätze pro Kategorie. Kein Markdown – reiner Text.\n\n"
        "Beispiel-Layout:\n"
        "🍝 DA's Lupo – Köln (Juni 2025)\n"
        "1. Essen – Geschmack & Qualität:\n"
        "⭐️⭐️⭐️⭐️½\n"
        "Sehr, sehr lecker! Besonders die Pasta mit Pilzen und Tomate-Burrata sowie die "
        "überbackenen Ravioli haben euch überzeugt.\n"
        "2. Ambiente – Atmosphäre & Einrichtung:\n"
        "⭐️⭐️⭐️⭐️\n"
        "Ihr habt draußen gesessen, innen war es aber ebenfalls sehr schön. Wie gewohnt bei "
        "Massimo: gemütlich und stimmungsvoll.\n"
        "3. Service – Freundlichkeit & Aufmerksamkeit:\n"
        "⭐️⭐️⭐️\n"
        "Aufmerksam, aber etwas zu flott im Servieren – das wirkte leicht gehetzt.\n"
        "4. Preis-Leistung – Gefühl für den Wert des Essens:\n"
        "⭐️⭐️⭐️⭐️⭐️\n"
        "Top! 80 € für zwei Hauptgerichte, eine Vorspeise und eine Flasche Wein – sogar "
        "günstiger als das Tarnika.\n"
        "5. Besonderheit – Einzigartigkeit oder Erinnerungspotenzial:\n"
        "⭐️⭐️⭐️⭐️\n"
        "Die in Tempura gebackene Zucchini-Vorspeise war ein echtes Highlight. Außerdem eine "
        "schöne Unterhaltung mit dem Nebentisch.\n\n"
        "Regeln:\n"
        "- Erste Zeile: Emoji passend zur Küche, Restaurantname, Stadt (falls genannt), "
        "dahinter in Klammern: ({month_year})\n"
        "- Alle fünf Kategorien in dieser Reihenfolge. Wird ein Aspekt gar nicht erwähnt, "
        "lasse die Kategorie weg.\n"
        "- Anrede wie im Beispiel (ihr/euch), wenn mehrere Personen dabei waren – sonst du-Form.\n"
        "- Sternebewertungen aus dem Transkript ableiten, halbe Sterne mit ½.\n"
        "- Sprache des Inputs verwenden."
    ),
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Shared Secret für /upload. Nicht gesetzt (lokal / vor Einrichtung auf Render)
# → Prüfung aus, App verhält sich wie bisher. Gesetzt → Header X-App-Secret Pflicht.
APP_SECRET = os.environ.get("APP_SECRET", "")

GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_DOCS_SCOPES = ["https://www.googleapis.com/auth/documents"]

TEMPLATE_LABELS = {
    "tagebuch":          "Tagebuch",
    "quick_note":        "Quick Note",
    "restaurant_review": "Restaurant Review",
}

# Deutsche Monatsnamen, unabhängig vom Server-Locale.
# (strftime "%-d" crasht unter Windows, "%B" liefert auf Render Englisch.)
GERMAN_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

def format_german_date(d: date) -> str:
    return f"{d.day}. {GERMAN_MONTHS[d.month - 1]} {d.year}"


class VoiceResult(BaseModel):
    """Strukturierte Antwort des kombinierten Gemini-Calls."""
    transcript: str
    formatted: str
    markdown: str


# ─── Obsidian: Markdown-Vorgaben pro Template ─────────────────────────────────
# Die Einträge werden an BESTEHENDE Sammel-Dateien angehängt, die bereits ein
# YAML-Frontmatter am Dateianfang haben. Deshalb KEIN Frontmatter pro Eintrag –
# ein zweites "---" mitten in der Datei würde Obsidian als Trennlinie rendern.
# Jeder Eintrag beginnt mit einer "## "-Überschrift, exakt wie im Vault üblich.

MARKDOWN_RULES = {
    "tagebuch": (
        "Erzeuge den Eintrag für die Obsidian-Datei 'K&K Tagebuch.md'.\n"
        "Format (exakt so, kein YAML-Frontmatter!):\n"
        "## [Datum] – [Titel] ({speaker})\n\n"
        "### Was war los?\n\n[Text]\n\n"
        "### Wie war es?\n\n[Text]\n\n"
        "### Gedanken danach\n\n[Text]\n\n"
        "Inhaltlich identisch zum Feld 'formatted' – nur mit Markdown-Überschriften. "
        "Datum wie in 'formatted' (also ggf. das im Audio genannte Datum)."
    ),
    "quick_note": (
        "Erzeuge den Eintrag für die Obsidian-Datei 'inbox.md'.\n"
        "Format (exakt so, kein YAML-Frontmatter!):\n"
        "## {date} – [Kurzer Titel] ({speaker})\n\n"
        "**TL;DR:** [ein bis zwei Sätze]\n\n"
        "### Kernaussagen\n"
        "- [Stichpunkt]\n\n"
        "### Action Items\n"
        "- [ ] [Aufgabe]\n\n"
        "(Abschnitt 'Action Items' nur, wenn Aufgaben erkennbar sind – als "
        "Obsidian-Checkboxen mit '- [ ]'.)\n\n"
        "Zum Schluss eine Zeile mit 3–5 Hashtags, z.B.: #idee #projekt"
    ),
    "restaurant_review": (
        "Erzeuge den Eintrag für die Obsidian-Datei 'Restaurant-Reviews.md'.\n"
        "Format (exakt so, kein YAML-Frontmatter!):\n"
        "## [Emoji] [Restaurantname] – [Stadt] ({month_year})\n\n"
        "1. Essen – Geschmack & Qualität:  \n"
        "⭐️⭐️⭐️⭐️½  \n"
        "[Beschreibung]\n\n"
        "(... alle fünf Kategorien wie im Feld 'formatted', gleiche Sterne, "
        "gleiche Texte. Am Zeilenende jeweils zwei Leerzeichen für den "
        "Markdown-Zeilenumbruch.)\n\n"
        "Zum Schluss eine Zeile mit Hashtags, immer beginnend mit #restaurant, "
        "z.B.: #restaurant #italienisch #köln"
    ),
}


# Die App wird von Kim und Kathrin genutzt – Gemini verschreibt sich sonst gern (Katrin/Katrien).
NAME_SPELLING_RULE = (
    "Wichtig – Schreibweise von Namen: Die sprechenden bzw. erwähnten Personen heißen "
    "Kim und Kathrin (Kathrin immer mit 'th', niemals 'Katrin'). Schreibe diese Namen exakt so."
)

TRANSCRIBE_ONLY_PROMPT = (
    "Transkribiere dieses Audio exakt. Gib nur den gesprochenen Text zurück, "
    "ohne Kommentare oder Erklärungen.\n\n"
    f"{NAME_SPELLING_RULE}"
)

def build_combined_prompt(template_prompt: str, markdown_rule: str) -> str:
    """Ein Call statt drei: Transkription + Google-Doc-Text + Obsidian-Markdown."""
    return (
        "Du erhältst eine Audio-Sprachnachricht. Erledige drei Aufgaben und antworte "
        "als JSON mit den Feldern \"transcript\", \"formatted\" und \"markdown\":\n\n"
        "1. \"transcript\": Transkribiere das Audio exakt. Nur der gesprochene Text, "
        "ohne Kommentare oder Erklärungen.\n\n"
        "2. \"formatted\": Verarbeite den transkribierten Text nach folgender Anweisung. "
        "Dieser Text geht in ein Google Doc – REINER TEXT ohne Markdown-Zeichen:\n\n"
        f"{template_prompt}\n\n"
        "3. \"markdown\": Derselbe Inhalt wie in \"formatted\", aber als Markdown für "
        "Obsidian aufbereitet:\n\n"
        f"{markdown_rule}\n\n"
        f"{NAME_SPELLING_RULE} Das gilt für alle drei Felder."
    )

# ─── Google Docs Helpers ───────────────────────────────────────────────────────

def extract_doc_id(url: str) -> str | None:
    """Extrahiert die Google Docs Document-ID aus einer URL. Gibt None zurück wenn kein Match."""
    if not url:
        return None
    match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def write_to_google_doc(doc_id: str, template: str, formatted_text: str) -> bool:
    """Fügt einen neuen Eintrag am Anfang des Google Docs ein. Gibt True bei Erfolg zurück."""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print("[Docs] GOOGLE_SERVICE_ACCOUNT_JSON nicht gesetzt – übersprungen")
        return False

    try:
        sa_info     = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            sa_info, scopes=GOOGLE_DOCS_SCOPES,
        )
        service  = build("docs", "v1", credentials=credentials)

        label    = TEMPLATE_LABELS.get(template, template)
        now      = datetime.now()
        date_str = format_german_date(now.date())
        time_str = now.strftime("%H:%M")

        separator = "────────────────────────────────────"
        content   = f"{separator}\n{label} · {date_str} · {time_str}\n\n{formatted_text}\n\n\n"

        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

        print(f"[Docs] Geschrieben in Doc {doc_id[:8]}...")
        return True

    except json.JSONDecodeError as e:
        print(f"[Docs] Ungültiges GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
        return False
    except HttpError as e:
        print(f"[Docs] Google API Fehler {e.status_code}: {e.reason}")
        return False
    except Exception as e:
        print(f"[Docs] Unerwarteter Fehler: {e}")
        return False


# ─── Obsidian-Postfach ────────────────────────────────────────────────────────
# Warum ein Google DOC als Postfach und keine .md-Datei in Google Drive?
# Service Accounts haben KEIN eigenes Drive-Kontingent und können in einem
# normalen (Consumer-)Google-Drive keine Dateien anlegen – jeder Upload
# scheitert mit storageQuotaExceeded. In ein Doc, das Kim gehört, dürfen sie
# aber Text einfügen. Deshalb: Markdown-Blöcke sammeln sich in einem Postfach-
# Doc, das lokale Skript tools/obsidian_sync.py holt sie ab und leert es.

QUEUE_BEGIN = "<<<VOICECORE"
QUEUE_END   = "<<<ENDE>>>"

def append_to_obsidian_queue(doc_id: str, template: str, speaker: str, markdown: str) -> bool:
    """Hängt einen Markdown-Block ans ENDE des Postfach-Docs. True bei Erfolg."""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print("[Queue] GOOGLE_SERVICE_ACCOUNT_JSON nicht gesetzt – übersprungen")
        return False

    try:
        sa_info     = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            sa_info, scopes=GOOGLE_DOCS_SCOPES,
        )
        service = build("docs", "v1", credentials=credentials)

        # Ans Ende anhängen (nicht oben einfügen) – der Abholer arbeitet die
        # Einträge in der Reihenfolge ab, in der sie eingesprochen wurden.
        doc      = service.documents().get(documentId=doc_id).execute()
        end_idx  = doc["body"]["content"][-1]["endIndex"] - 1

        stamp = datetime.now().isoformat(timespec="seconds")
        block = (
            f"\n{QUEUE_BEGIN}|{template}|{speaker}|{stamp}>>>\n"
            f"{markdown}\n"
            f"{QUEUE_END}\n"
        )

        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": end_idx}, "text": block}}]},
        ).execute()

        print(f"[Queue] Markdown-Block ins Postfach gelegt ({template})")
        return True

    except HttpError as e:
        print(f"[Queue] Google API Fehler {e.status_code}: {e.reason}")
        return False
    except Exception as e:
        print(f"[Queue] Unerwarteter Fehler: {e}")
        return False

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {
        "status":  "ok",
        "version": app.version,
        "gemini":  bool(GEMINI_API_KEY),
        "model":   GEMINI_MODEL,
    }


@app.post("/upload")
async def upload_audio(
    audio: UploadFile = File(...),
    template: str = Form(...),
    destination_url: str = Form(default=""),
    speaker: str = Form(default=""),
    obsidian_queue_url: str = Form(default=""),
    x_app_secret: str = Header(default=""),
):
    # Zugriffsschutz – VOR jeder Verarbeitung und jedem Gemini-Call
    if APP_SECRET and not secrets.compare_digest(x_app_secret, APP_SECRET):
        raise HTTPException(status_code=401, detail="Falsches oder fehlendes App-Passwort")

    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Audio-Datei erwartet, erhalten: {content_type}"
        )

    job_id      = str(uuid.uuid4())
    audio_bytes = await audio.read()
    speaker     = speaker.strip() or "unbekannt"

    file_size_kb = round(len(audio_bytes) / 1024, 1)

    print(f"[VoiceCore] Job: {job_id} | Template: {template} | Sprecher:in: {speaker} | {file_size_kb} KB | {content_type}")

    # ── Transkription + Formatierung + Markdown in EINEM Gemini-Call ──────
    transcript = None
    formatted  = None
    markdown   = None

    if not gemini_client:
        transcript = "[GEMINI_API_KEY fehlt – bitte in Render setzen]"
    else:
        # Codec-Parameter abschneiden: "audio/webm;codecs=opus" → "audio/webm"
        mime_type  = content_type.split(";")[0].strip()
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

        prompt_template = TEMPLATE_PROMPTS.get(template)
        markdown_rule   = MARKDOWN_RULES.get(template)
        try:
            if prompt_template and markdown_rule:
                today      = date.today()
                fmt_kwargs = dict(
                    date=format_german_date(today),
                    speaker=speaker,
                    month_year=f"{GERMAN_MONTHS[today.month - 1]} {today.year}",
                )
                prompt = build_combined_prompt(
                    prompt_template.format(**fmt_kwargs),
                    markdown_rule.format(**fmt_kwargs),
                )
                response = gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[audio_part, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=VoiceResult,
                    ),
                )
                result = response.parsed
                if result is None:
                    raise ValueError("Gemini lieferte kein gültiges JSON")
                transcript = result.transcript.strip()
                formatted  = result.formatted.strip()
                markdown   = result.markdown.strip()
                print(f"  Transkript: {transcript[:80]}...")
                print(f"  Formatiert ({template}): {formatted[:80]}...")
                print(f"  Markdown ({template}): {markdown[:80]}...")
            else:
                response = gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[audio_part, TRANSCRIBE_ONLY_PROMPT],
                )
                transcript = response.text.strip()
                print(f"  Transkript: {transcript[:80]}...")
        except Exception as e:
            print(f"  Fehler bei Verarbeitung: {e}")
            transcript = f"[Fehler bei Transkription: {e}]"
            formatted  = None
            markdown   = None
    # ── Google Docs Write ──────────────────────────────────────────────────
    doc_written = False
    if destination_url and formatted:
        doc_id = extract_doc_id(destination_url)
        if doc_id:
            doc_written = write_to_google_doc(doc_id, template, formatted)
        else:
            print(f"[Docs] Konnte Doc-ID nicht aus URL extrahieren: {destination_url}")

    # ── Obsidian-Postfach ──────────────────────────────────────────────────
    queued_for_obsidian = False
    if obsidian_queue_url and markdown:
        queue_id = extract_doc_id(obsidian_queue_url)
        if queue_id:
            queued_for_obsidian = append_to_obsidian_queue(queue_id, template, speaker, markdown)
        else:
            print(f"[Queue] Konnte Doc-ID nicht aus URL extrahieren: {obsidian_queue_url}")
    # ─────────────────────────────────────────────────────────────────────

    return JSONResponse({
        "job_id":              job_id,
        "template":            template,
        "file_size_kb":        file_size_kb,
        "transcript":          transcript,
        "formatted":           formatted,
        "markdown":            markdown,
        "doc_written":         doc_written,
        "queued_for_obsidian": queued_for_obsidian,
    })

# ─── Frontend (Production) ────────────────────────────────────────────────────
# Muss nach allen API-Routen stehen, damit /health und /upload Vorrang haben.

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
