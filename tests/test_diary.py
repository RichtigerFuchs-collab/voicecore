"""Pipeline regression tests with synthetic content and real SDK response types."""

import json
import unittest
from unittest.mock import Mock

from google.genai import types

from backend.diary import (
    MAX_OUTPUT_TOKENS, DiaryAudit, DiaryDraft, DiaryProcessingError,
    diary_to_markdown, process_diary,
)
from backend.main import NAME_SPELLING_RULE, TEMPLATE_PROMPTS, TRANSCRIBE_ONLY_PROMPT


TRANSCRIPT = (
    "Gestern war ich mit Kathrin am Rhein. Wir saßen neben der alten Brücke. "
    "Der Wind hat ihre Serviette ins Wasser geweht und wir mussten beide lachen. "
    "Danach rief ich Alex an, weil mich unser Streit beschäftigt hat. "
    "Ich war erleichtert, aber noch unsicher, ob wir uns verstanden hatten. "
    "Ich wollte zuerst nicht anrufen, weil ich Angst vor einem weiteren Streit hatte. "
    "Dann dachte ich, dass Schweigen das Problem auch nicht löst. "
    "Abends gab es Nudeln mit Pilzen, nein, mit Zucchini. "
    "Fast vergessen: Auf dem Heimweg habe ich den grünen Schal im Café abgeholt."
)
FORMATTED = (
    "9. Oktober 2026 – Wind am Rhein (Kathrin)\n\n"
    "Was war los?\nIch war mit Kathrin am Rhein neben der alten Brücke. "
    "Der Wind wehte ihre Serviette ins Wasser und wir mussten beide lachen.\n\n"
    "Ich rief Alex an, weil mich unser Streit beschäftigt hat. "
    "Abends gab es Nudeln mit Zucchini. Auf dem Heimweg holte ich den grünen Schal im Café ab.\n\n"
    "Wie war es?\nIch war erleichtert, aber noch unsicher, ob wir uns verstanden hatten.\n\n"
    "Gedanken danach\nIch wollte zuerst nicht anrufen, weil ich Angst vor einem weiteren Streit hatte. "
    "Dann dachte ich, dass Schweigen das Problem auch nicht löst."
)
SHORT_DRAFT = "9. Oktober 2026 – Ein schöner Tag (Kathrin)\n\nWas war los?\nEs war ein schöner Tag."


def response(text=None, parsed=None, reason="STOP", candidates=True):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(parts=[types.Part.from_text(text=text or "")]),
            finish_reason=reason,
        )] if candidates else [],
        parsed=parsed,
    )


def clean_audit():
    return response(parsed=DiaryAudit(
        missing_contents=[], distorted_contents=[], unsupported_contents=[]))


class DiaryPipelineTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.audio = types.Part.from_bytes(data=b"audio fixture", mime_type="audio/webm")
        self.prompt = TEMPLATE_PROMPTS["tagebuch"].format(
            date="10. Oktober 2026", speaker="Kathrin") + "\n" + NAME_SPELLING_RULE
        self.good = [response(text=TRANSCRIPT), response(parsed=DiaryDraft(formatted=FORMATTED)),
                     clean_audit()]

    def run_pipeline(self, responses):
        self.client.models.generate_content.side_effect = responses
        return process_diary(self.client, "gemini-3.1-flash-lite", self.audio,
                             self.prompt, TRANSCRIBE_ONLY_PROMPT)

    def test_full_transcript_reaches_draft_and_audit_without_a_word_limit(self):
        transcript, formatted, markdown = self.run_pipeline(self.good)
        self.assertEqual(transcript, TRANSCRIPT)
        self.assertEqual(formatted, FORMATTED)
        calls = self.client.models.generate_content.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].kwargs["contents"], [self.audio])
        self.assertEqual(json.loads(calls[1].kwargs["contents"])["transcript"], TRANSCRIPT)
        audit_data = json.loads(calls[2].kwargs["contents"])
        self.assertEqual(audit_data["transcript"], TRANSCRIPT)
        self.assertEqual(audit_data["formatted"], FORMATTED)
        self.assertIn("grünen Schal", audit_data["transcript"])
        self.assertEqual(markdown.removeprefix("## ").replace("\n### ", "\n"), formatted)
        for call in calls:
            self.assertEqual(call.kwargs["config"].max_output_tokens, MAX_OUTPUT_TOKENS)
        self.assertIn("Kathrin", calls[0].kwargs["config"].system_instruction)
        self.assertIn("Kathrin", calls[1].kwargs["config"].system_instruction)
        self.assertIn("Kathrin", audit_data["context"])

    def test_missing_distorted_or_invented_content_is_repaired_then_reaudited(self):
        for kind in ("missing_contents", "distorted_contents", "unsupported_contents"):
            with self.subTest(kind=kind):
                issues = {"missing_contents": [], "distorted_contents": [], "unsupported_contents": []}
                issues[kind] = ["Schal, Anruf oder Gefühl nicht originalgetreu"]
                result = self.run_pipeline([
                    self.good[0], response(parsed=DiaryDraft(formatted=SHORT_DRAFT)),
                    response(parsed=DiaryAudit(**issues)),
                    response(parsed=DiaryDraft(formatted=FORMATTED)), clean_audit(),
                ])
                self.assertEqual(result[1], FORMATTED)
                calls = self.client.models.generate_content.call_args_list[-5:]
                repair = json.loads(calls[3].kwargs["contents"])
                self.assertEqual(repair["transcript"], TRANSCRIPT)
                self.assertEqual(repair["issues"], issues)
                self.assertEqual(json.loads(calls[4].kwargs["contents"])["formatted"], FORMATTED)

    def test_single_line_draft_is_format_repaired_before_clean_audit(self):
        single_line = FORMATTED.replace("\n", " ")
        result = self.run_pipeline([
            self.good[0], response(parsed=DiaryDraft(formatted=single_line)),
            self.good[1], clean_audit(),
        ])
        self.assertEqual(result, (TRANSCRIPT, FORMATTED, diary_to_markdown(FORMATTED)))
        calls = self.client.models.generate_content.call_args_list
        self.assertEqual(len(calls), 4)
        repair = json.loads(calls[2].kwargs["contents"])
        self.assertEqual(repair["transcript"], TRANSCRIPT)
        self.assertEqual(repair["formatted"], single_line)
        self.assertTrue(repair["format_error"])
        self.assertEqual(calls[2].kwargs["config"].response_schema, DiaryDraft)
        audit = json.loads(calls[3].kwargs["contents"])
        self.assertEqual(audit["transcript"], TRANSCRIPT)
        self.assertEqual(audit["formatted"], FORMATTED)
        self.assertEqual(calls[3].kwargs["config"].response_schema, DiaryAudit)

    def test_failed_format_repair_retains_transcript_and_stops_before_audit(self):
        single_line = FORMATTED.replace("\n", " ")
        failures = [
            response(parsed=DiaryDraft(formatted=single_line)),
            response(parsed=None),
            response(parsed=DiaryDraft(formatted=FORMATTED), reason="MAX_TOKENS"),
            RuntimeError("secret-provider-detail"),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                self.client.models.generate_content.reset_mock()
                with self.assertRaises(DiaryProcessingError) as caught:
                    self.run_pipeline([
                        self.good[0], response(parsed=DiaryDraft(formatted=single_line)),
                        failure,
                    ])
                self.assertEqual(caught.exception.transcript, TRANSCRIPT)
                self.assertNotIn("secret-provider-detail", str(caught.exception))
                self.assertEqual(self.client.models.generate_content.call_count, 3)

    def test_format_repair_still_allows_one_content_repair_and_reaudit(self):
        issues = {"missing_contents": ["Der grüne Schal fehlt"],
                  "distorted_contents": [], "unsupported_contents": []}
        single_line = SHORT_DRAFT.replace("\n", " ")
        result = self.run_pipeline([
            self.good[0], response(parsed=DiaryDraft(formatted=single_line)),
            response(parsed=DiaryDraft(formatted=SHORT_DRAFT)),
            response(parsed=DiaryAudit(**issues)), self.good[1], clean_audit(),
        ])
        self.assertEqual(result, (TRANSCRIPT, FORMATTED, diary_to_markdown(FORMATTED)))
        calls = self.client.models.generate_content.call_args_list
        self.assertEqual(len(calls), 6)
        self.assertEqual(json.loads(calls[3].kwargs["contents"])["formatted"], SHORT_DRAFT)
        repair = json.loads(calls[4].kwargs["contents"])
        self.assertEqual(repair["transcript"], TRANSCRIPT)
        self.assertEqual(repair["formatted"], SHORT_DRAFT)
        self.assertEqual(repair["issues"], issues)
        final_audit = json.loads(calls[5].kwargs["contents"])
        self.assertEqual(final_audit["transcript"], TRANSCRIPT)
        self.assertEqual(final_audit["formatted"], FORMATTED)
        self.assertEqual(calls[5].kwargs["config"].response_schema, DiaryAudit)

    def test_still_incomplete_after_one_repair_fails_with_reference_transcript(self):
        bad = response(parsed=DiaryAudit(
            missing_contents=["Der grüne Schal fehlt"], distorted_contents=[], unsupported_contents=[]))
        with self.assertRaises(DiaryProcessingError) as caught:
            self.run_pipeline([self.good[0], self.good[1], bad, self.good[1], bad])
        self.assertEqual(caught.exception.transcript, TRANSCRIPT)
        self.assertIn("weiterhin", str(caught.exception))
        self.assertEqual(self.client.models.generate_content.call_count, 5)

    def test_every_stage_rejects_token_limit_safety_and_missing_candidates(self):
        bad_audit = response(parsed=DiaryAudit(
            missing_contents=["Detail fehlt"], distorted_contents=[], unsupported_contents=[]))
        complete_path = self.good[:2] + [bad_audit, self.good[1], clean_audit()]
        for stage in range(5):
            for reason, candidates in (("MAX_TOKENS", True), ("SAFETY", True), ("STOP", False)):
                with self.subTest(stage=stage, reason=reason, candidates=candidates):
                    self.client.models.generate_content.reset_mock()
                    with self.assertRaises(DiaryProcessingError) as caught:
                        # Even parsed, syntactically valid JSON is unsafe after MAX_TOKENS.
                        self.run_pipeline(complete_path[:stage] + [response(
                            text=TRANSCRIPT, parsed=complete_path[stage].parsed,
                            reason=reason, candidates=candidates)])
                    self.assertEqual(self.client.models.generate_content.call_count, stage + 1)
                    self.assertEqual(caught.exception.transcript, None if stage == 0 else TRANSCRIPT)

    def test_api_exceptions_in_each_stage_do_not_leak_details_or_return_a_draft(self):
        bad_audit = response(parsed=DiaryAudit(
            missing_contents=["Detail fehlt"], distorted_contents=[], unsupported_contents=[]))
        complete_path = self.good[:2] + [bad_audit, self.good[1], clean_audit()]
        for stage in range(5):
            with self.subTest(stage=stage):
                with self.assertRaises(DiaryProcessingError) as caught:
                    self.run_pipeline(complete_path[:stage] + [RuntimeError("secret-provider-detail")])
                self.assertNotIn("secret-provider-detail", str(caught.exception))
                self.assertEqual(caught.exception.transcript, None if stage == 0 else TRANSCRIPT)

    def test_empty_transcription_or_invalid_structured_output_fails(self):
        for responses in ([response(text="  ")], [self.good[0], response(parsed=None)],
                          [self.good[0], self.good[1], response(parsed={})],
                          [self.good[0], response(parsed={"formatted": ""})]):
            with self.subTest(responses=responses):
                with self.assertRaises(DiaryProcessingError):
                    self.run_pipeline(responses)

    def test_markdown_preserves_long_body_with_quotes_dates_numbers_and_paragraphs(self):
        body = "\n\n".join(f'Szene {i}: Kathrin sagte „Das bleibt!“, am Rhein um 18:30 Uhr.'
                             for i in range(300))
        formatted = f"9. Oktober 2026 – Viele Erinnerungen (Kim)\n\nWas war los?\n{body}"
        markdown = diary_to_markdown(formatted)
        self.assertEqual(markdown.removeprefix("## ").replace("\n### ", "\n"), formatted)
        self.assertTrue(markdown.endswith('Szene 299: Kathrin sagte „Das bleibt!“, am Rhein um 18:30 Uhr.'))

    def test_empty_missing_or_duplicate_sections_fail(self):
        for text in ("", "Nur ein Titel", "Titel\n\nEin Text ohne Abschnitt",
                     "Titel\n\nWas war los?", "Titel\n\nWas war los?\n\nWie war es?\nGefühl",
                     "Titel\n\nWas war los?\nText\n\nWas war los?\nMehr Text"):
            with self.subTest(text=text):
                with self.assertRaises(DiaryProcessingError):
                    diary_to_markdown(text)


if __name__ == "__main__":
    unittest.main()
