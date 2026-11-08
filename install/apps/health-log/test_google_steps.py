"""実OAuthやネットワークなしで日別API応答からMarkdownまで確認する。"""
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from google_steps import BASE, FAMILY, GoogleSteps, StepsError, StepsSnapshot, civil, request_json, save_snapshot
from server import Store


class GoogleStepsTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.response = {"rollupDataPoints": [{"civilStartTime": civil(date(2026, 11, 6)), "civilEndTime": civil(date(2026, 11, 7)), "steps": {"countSum": "1234"}}]}
        self.identity = {"healthUserId": "test-user"}
        self.clock = datetime(2026, 11, 7, 1, 0, tzinfo=timezone.utc)
        def transport(method, url, body, token):
            self.calls.append((method, url, body))
            self.assertEqual(token, "fixture-token")
            return self.identity if method == "GET" else self.response
        self.client = GoogleSteps("fixture-token", "test-user", transport=transport, now=lambda: self.clock)

    def test_request_identity_and_one_civil_day(self):
        snapshot = self.client.fetch_day("2026-11-06")
        self.assertEqual(snapshot.steps, 1234)
        self.assertEqual(self.calls[0], ("GET", BASE + "users/me/identity", None))
        request = self.calls[1][2]
        self.assertEqual(request["range"]["end"], civil(date(2026, 11, 7)))
        self.assertEqual(request["dataSourceFamily"], FAMILY)
        self.assertFalse(snapshot.fit_sync_verified)
        self.assertNotIn("test-user", str(snapshot.as_dict()))

    def test_wrong_account_stops_before_steps(self):
        self.identity = {"healthUserId": "other"}
        with self.assertRaises(StepsError): self.client.fetch_day("2026-11-06")
        self.assertEqual(len(self.calls), 1)

    def test_missing_and_explicit_zero(self):
        point = self.response["rollupDataPoints"][0]
        point["steps"] = {"countSum": "0"}
        self.assertEqual(self.client.fetch_day("2026-11-06").steps, 0)
        point.pop("steps")
        snapshot = self.client.fetch_day("2026-11-06")
        self.assertIsNone(snapshot.steps)
        self.assertEqual(snapshot.missing_state, "steps_omitted")
        self.response = {}
        self.assertEqual(self.client.fetch_day("2026-11-06").missing_state, "no_window")

    def test_wrong_window_and_partial_response_fail(self):
        self.response["nextPageToken"] = "unconsumed"
        with self.assertRaises(StepsError): self.client.fetch_day("2026-11-06")
        self.response.pop("nextPageToken")
        self.response["rollupDataPoints"][0]["civilStartTime"] = civil(date(2026, 11, 5))
        with self.assertRaises(StepsError): self.client.fetch_day("2026-11-06")

    def test_invalid_values_fail(self):
        for count in (True, 10, "-1", "2.5", "200001", "00", "NaN"):
            self.response["rollupDataPoints"][0]["steps"] = {"countSum": count}
            with self.subTest(count=count), self.assertRaises(StepsError): self.client.fetch_day("2026-11-06")

    def test_error_does_not_expose_token_or_body(self):
        for status in (302, 400, 401, 403, 429, 500):
            error = HTTPError(BASE + "users/me/identity", status, "fixture-token private-body", {}, None)
            with patch("google_steps.build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.subTest(status=status), self.assertRaises(StepsError) as caught:
                    request_json("GET", BASE + "users/me/identity", None, "fixture-token")
                self.assertNotIn("fixture-token", str(caught.exception))
                self.assertNotIn("private-body", str(caught.exception))

    def test_unapproved_host_is_not_called(self):
        with patch("google_steps.build_opener") as opener:
            with self.assertRaises(StepsError): request_json("GET", "https://example.invalid/", None, "fixture-token")
            opener.assert_not_called()

    def test_date_validation_before_api(self):
        for day in ("2026-02-30", "../2026-11-06", "20261106"):
            with self.assertRaises(StepsError): self.client.fetch_day(day)
        self.assertEqual(self.calls, [])

    def test_snapshot_save_retry_change_and_reversal(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            (root / "ログ").mkdir()
            (root / ".git").mkdir()
            store = Store(root)
            first = self.client.fetch_day("2026-11-06")
            saved = save_snapshot(store, first)
            self.assertTrue(saved["path"].startswith("Attachments/health/records/2026-11-06_"))
            content = (root / saved["path"]).read_text(encoding="utf-8")
            self.assertIn("source: google_health", content)
            self.assertIn("fit_sync_verified: false", content)
            self.assertNotIn("fixture-token", content)
            self.assertNotIn("test-user", content)
            again = replace(first, observed_at="2026-11-07T02:00:00+00:00")
            self.assertEqual(save_snapshot(store, again)["path"], saved["path"])
            self.assertEqual(len(list((root / "Attachments/health/records").iterdir())), 1)
            changed = replace(first, steps=2000, observed_at="2026-11-07T03:00:00+00:00")
            save_snapshot(store, changed)
            reversed_value = replace(first, observed_at="2026-11-07T04:00:00+00:00")
            self.assertNotEqual(save_snapshot(store, reversed_value)["path"], saved["path"])
            self.assertEqual(len(list((root / "Attachments/health/records").iterdir())), 3)

    def test_unchanged_snapshot_in_legacy_folder_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ログ").mkdir()
            store = Store(root)
            snapshot = self.client.fetch_day("2026-11-06")
            saved = save_snapshot(store, snapshot)
            old = root / saved["path"]
            legacy = root / "ログ" / old.name
            old.rename(legacy)
            result = save_snapshot(store, replace(snapshot, observed_at="2026-11-07T02:00:00+00:00"))
            self.assertTrue(result["unchanged"])
            self.assertEqual(result["path"], legacy.relative_to(root).as_posix())
            self.assertEqual(list(store.folder.iterdir()), [])

    def test_unverified_snapshot_cannot_be_saved(self):
        snapshot = self.client.fetch_day("2026-11-06")
        with self.assertRaises(StepsError): save_snapshot(None, replace(snapshot, identity_verified=False))
        with self.assertRaises(StepsError): save_snapshot(None, replace(snapshot, source="google_fit"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
