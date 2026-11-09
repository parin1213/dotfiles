"""公開モード別の資格情報期限を架空のトークンだけで検証する。"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import unittest

from google_steps import SCOPE
from sync_credentials import Bundle, CredentialError, from_grant, refreshed, rotated


NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


class ProductionCredentialTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"scope": SCOPE, "token_type": "Bearer", "refresh_token": "fixture-refresh"}
        self.bundle = Bundle("123-fixture.apps.googleusercontent.com", "fixture-secret", "fixture-refresh",
                             "fixture-user", NOW.isoformat(), (NOW + timedelta(days=7)).isoformat(),
                             "test@example.invalid", "test-health-project")

    def grant(self, **kwargs):
        return from_grant(self.bundle.client_id, self.bundle.client_secret, self.payload, self.bundle.health_user_id,
                          authorized_at=NOW, account=self.bundle.account, project_id=self.bundle.project_id, **kwargs)

    def test_missing_mode_keeps_seven_day_limit(self):
        data = json.loads(self.bundle.serialized())
        data.pop("authorization_mode")
        loaded = Bundle(**data).validate()
        self.assertEqual(loaded.authorization_mode, "testing")
        self.assertEqual(loaded.expires_at, self.bundle.expires_at)
        with self.assertRaises(CredentialError):
            loaded.live(NOW + timedelta(days=7))
        self.assertEqual(self.grant().expires_at, self.bundle.expires_at)

    def test_no_expiration_requires_explicit_production_mode(self):
        with self.assertRaises(CredentialError):
            replace(self.bundle, expires_at=None).validate()
        for mode in ("", None, False, "published", []):
            with self.subTest(mode=mode), self.assertRaises(CredentialError):
                self.grant(authorization_mode=mode)
        self.payload["expires_in"] = 3600
        bundle = self.grant(authorization_mode="production")
        self.assertIsNone(bundle.expires_at)
        self.assertEqual(bundle.authorization_mode, "production")
        bundle.live(NOW + timedelta(days=180))
        self.assertIsNone(json.loads(bundle.serialized())["expires_at"])
        with self.assertRaises(CredentialError):
            bundle.live(NOW - timedelta(seconds=1))

    def test_production_accepts_server_duration_longer_than_seven_days(self):
        self.payload["refresh_token_expires_in"] = 30 * 86400
        with self.assertRaises(CredentialError):
            self.grant()
        bundle = self.grant(authorization_mode="production")
        self.assertEqual(bundle.expires_at, (NOW + timedelta(days=30)).isoformat())
        with self.assertRaises(CredentialError):
            bundle.live(NOW + timedelta(days=30))

    def test_invalid_server_duration_never_becomes_indefinite(self):
        for duration in (0, -1, True, "3600", None, 10**100):
            with self.subTest(duration=duration):
                self.payload["refresh_token_expires_in"] = duration
                with self.assertRaises(CredentialError):
                    self.grant(authorization_mode="production")

    def test_rotation_never_changes_mode_or_extends_expiration(self):
        for bundle in (self.bundle, replace(self.bundle, authorization_mode="production")):
            updated = refreshed(bundle, {"refresh_token": "fixture-new-refresh",
                                         "refresh_token_expires_in": 30 * 86400}, NOW)
            self.assertEqual(updated.expires_at, bundle.expires_at)
            self.assertEqual(updated.authorization_mode, bundle.authorization_mode)
            self.assertEqual(updated.authorized_at, bundle.authorized_at)
            self.assertEqual(rotated(bundle, "fixture-new-refresh").expires_at, bundle.expires_at)

    def test_server_shorter_expiration_is_retained(self):
        for bundle in (self.bundle, replace(self.bundle, authorization_mode="production", expires_at=None)):
            updated = refreshed(bundle, {"refresh_token_expires_in": 3600}, NOW)
            self.assertEqual(updated.expires_at, (NOW + timedelta(hours=1)).isoformat())
            self.assertEqual(refreshed(updated, {}, NOW).expires_at, updated.expires_at)
        production = replace(self.bundle, authorization_mode="production", expires_at=None)
        self.assertIsNone(refreshed(production, {"expires_in": 3600}, NOW).expires_at)


if __name__ == "__main__":
    unittest.main()
