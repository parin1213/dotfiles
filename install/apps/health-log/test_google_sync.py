"""継続同期は架空の更新トークンと一時Vaultだけで検証する。"""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from google_once import AuthError
from google_steps import SCOPE, StepsError, civil, save_snapshot
from google_sync import SyncFailure, run_sync, target_days, write_status
from health_scopes import SLEEP_SCOPE, requested_scope
from sync_credentials import Bundle, CredentialError, encrypt_bundle, from_grant, load_runtime
from server import Store


NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        (self.root / "ログ").mkdir()
        (self.root / ".git").mkdir()
        self.store = Store(self.root)
        self.bundle = Bundle("123-fixture.apps.googleusercontent.com", "fixture-secret", "fixture-refresh", "fixture-user",
                             NOW.isoformat(), (NOW + timedelta(days=7)).isoformat(), "test@example.invalid", "test-health-project")
        self.calls = []
        def grant(url, fields):
            self.calls.append("grant")
            return {"access_token": "fixture-access", "token_type": "Bearer", "scope": SCOPE}
        def api(method, url, body, token):
            self.calls.append(method)
            if method == "GET": return {"healthUserId": "fixture-user"}
            start = body["range"]["start"]
            end = body["range"]["end"]
            return {"rollupDataPoints": [{"civilStartTime": start, "civilEndTime": end, "steps": {"countSum": "17"}}]}
        self.grant, self.api = grant, api

    def tearDown(self):
        self.temp.cleanup()

    def run_sync(self, **kwargs):
        return run_sync(self.bundle, self.store, zone_name="UTC", expected_account="test@example.invalid", expected_project="test-health-project", now=NOW, grant=self.grant, api=self.api, **kwargs)

    def test_target_days_are_local_and_limited(self):
        self.assertEqual(target_days(NOW, "UTC"), ["2026-11-05", "2026-11-06"])
        for zone, count in (("", 2), ("bad/zone", 2), ("UTC", 3), ("UTC", True)):
            with self.assertRaises(SyncFailure): target_days(NOW, zone, count)

    def test_timezone_boundary(self):
        try: ZoneInfo("Asia/Tokyo")
        except ZoneInfoNotFoundError: self.skipTest("この実行環境にはIANAタイムゾーンデータがありません")
        late = NOW.replace(hour=23)
        self.assertEqual(target_days(late, "Asia/Tokyo"), ["2026-11-06", "2026-11-07"])

    def test_two_days_saved_without_duplicate_or_secret(self):
        result = self.run_sync()
        self.assertEqual(result["completed_day_count"], 2)
        self.assertEqual(result["status"], "success")
        self.run_sync()
        notes = list((self.root / "Attachments/health/records").iterdir())
        self.assertEqual(len(notes), 2)
        for note in notes:
            text = note.read_text(encoding="utf-8")
            for secret in ("fixture-secret", "fixture-refresh", "fixture-access", "fixture-user"):
                self.assertNotIn(secret, text)

    def test_steps_only_grant_never_initializes_sleep(self):
        with patch("google_sync.GoogleSleep") as sleep:
            result = self.run_sync()
        sleep.assert_not_called()
        self.assertEqual(result["sleep_status"], "not_authorized")
        self.assertEqual(result["steps_status"], "success")
        self.assertEqual(result["sleep_completed_day_count"], 0)

    def enable_sleep(self):
        self.bundle = replace(self.bundle, scope=requested_scope(True))
        self.grant = lambda *_: {"access_token": "fixture-access", "token_type": "Bearer", "scope": self.bundle.scope}

    def test_sleep_uses_persisted_scope_and_own_transport(self):
        self.enable_sleep()
        with patch("google_sync.GoogleSleep") as sleep, patch("google_sync.save_sleep_snapshot") as save:
            sleep.return_value.fetch_day.side_effect = ["fixture-yesterday", "fixture-today"]
            result = self.run_sync()
        self.assertNotIn("transport", sleep.call_args.kwargs)
        self.assertEqual(sleep.call_args.args, ("fixture-access", "fixture-user"))
        self.assertEqual(sleep.return_value.fetch_day.call_args_list[0].args, ("2026-11-05", "UTC"))
        self.assertEqual(sleep.return_value.fetch_day.call_args_list[1].args, ("2026-11-06", "UTC"))
        self.assertEqual(save.call_count, 2)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sleep_status"], "success")
        self.assertEqual(result["sleep_completed_day_count"], 2)

    def test_injected_sleep_transport_does_not_replace_steps_transport(self):
        self.enable_sleep()
        fake_sleep_api = lambda *_: None
        with patch("google_sync.GoogleSleep") as sleep, patch("google_sync.save_sleep_snapshot"):
            self.run_sync(sleep_api=fake_sleep_api)
        self.assertIs(sleep.call_args.kwargs["transport"], fake_sleep_api)
        self.assertEqual(self.calls.count("POST"), 2)

    def test_sleep_client_saves_real_snapshots_with_fake_api(self):
        try: ZoneInfo("UTC")
        except ZoneInfoNotFoundError: self.skipTest("この実行環境にはIANAタイムゾーンデータがありません")
        self.enable_sleep()
        sleep_calls = []
        def sleep_api(method, url, body, token):
            sleep_calls.append(url)
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "fixture-access")
            if url.endswith("/identity"):
                return {"healthUserId": "fixture-user"}
            query = parse_qs(urlsplit(url).query)
            day = query["filter"][0].split('"')[1][:10]
            return {"dataPoints": [{"name": f"users/fixture-user/dataTypes/sleep/dataPoints/fixture-{day}",
                "sleep": {"interval": {"startTime": day + "T00:00:00+00:00", "endTime": day + "T07:00:00+00:00"},
                          "summary": {"minutesAsleep": "420"}}}]}
        result = self.run_sync(sleep_api=sleep_api)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sleep_completed_day_count"], 2)
        self.assertEqual(len(sleep_calls), 4)
        notes = list((self.root / "Attachments/health/records").iterdir())
        self.assertEqual(len(notes), 4)
        self.assertEqual(sum("kind: sleep" in note.read_text(encoding="utf-8") for note in notes), 2)

    def test_sleep_fetch_failure_keeps_successful_steps(self):
        self.enable_sleep()
        with patch("google_sync.GoogleSleep") as sleep, patch("google_sync.save_sleep_snapshot") as save:
            sleep.return_value.fetch_day.side_effect = ["fixture-day", RuntimeError("fixture-private-error")]
            result = self.run_sync()
        save.assert_not_called()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "sleep_data_request_failed")
        self.assertEqual(result["steps_status"], "success")
        self.assertEqual(result["completed_day_count"], 2)
        self.assertEqual(result["sleep_status"], "error")
        self.assertEqual(result["sleep_completed_day_count"], 0)
        self.assertEqual(len(list((self.root / "Attachments/health/records").iterdir())), 2)
        self.assertNotIn("fixture-private-error", json.dumps(result))

    def test_sleep_partial_save_reports_error_and_counts(self):
        self.enable_sleep()
        with patch("google_sync.GoogleSleep"), \
             patch("google_sync.save_sleep_snapshot", side_effect=[None, OSError("fixture-private-error")]):
            result = self.run_sync()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["sleep_error_code"], "sleep_vault_save_failed")
        self.assertEqual(result["completed_day_count"], 2)
        self.assertEqual(result["sleep_completed_day_count"], 1)

    def test_refresh_scope_must_match_stored_bundle(self):
        for bundle_scope, granted in ((SCOPE, requested_scope(True)), (requested_scope(True), SCOPE),
                                      (requested_scope(True), SLEEP_SCOPE), (SCOPE, SCOPE + " unexpected"),
                                      (SCOPE, [SCOPE]), (SCOPE, SCOPE + " " + SCOPE)):
            with self.subTest(bundle_scope=bundle_scope, granted=granted):
                self.bundle = replace(self.bundle, scope=bundle_scope)
                self.grant = lambda *_: {"access_token": "fixture-access", "token_type": "Bearer", "scope": granted}
                with self.assertRaises(SyncFailure) as failure:
                    self.run_sync()
                self.assertEqual(failure.exception.reason, "invalid_grant_response")
                self.assertEqual(self.calls, [])

    def test_omitted_refresh_scope_keeps_saved_sleep_permission(self):
        self.enable_sleep()
        self.grant = lambda *_: {"access_token": "fixture-access", "token_type": "Bearer"}
        with patch("google_sync.GoogleSleep") as sleep, patch("google_sync.save_sleep_snapshot"):
            self.assertEqual(self.run_sync()["sleep_status"], "success")
        sleep.assert_called_once()

    def test_expired_credentials_never_call_google(self):
        self.bundle = replace(self.bundle, authorized_at=(NOW-timedelta(days=8)).isoformat(), expires_at=(NOW-timedelta(days=1)).isoformat())
        with self.assertRaises(SyncFailure) as failure: self.run_sync()
        self.assertEqual(failure.exception.reason, "credential_expired_or_invalid")
        self.assertEqual(self.calls, [])

    def test_wrong_identity_writes_nothing(self):
        self.api = lambda *_: {"healthUserId":"other-user"}
        with self.assertRaises(SyncFailure): self.run_sync()
        self.assertEqual(list((self.root / "Attachments/health/records").iterdir()), [])

    def test_wrong_configured_account_never_calls_google(self):
        self.bundle = replace(self.bundle, account="other@example.invalid")
        with self.assertRaises(SyncFailure) as failure: self.run_sync()
        self.assertEqual(failure.exception.reason,"credential_account_mismatch")
        self.assertEqual(self.calls,[])

    def test_second_fetch_failure_writes_nothing(self):
        original = self.api
        def failing(method, url, body, token):
            if method == "POST" and body["range"]["start"]["date"]["day"] == 6: raise StepsError("fixture-error")
            return original(method, url, body, token)
        self.api = failing
        with self.assertRaises(SyncFailure): self.run_sync()
        self.assertEqual(list((self.root / "Attachments/health/records").iterdir()), [])

    def test_authentication_failure_does_not_retry(self):
        def denied(*_):
            self.calls.append("denied")
            raise AuthError("fixture-invalid-grant")
        self.grant = denied
        with self.assertRaises(SyncFailure) as failure: self.run_sync()
        self.assertEqual(failure.exception.reason, "authentication_failed")
        self.assertEqual(self.calls, ["denied"])

    def test_rotation_must_be_saved_before_data_read(self):
        self.grant = lambda *_: {"access_token":"fixture-access", "token_type":"Bearer", "refresh_token":"new-fixture-refresh"}
        with self.assertRaises(SyncFailure) as failure: self.run_sync()
        self.assertEqual(failure.exception.reason, "credential_rotation_not_saved")
        self.assertEqual(self.calls, [])
        stored = []
        def persist(bundle):
            self.assertEqual(self.calls, [])
            stored.append(bundle)
        self.run_sync(credential_writer=persist)
        self.assertEqual(stored[0].refresh_token, "new-fixture-refresh")
        self.assertEqual(stored[0].expires_at, self.bundle.expires_at)

    def test_refresh_expiration_saved_before_data_read(self):
        self.bundle = replace(self.bundle, authorization_mode="production", expires_at=None)
        self.grant = lambda *_: {"access_token": "fixture-access", "token_type": "Bearer",
                                 "refresh_token_expires_in": 3600}
        with self.assertRaises(SyncFailure) as failure:
            self.run_sync()
        self.assertEqual(failure.exception.reason, "credential_rotation_not_saved")
        self.assertEqual(self.calls, [])
        saved = []
        def persist(bundle):
            self.assertEqual(self.calls, [])
            saved.append(bundle)
        self.assertEqual(self.run_sync(credential_writer=persist)["status"], "success")
        self.assertEqual(saved[0].authorization_mode, "production")
        self.assertEqual(saved[0].expires_at, (NOW + timedelta(hours=1)).isoformat())

    def test_invalid_refresh_expiration_stops_before_data_read(self):
        for duration in (0, -1, None, True, "3600", 10**100):
            with self.subTest(duration=duration):
                self.grant = lambda *_: {"access_token": "fixture-access", "token_type": "Bearer",
                                         "refresh_token_expires_in": duration}
                with self.assertRaises(SyncFailure) as failure:
                    self.run_sync()
                self.assertEqual(failure.exception.reason, "invalid_grant_response")
                self.assertEqual(self.calls, [])

    def test_partial_save_is_reported(self):
        saved = 0
        def partial(store, snapshot):
            nonlocal saved
            if saved: raise OSError("fixture-save-failure")
            saved += 1
            return save_snapshot(store, snapshot)
        with patch("google_sync.save_snapshot", side_effect=partial):
            with self.assertRaises(SyncFailure) as failure: self.run_sync()
        self.assertEqual(failure.exception.completed, 1)
        self.assertEqual(len(list((self.root / "Attachments/health/records").iterdir())), 1)

    def test_status_contains_no_values_or_credentials(self):
        path = self.root / "state/status.json"
        write_status(path, {"status":"success", "completed_day_count":2, "steps":17, "access_token":"fixture-access"}, NOW)
        write_status(path, {"status":"error", "error_code":"authentication_failed"}, NOW + timedelta(hours=1))
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(state["last_success_at"], NOW.isoformat())
        self.assertNotIn("steps", state)
        self.assertNotIn("fixture-access", path.read_text(encoding="utf-8"))

    def test_bundle_runtime_and_representation(self):
        self.assertNotIn("fixture-secret", repr(self.bundle))
        runtime = self.root / "runtime"
        runtime.mkdir()
        target = runtime / "google-health.json"
        target.write_bytes(self.bundle.serialized())
        target.chmod(0o600)
        loaded = load_runtime(runtime)
        self.assertEqual(loaded.health_user_id, "fixture-user")
        with self.assertRaises(CredentialError): replace(self.bundle, scope="unexpected").validate()
        with self.assertRaises(CredentialError): replace(self.bundle, expires_at=(NOW+timedelta(days=8)).isoformat()).validate()

    def test_from_grant_caps_testing_duration(self):
        payload = {"scope":SCOPE, "token_type":"Bearer", "refresh_token":"fixture-refresh"}
        bundle = from_grant(self.bundle.client_id, self.bundle.client_secret, payload, "fixture-user", authorized_at=NOW, account=self.bundle.account, project_id=self.bundle.project_id)
        self.assertEqual(bundle.expires_at, self.bundle.expires_at)
        with self.assertRaises(CredentialError): from_grant(self.bundle.client_id, self.bundle.client_secret, payload | {"refresh_token_expires_in": 9999999}, "fixture-user", authorized_at=NOW, account=self.bundle.account, project_id=self.bundle.project_id)

    def test_bundle_accepts_only_supported_scope_combinations(self):
        for scope in (SCOPE, requested_scope(True), SLEEP_SCOPE + " " + SCOPE):
            with self.subTest(scope=scope):
                self.assertEqual(replace(self.bundle, scope=scope).validate().scope, scope)
        for scope in (SLEEP_SCOPE, "", None, [], "unexpected", SCOPE + " unexpected", SCOPE + " " + SCOPE):
            with self.subTest(scope=scope):
                with self.assertRaises(CredentialError):
                    replace(self.bundle, scope=scope).validate()

    def test_sleep_grant_requires_explicit_expected_scope(self):
        payload = {"scope": requested_scope(True), "token_type": "Bearer", "refresh_token": "fixture-refresh"}
        args = (self.bundle.client_id, self.bundle.client_secret, payload, "fixture-user")
        kwargs = {"authorized_at": NOW, "account": self.bundle.account, "project_id": self.bundle.project_id}
        with self.assertRaises(CredentialError):
            from_grant(*args, **kwargs)
        authorized = from_grant(*args, expected_scope=requested_scope(True), **kwargs)
        self.assertEqual(authorized.scope, requested_scope(True))
        with self.assertRaises(CredentialError):
            from_grant(*args, expected_scope=SLEEP_SCOPE, **kwargs)

    def test_encryption_uses_stdin_and_atomic_ciphertext(self):
        target = self.root / "private/google-health.cred"
        def encrypt(args, **kwargs):
            self.assertNotIn("fixture-refresh", str(args))
            self.assertEqual(kwargs["input"], self.bundle.serialized())
            Path(args[-1]).write_bytes(b"fixture-ciphertext")
            return SimpleNamespace(returncode=0)
        with patch("sync_credentials.subprocess.run", side_effect=encrypt): encrypt_bundle(self.bundle, target)
        self.assertEqual(target.read_bytes(), b"fixture-ciphertext")
        with patch("sync_credentials.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(CredentialError): encrypt_bundle(self.bundle, target)
        self.assertEqual(target.read_bytes(), b"fixture-ciphertext")


if __name__ == "__main__":
    unittest.main(verbosity=2)
