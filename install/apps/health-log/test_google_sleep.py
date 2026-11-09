"""公式レスポンス形の合成データだけで睡眠同期を検証する。実APIには接続しない。"""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from google_sleep import GoogleSleep, SleepError, ENDPOINT, request_sleep_json, save_snapshot
from google_steps import GoogleSteps, civil, save_snapshot as save_steps
from server import Store, validate

NOW = datetime(2026, 11, 9, 0, tzinfo=timezone.utc)


def point(name="night", start="2026-11-08T22:00:00+09:00", end="2026-11-09T06:00:00+09:00", minutes="450"):
    return {"name": "users/fixture-user/dataTypes/sleep/dataPoints/" + name,
            "sleep": {"interval": {"startTime": start, "endTime": end},
                      "summary": {} if minutes is None else {"minutesAsleep": minutes}}}


class SleepTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "ログ").mkdir()
        self.store = Store(self.root)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, points=None, pages=None, now=NOW):
        pages = list(pages) if pages is not None else [{"dataPoints": points if points is not None else [point()]}]
        def api(method, url, body, token):
            self.calls.append(url)
            if url.endswith("identity"):
                return {"healthUserId": "fixture-user"}
            return pages.pop(0)
        return GoogleSleep("fixture-access", "fixture-user", transport=api, now=lambda: now).fetch_day("2026-11-09", "Asia/Tokyo")

    def test_wake_day_and_actual_sleep_not_bed_duration(self):
        result = self.snapshot()
        self.assertEqual(result.minutes, 450)
        self.assertEqual(result.date, "2026-11-09")
        query = parse_qs(urlsplit(self.calls[-1]).query)
        self.assertNotIn("dataSourceFamily", query)
        self.assertIn('sleep.interval.end_time', query["filter"][0])
        self.assertIn('2026-11-08T15:00:00+00:00', query["filter"][0])

    def test_pagination_deduplicates_and_adds_nap(self):
        nap = point("nap", "2026-11-09T13:00:00+09:00", "2026-11-09T13:30:00+09:00", "25")
        result = self.snapshot(pages=[{"dataPoints": [point()], "nextPageToken": "p2"}, {"dataPoints": [point(), nap]}])
        self.assertEqual(result.minutes, 475)
        self.assertEqual(len(result.sessions), 2)

    def test_absent_summary_and_overlap_are_not_zero(self):
        cases = [([], "no_sessions"), ([point(minutes=None)], "summary_missing"),
                 ([point(), point("overlap")], "overlapping_sessions")]
        for points, state in cases:
            with self.subTest(state=state):
                result = self.snapshot(points)
                self.assertIsNone(result.minutes)
                self.assertEqual(result.missing_state, state)
        self.assertEqual(self.snapshot([point(minutes="0")]).minutes, 0)

    def test_rejects_wrong_day_bad_values_and_conflicting_ids(self):
        for points in ([point(end="2026-11-10T06:00:00+09:00")], [point(minutes=True)],
                       [point(minutes="9999")], [point(), point(minutes="400")]):
            with self.subTest(points=points), self.assertRaises(SleepError):
                self.snapshot(points)

    def test_repeated_page_and_bad_identity_fail_closed(self):
        with self.assertRaises(SleepError):
            self.snapshot(pages=[{"nextPageToken": "same"}, {"nextPageToken": "same"}])
        with self.assertRaises(SleepError):
            GoogleSleep("fixture-access", "fixture-user", transport=lambda *args: {"healthUserId": "other"}).fetch_day("2026-11-09", "UTC")

    def test_transport_rejects_other_hosts_methods_and_filters_before_network(self):
        with patch("google_sleep.build_opener") as opener:
            for method, url in [("POST", ENDPOINT), ("GET", "https://example.invalid/data"),
                                ("GET", ENDPOINT + "?dataSourceFamily=anything"), ("GET", ENDPOINT + "#bad")]:
                with self.assertRaises(SleepError): request_sleep_json(method, url, None, "fixture-access")
            opener.assert_not_called()

    def test_save_is_idempotent_and_does_not_store_token(self):
        result = self.snapshot()
        first = save_snapshot(self.store, result)
        second = save_snapshot(self.store, self.snapshot(now=NOW.replace(hour=1)))
        self.assertEqual(first["path"], second["path"])
        self.assertTrue(second["unchanged"])
        body = (self.root / first["path"]).read_text(encoding="utf-8")
        self.assertIn("kind: sleep", body)
        self.assertNotIn("fixture-access", body)
        self.assertNotIn("fixture-user", body.split("account_hash:", 1)[1].splitlines()[0])

    def test_mcp_returns_sleep_observation_in_minutes(self):
        save_snapshot(self.store, self.snapshot())
        module_path = Path(__file__).parent.parent / "obsidian-mcp/health.py"
        spec = importlib.util.spec_from_file_location("sleep_test_health", module_path)
        health = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(health)
        vault = SimpleNamespace(root=self.root, read=lambda relative: (self.root / relative).read_text(encoding="utf-8"))
        result = health.day(vault, "2026-11-09")
        self.assertEqual(result["skipped_invalid"], 0)
        self.assertEqual(result["latest_observations"]["sleep"][0]["value"], 450)
        self.assertEqual(result["latest_observations"]["sleep"][0]["unit"], "minutes")

    def test_steps_and_sleep_dedup_remain_independent(self):
        def api(method, url, payload, token):
            if method == "GET": return {"healthUserId": "fixture-user"}
            return {"rollupDataPoints": [{"civilStartTime": payload["range"]["start"], "civilEndTime": payload["range"]["end"], "steps": {"countSum": "450"}}]}
        client = GoogleSteps("fixture-access", "fixture-user", transport=api, now=lambda: NOW)
        step = client.fetch_day("2026-11-09")
        save_steps(self.store, step)
        save_snapshot(self.store, self.snapshot(now=NOW.replace(hour=1)))
        result = save_steps(self.store, client.fetch_day("2026-11-09"))
        self.assertTrue(result["unchanged"])
        self.assertEqual(len(self.store.record_paths("*.md")), 2)


if __name__ == "__main__":
    unittest.main()
