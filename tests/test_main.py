"""Tests for main.py. Run with: python3 -m unittest discover -s tests -v"""

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


class FakeDiscord(BaseHTTPRequestHandler):
    """Minimal stand-in for a Discord webhook endpoint."""

    received = []
    fail_times = 0
    status = 200

    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).received.append({"url": self.path, "body": body})

        if type(self).fail_times > 0:
            type(self).fail_times -= 1
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return

        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if type(self).status != 204:
            self.wfile.write(json.dumps({"id": "12345"}).encode())

    def log_message(self, *args):  # keep the test output clean
        pass


class ReminderTest(unittest.TestCase):
    def setUp(self):
        FakeDiscord.received = []
        FakeDiscord.fail_times = 0
        FakeDiscord.status = 200
        self.server = HTTPServer(("127.0.0.1", 0), FakeDiscord)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/webhooks/test"
        self.addCleanup(self.server.shutdown)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_file = os.path.join(self.tmp.name, "state.json")

    def test_message_format(self):
        message = main.build_message(main.DEFAULT_MESSAGE, 7)
        self.assertEqual(
            message,
            "🧦 Dag 7 van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok",
        )

    def test_day_advances_once_per_day(self):
        first = main.post_daily_reminder(self.state_file, webhook_url=self.url)
        second = main.post_daily_reminder(self.state_file, webhook_url=self.url)

        # Same day twice -> the same "Dag X" goes out, no skipped day numbers.
        self.assertEqual((first["day"], second["day"]), (1, 1))
        self.assertIn("Dag 1", FakeDiscord.received[0]["body"]["content"])
        self.assertIn("Dag 1", FakeDiscord.received[1]["body"]["content"])

        state = json.load(open(self.state_file))
        self.assertEqual((state["day"], state["last_day"]), (2, 1))
        self.assertIsNotNone(state["last_posted"])

        # A new day -> the counter goes up.
        state["last_posted"] = "2000-01-01"
        with open(self.state_file, "w") as handle:
            json.dump(state, handle)
        third = main.post_daily_reminder(self.state_file, webhook_url=self.url)
        self.assertEqual(third["day"], 2)
        self.assertEqual(json.load(open(self.state_file))["day"], 3)

    def test_dry_run_changes_nothing(self):
        result = main.post_daily_reminder(self.state_file, dry_run=True, webhook_url=self.url)
        self.assertFalse(result["posted"])
        self.assertEqual(FakeDiscord.received, [])
        self.assertFalse(os.path.exists(self.state_file))

    def test_retry_on_rate_limit(self):
        FakeDiscord.fail_times = 1
        result = main.post_daily_reminder(self.state_file, webhook_url=self.url)
        self.assertTrue(result["posted"])
        self.assertEqual(len(FakeDiscord.received), 2)

    def test_bad_webhook_is_not_retried_forever(self):
        FakeDiscord.status = 401
        with self.assertRaises(SystemExit):
            main.post_daily_reminder(self.state_file, webhook_url=self.url)
        self.assertEqual(len(FakeDiscord.received), 1)

    def test_waits_for_discord_confirmation(self):
        main.post_daily_reminder(self.state_file, webhook_url=self.url)
        self.assertIn("wait=true", FakeDiscord.received[0]["url"])

    def test_corrupt_state_file_starts_at_day_one(self):
        with open(self.state_file, "w") as handle:
            handle.write("not json at all")
        self.assertEqual(
            main.load_state(self.state_file),
            {"day": 1, "last_posted": None, "last_day": None},
        )

    def test_custom_message_and_day_override(self):
        result = main.post_daily_reminder(
            self.state_file,
            message_override="Dag {day}: sokken!",
            day_override=42,
            webhook_url=self.url,
        )
        self.assertEqual(result["message"], "Dag 42: sokken!")
        self.assertEqual(FakeDiscord.received[0]["body"]["content"], "Dag 42: sokken!")
        self.assertFalse(os.path.exists(self.state_file))  # override -> state untouched

    def test_missing_webhook_url_explains_itself(self):
        with self.assertRaises(SystemExit) as ctx:
            main.post_daily_reminder(self.state_file, webhook_url="")
        self.assertIn("DISCORD_WEBHOOK_URL", str(ctx.exception))

    def test_cli_dry_run(self):
        sys.argv = ["main.py", "--dry-run", "--state-file", self.state_file]
        self.assertEqual(main.main(["--dry-run", "--state-file", self.state_file]), 0)


if __name__ == "__main__":
    unittest.main()
