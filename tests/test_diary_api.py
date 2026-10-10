"""HTTP boundary tests; every model and export operation is mocked."""
import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend import main
from backend.diary import DiaryProcessingError


class DiaryApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.model = Mock()
        self.process = self.patch("process_diary", return_value=("Gesprochen", "Eintrag", "## Eintrag"))
        self.patch("gemini_client", new=self.model)
        self.patch("APP_SECRET", new="")
        self.docs = self.patch("write_to_google_doc", return_value=True)
        self.queue = self.patch("append_to_obsidian_queue", return_value=True)

    def patch(self, name, **kwargs):
        patcher = patch.object(main, name, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def upload(self, template="tagebuch", speaker="Kathrin", content_type="audio/webm;codecs=opus", headers=None):
        return self.client.post(
            "/upload",
            files={"audio": ("recording.webm", b"audio fixture", content_type)},
            data={"template": template, "speaker": speaker,
                  "destination_url": "https://docs.google.com/document/d/doc-target/edit",
                  "obsidian_queue_url": "https://docs.google.com/document/d/queue-target/edit"},
            headers=headers or {},
        )

    def assert_no_export(self, response):
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["error"])
        self.assertIsNone(body["formatted"])
        self.assertIsNone(body["markdown"])
        self.assertFalse(body["doc_written"])
        self.assertFalse(body["queued_for_obsidian"])
        self.docs.assert_not_called()
        self.queue.assert_not_called()
        return body

    def test_success_exports_only_completed_pipeline_result(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["transcript"], body["formatted"], body["markdown"]),
                         ("Gesprochen", "Eintrag", "## Eintrag"))
        self.assertTrue(body["doc_written"])
        self.assertTrue(body["queued_for_obsidian"])
        self.docs.assert_called_once_with("doc-target", "tagebuch", "Eintrag")
        self.queue.assert_called_once_with("queue-target", "tagebuch", "Kathrin", "## Eintrag")
        self.model.models.generate_content.assert_not_called()
        args = self.process.call_args.args
        self.assertIs(args[0], self.model)
        self.assertEqual(args[2].inline_data.mime_type, "audio/webm")
        self.assertEqual(args[2].inline_data.data, b"audio fixture")
        self.assertIn("Kathrin", args[3])

    def test_processing_runs_without_event_loop_in_worker_thread(self):
        threads = []

        def processing(*args, **kwargs):
            threads.append(threading.current_thread().name)
            with self.assertRaises(RuntimeError):
                asyncio.get_running_loop()
            return "Gesprochen", "Eintrag", "## Eintrag"

        self.process.side_effect = processing
        self.assertEqual(self.upload().status_code, 200)
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], threading.current_thread().name)

    def test_expected_failures_never_export_and_preserve_available_transcript(self):
        for transcript in (None, "Vollständiges Transkript"):
            with self.subTest(transcript=transcript):
                self.process.side_effect = DiaryProcessingError("Ausgabegrenze erreicht", transcript=transcript)
                body = self.assert_no_export(self.upload())
                self.assertEqual(body["error"], "Ausgabegrenze erreicht")
                self.assertEqual(body["transcript"], transcript or "")

    def test_unexpected_failure_is_safe_and_never_exports(self):
        self.process.side_effect = RuntimeError("secret-provider-detail")
        body = self.assert_no_export(self.upload())
        self.assertNotIn("secret-provider-detail", str(body))

    def test_missing_api_key_never_calls_pipeline_or_exports(self):
        with patch.object(main, "gemini_client", None):
            self.assert_no_export(self.upload())
        self.process.assert_not_called()

    def test_password_is_checked_before_any_processing(self):
        with patch.object(main, "APP_SECRET", "correct"):
            for headers in ({}, {"X-App-Secret": "wrong"}):
                with self.subTest(headers=headers):
                    self.assertEqual(self.upload(headers=headers).status_code, 401)
            self.assertEqual(self.upload(headers={"X-App-Secret": "correct"}).status_code, 200)
        self.process.assert_called_once()
        self.model.models.generate_content.assert_not_called()

    def test_non_audio_rejected_before_processing(self):
        self.assertEqual(self.upload(content_type="text/plain").status_code, 400)
        self.process.assert_not_called()
        self.docs.assert_not_called()
        self.queue.assert_not_called()

    def test_speaker_is_trimmed_or_defaults_to_unknown(self):
        for provided, expected in (("  Kathrin  ", "Kathrin"), ("   ", "unbekannt")):
            with self.subTest(provided=provided):
                self.assertEqual(self.upload(speaker=provided).status_code, 200)
                self.assertEqual(self.queue.call_args.args[2], expected)
                self.assertIn(expected, self.process.call_args.args[3])

    def test_other_templates_keep_single_combined_call(self):
        self.model.models.generate_content.return_value = SimpleNamespace(
            parsed=main.VoiceResult(transcript=" Raw ", formatted=" Finished ", markdown=" Markdown "))
        for template in ("quick_note", "restaurant_review"):
            with self.subTest(template=template):
                self.model.models.generate_content.reset_mock()
                response = self.upload(template=template)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual((body["transcript"], body["formatted"], body["markdown"]),
                                 ("Raw", "Finished", "Markdown"))
                self.model.models.generate_content.assert_called_once()
                config = self.model.models.generate_content.call_args.kwargs["config"]
                self.assertEqual(config.response_mime_type, "application/json")
                self.assertIs(config.response_schema, main.VoiceResult)
                self.docs.assert_called_with("doc-target", template, "Finished")
                self.queue.assert_called_with("queue-target", template, "Kathrin", "Markdown")
        self.process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
