# Prüfung der Tagebuchverarbeitung

## Lokale Regression

Vom Repository-Root in einer Python-Umgebung mit den bestehenden `requirements.txt`:

```sh
python -m unittest discover -s tests -v
```

`test_diary.py` verwendet echte SDK-Antworttypen mit simulierten Modellantworten. Geprüft werden alle möglichen KI-Stufen, Erhalt des vollständigen Referenztranskripts, Audit/Korrektur, Ausgabelimit und Safety-Abbruch, leere/ungültige Ergebnisse sowie identischer Inhalt beider Exporte. `test_diary_api.py` prüft die HTTP-Grenze, Exportschutz, Zugriffsschutz, Worker-Ausführung und die bisherigen anderen Vorlagen. Alle Modell- und Exportaufrufe sind ersetzt; keine privaten Daten und keine API-Kosten.

Diese Tests beweisen den Verarbeitungspfad. Sie beweisen nicht, dass Gemini bei echten Aufnahmen zuverlässig alle Inhalte erkennt.

## Browser-Regression

Das gebaute Frontend lokal über `uvicorn main:app --host 127.0.0.1 --port 8765` starten. Mit lokal verfügbarem Playwright und dessen Chromium-Browser:

```sh
VOICECORE_BASE_URL=http://127.0.0.1:8765 node tests/frontend-retry.cjs
```

Falls Playwright außerhalb des Projekts installiert ist, `VOICECORE_PLAYWRIGHT_PATH` auf dessen Modulpfad setzen. `PLAYWRIGHT_BROWSERS_PATH` kann auf eine isolierte Browserinstallation zeigen. Playwright wird nur als Testwerkzeug benötigt und ist keine Runtime-Abhängigkeit der App.

Die sechs Szenarien prüfen Sicherung vor HTTP, Fehlermeldung und Retry mit ursprünglichen Metadaten, Reload während Verarbeitung, fehlgeschlagene Speicherung, lokale Löschfehler mit erfolgtem Export, Ladefehler und ein gültiges Transkript mit einer öffnenden Klammer. Alle Upload- und Health-Anfragen werden abgefangen; andere externe Anfragen sind blockiert. Synthetisches Audio stammt aus dem Testbrowser.

**Lokaler Nachweis am 10.10.2026:** 17 Python-Tests mit Unterfällen, sechs Browser-Szenarien, Frontend-Produktionsbuild und `git diff --check`. Modellantworten und Exporte wurden simuliert. Eine fachliche Abnahme mit echten Modellantworten steht aus.

## Fachliche Abnahme vor dem Live-Einsatz

Ein geprüftes Referenztranskript und eine Liste aller bedeutungstragenden Inhalte vor der Generierung festhalten. Zuerst mit synthetischen Inhalten und leeren Exportzielen in einer Testumgebung prüfen. Das benötigt einen eingerichteten Gemini-Zugang und die Freigabe für dessen Nutzung. Eigene Aufnahmen anschließend bewusst auswählen; keine ungefragte Übertragung privater Vault-Inhalte.

| Fall | Was erhalten bleiben muss |
| --- | --- |
| Mehrere Themen | Jedes Thema mit seinen Details, auch ein kurzer Nebenblock zwischen langen Erzählungen |
| Ausführliche Reflexion | Anlass, Gedankenverlauf, Gefühle, Zweifel, Begründung und Schlussfolgerung |
| Anekdote | Die konkrete Szene mit Beteiligten, Ort und erinnerungswürdigen Details |
| Mehr Details zum selben Thema | Zusätzliche Inhalte erscheinen im Ergebnis, statt auf dieselbe Kurzfassung zurückzufallen |
| Bereinigung und Selbstkorrektur | Füllwörter/Dopplungen entfallen, korrigierte Aussagen gelten, emotionale Wiederholungen bleiben |
| Lange Aufnahme | Anfang, Mitte und Ende bleiben vertreten; kein stiller Erfolg bei technischer Begrenzung |

Als kurzes synthetisches Beispiel dient `TRANSCRIPT` in `test_diary.py`: Rhein, alte Brücke, Serviette im Wasser, Lachen, Anruf bei Alex, Grund des Anrufs, Angst und veränderte Überlegung, Erleichterung mit verbleibendem Zweifel, Selbstkorrektur von Pilzen zu Zucchini, grüner Schal im Café als letztes Detail. In der echten Modellabnahme jedes Element einzeln prüfen. Eine zweite Variante ergänzt konkrete Details zum selben Erlebnis. Für die lange Variante mehrere eigenständige Themen mit Details am Anfang, in der Mitte und am Ende einsprechen.

Zusätzlich prüfen:

- Datum und Name, insbesondere Kathrin mit `th`, stimmen.
- Google-Docs-Text und Obsidian-Markdown unterscheiden sich nur in der Formatierung.
- Fehler zeigen eine verständliche Ursache, exportieren nichts und lassen die Aufnahme erneut senden.
- Nach Schließen/Reload während Verarbeitung bleibt die Aufnahme verfügbar; Retry verwendet ursprüngliche Vorlage und Sprecher.
- Eine offene Aufnahme wird durch eine neue Aufnahme nicht überschrieben.
- Ein lokaler Löschfehler nach erfolgreicher Verarbeitung löst nur lokales Entfernen aus, keinen weiteren Upload.

Wartezeit und Modellverbrauch getrennt vom Inhalt beurteilen. Die Pipeline verwendet drei Aufrufe im Normalfall und fünf mit Korrektur. Eine bestandene Inhaltsprüfung ist kein Beweis für eine fehlerfreie Transkription. Bei verloren gegangener HTTP-Erfolgsantwort kann ein späterer Retry mangels serverseitiger Idempotenz weiterhin doppelte Exporte auslösen.
