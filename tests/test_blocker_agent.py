import json
import tempfile
import unittest
from pathlib import Path

from content_pipeline.bots.blocker_agent import (
    absorb_blocker_solution,
    blocker_status,
    blocker_status_html,
    load_blocker_journal,
    record_blocker,
    resolve_blocker,
    suggest_blocker_fixes,
)


class BlockerAgentTest(unittest.TestCase):
    def test_record_and_resolve_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            path = record_blocker(
                output,
                command="gemini-image-plan",
                issue="Gemini budget exhausted",
                solution="Rotate to mock fallback until UTC reset.",
                component="image",
                tags=["quota", "fallback"],
            )

            journal = load_blocker_journal(output)
            blocker_id = journal["entries"][0]["id"]
            self.assertTrue(path.exists())
            self.assertEqual(journal["entries"][0]["status"], "resolved")
            self.assertEqual(journal["entries"][0]["solution"], "Rotate to mock fallback until UTC reset.")

            resolve_blocker(output, blocker_id, "Use Imagen fallback and keep a daily budget.")
            updated = load_blocker_journal(output)

            self.assertEqual(updated["entries"][0]["status"], "resolved")
            self.assertEqual(updated["entries"][0]["solution"], "Use Imagen fallback and keep a daily budget.")

    def test_status_and_html_render_open_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            record_blocker(
                output,
                command="run",
                issue="Unexpected quota block",
                component="pipeline",
                severity="high",
            )

            status = blocker_status(output)
            html = blocker_status_html(output)

            self.assertEqual(status["open_count"], 1)
            self.assertEqual(status["resolved_count"], 0)
            self.assertIn("Unexpected quota block", json.dumps(status))
            self.assertIn("Blocker learning agent", html)
            self.assertIn("Unexpected quota block", html)

    def test_learned_solution_keeps_source_metadata_and_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "output"
            absorb_blocker_solution(
                output,
                issue="429 Too Many Requests on Gemini image calls",
                solution="Add per-key cooldown and fallback to the next Gemini key.",
                command="gemini-image-plan",
                component="image",
                source_title="Google rate-limit guidance",
                source_url="https://example.com/rate-limits",
                notes="Use the same strategy when burst traffic spikes.",
                tags=["quota", "fallback"],
            )

            suggestions = suggest_blocker_fixes(output)
            status = blocker_status(output)
            journal = load_blocker_journal(output)

            self.assertEqual(journal["entries"][0]["source_title"], "Google rate-limit guidance")
            self.assertEqual(journal["entries"][0]["source_url"], "https://example.com/rate-limits")
            self.assertEqual(status["resolved_count"], 1)
            self.assertGreaterEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0]["source_title"], "Google rate-limit guidance")
            self.assertIn("fallback", suggestions[0]["solution"])


if __name__ == "__main__":
    unittest.main()
