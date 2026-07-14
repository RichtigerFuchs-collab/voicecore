"""
VoiceCore → Obsidian: Abholer für das Postfach-Doc.

Holt alle Markdown-Blöcke aus dem Postfach-Google-Doc, hängt sie an die drei
Vault-Dateien an und leert danach das Postfach.

  Tagebuch          → Tagebuch & Reiseberichte/K&K Tagebuch.md   (oben)
  Quick Note        → 00_Inbox/inbox.md                          (oben)
  Restaurant Review → Reviews/Restaurant-Reviews.md              (vor "Verknüpft")

Einrichtung:
  1. obsidian_sync.config.example.json  →  obsidian_sync.config.json kopieren
  2. Darin die drei Pfade/URLs eintragen (Service-Account-JSON, Postfach-Doc, Vault)
  3. Testlauf:  python tools/obsidian_sync.py
  4. Automatisieren: Windows-Aufgabenplanung, z.B. alle 15 Min oder beim Anmelden

Das Skript ist idempotent und sicher: Erst wenn ALLE Blöcke erfolgreich ins
Vault geschrieben wurden, wird das Postfach geleert. Schlägt etwas fehl,
bleibt das Postfach unangetastet – kein Eintrag geht verloren.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/documents"]

QUEUE_BEGIN_RE = re.compile(r"<<<VOICECORE\|([^|]+)\|([^|]*)\|([^>]*)>>>")
QUEUE_END      = "<<<ENDE>>>"

# Template → (Pfad im Vault, Einfüge-Strategie)
#   "top"           = direkt nach dem YAML-Frontmatter (neueste Einträge oben)
#   "before_links"  = vor dem abschließenden "## 🔗 Verknüpft"-Block
TARGETS = {
    "tagebuch":          ("Tagebuch & Reiseberichte/K&K Tagebuch.md", "top"),
    "quick_note":        ("00_Inbox/inbox.md",                        "top"),
    "restaurant_review": ("Reviews/Restaurant-Reviews.md",            "before_links"),
}

FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
HEADING_RE     = re.compile(r"^## ", re.MULTILINE)


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "obsidian_sync.config.json"
    if not cfg_path.exists():
        sys.exit(
            f"Keine Konfiguration gefunden: {cfg_path}\n"
            "→ obsidian_sync.config.example.json kopieren und ausfüllen."
        )
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def extract_doc_id(url_or_id: str) -> str:
    match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url_or_id)
    return match.group(1) if match else url_or_id.strip()


def read_doc_text(service, doc_id: str) -> tuple[str, int]:
    """Gibt (Volltext, end_index) des Docs zurück."""
    doc  = service.documents().get(documentId=doc_id).execute()
    body = doc["body"]["content"]

    text = []
    for element in body:
        for run in element.get("paragraph", {}).get("elements", []):
            text.append(run.get("textRun", {}).get("content", ""))

    return "".join(text), body[-1]["endIndex"] - 1


def parse_blocks(text: str) -> list[dict]:
    """Zerlegt den Postfach-Text in Einträge."""
    blocks = []
    for match in QUEUE_BEGIN_RE.finditer(text):
        template, speaker, stamp = match.groups()
        rest = text[match.end():]
        end  = rest.find(QUEUE_END)
        if end == -1:
            print(f"  ! Block ohne Ende-Marker ({template}) – übersprungen")
            continue
        blocks.append({
            "template": template.strip(),
            "speaker":  speaker.strip(),
            "stamp":    stamp.strip(),
            "markdown": rest[:end].strip(),
        })
    return blocks


def insert_into_vault(vault: Path, block: dict) -> bool:
    target = TARGETS.get(block["template"])
    if not target:
        print(f"  ! Unbekanntes Template '{block['template']}' – übersprungen")
        return False

    rel_path, strategy = target
    file_path = vault / rel_path
    if not file_path.exists():
        print(f"  ! Datei fehlt: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")
    entry   = block["markdown"].strip() + "\n\n"

    if entry.strip() in content:
        print(f"  = Bereits vorhanden ({block['template']}) – übersprungen")
        return True

    if strategy == "before_links":
        # Vor den abschließenden Verknüpfungs-Block (falls vorhanden), sonst ans Ende
        marker = content.find("---\n## 🔗 Verknüpft")
        if marker == -1:
            marker = content.find("## 🔗 Verknüpft")
        new_content = (
            content[:marker] + entry + content[marker:] if marker != -1
            else content.rstrip() + "\n\n" + entry
        )
    else:  # "top" – neuester Eintrag zuerst, aber unter einem evtl. Intro-Text
        fm  = FRONTMATTER_RE.match(content)
        cut = fm.end() if fm else 0
        # Vor der ersten "## "-Überschrift einfügen. Gibt es noch keine
        # (frische Datei mit nur Frontmatter + Intro), kommt der Eintrag ans Ende.
        heading = HEADING_RE.search(content, cut)
        pos = heading.start() if heading else len(content)
        new_content = (
            content[:pos].rstrip("\n") + "\n\n" + entry + content[pos:]
            if heading
            else content.rstrip("\n") + "\n\n" + entry
        )

    # Frontmatter-Feld "aktualisiert" mitziehen, falls vorhanden
    new_content = re.sub(
        r"(\Aaktualisiert:\s*)\S+|(?<=\n)(aktualisiert:\s*)\S+",
        lambda m: (m.group(1) or m.group(2)) + datetime.now().strftime("%Y-%m-%d"),
        new_content,
        count=1,
    )

    file_path.write_text(new_content, encoding="utf-8")
    print(f"  + {block['template']} → {rel_path}")
    return True


def clear_queue(service, doc_id: str, end_index: int) -> None:
    if end_index <= 1:
        return
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": end_index}
            }
        }]},
    ).execute()


def main() -> None:
    cfg   = load_config()
    vault = Path(cfg["vault_path"])
    if not vault.exists():
        sys.exit(f"Vault-Pfad nicht gefunden: {vault}")

    credentials = service_account.Credentials.from_service_account_file(
        cfg["service_account_file"], scopes=SCOPES,
    )
    service = build("docs", "v1", credentials=credentials)
    doc_id  = extract_doc_id(cfg["queue_doc_url"])

    text, end_index = read_doc_text(service, doc_id)
    blocks = parse_blocks(text)

    if not blocks:
        print("Postfach ist leer – nichts zu tun.")
        return

    print(f"{len(blocks)} Eintrag/Einträge im Postfach:")
    all_ok = all(insert_into_vault(vault, b) for b in blocks)

    if all_ok:
        clear_queue(service, doc_id, end_index)
        print("Postfach geleert. Fertig.")
    else:
        print(
            "\nMindestens ein Eintrag konnte nicht geschrieben werden – "
            "das Postfach bleibt unverändert, damit nichts verloren geht."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
