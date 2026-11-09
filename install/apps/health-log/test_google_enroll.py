"""継続同意の準備は架空の資格情報と通信だけで検証する。"""
from datetime import datetime, timezone
import json
import subprocess
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from google_enroll import OfflineEnrollment, store_on_pi
from google_enroll import main
from google_once import REVOKE_URL
from google_steps import SCOPE
from health_scopes import SLEEP_SCOPE, requested_scope
from sync_credentials import CredentialError
from test_google_once import ACCOUNT, PROJECT, CLIENT_ID, SECRET, TOKEN


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.calls, self.saved = [], []
        self.payload = {"access_token": TOKEN, "refresh_token": "fixture-refresh-token",
                        "token_type": "Bearer", "scope": SCOPE}
        def post(url, fields):
            self.calls.append(url)
            return {} if url == REVOKE_URL else dict(self.payload)
        self.flow = OfflineEnrollment(account=ACCOUNT, project_id=PROJECT, ssh_target="raspi4",
            now=lambda: datetime(2026, 11, 6, tzinfo=timezone.utc), post=post,
            api=lambda *args: {"healthUserId": "fixture-user"}, store=self.saved.append)

    def test_separate_offline_flow_and_encrypted_handoff(self):
        url = self.flow.begin(CLIENT_ID, SECRET)
        self.assertEqual(parse_qs(urlsplit(url).query)["access_type"], ["offline"])
        self.assertEqual(parse_qs(urlsplit(url).query)["scope"], [SCOPE])
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertTrue(result["success"])
        self.assertTrue(result["stored_encrypted"])
        self.assertFalse(result["scheduler_enabled"])
        self.assertFalse(result["revoked"])
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0].expires_at, "2026-11-13T00:00:00+00:00")
        for secret in (SECRET, TOKEN, "fixture-refresh-token", "fixture-user", "fixture-code"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIsNone(self.flow.client_secret)

    def test_failed_storage_revokes_and_never_reports_success(self):
        self.flow.store = lambda bundle: (_ for _ in ()).throw(RuntimeError(SECRET))
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revoked"])
        self.assertFalse(result["stored_encrypted"])
        self.assertEqual(self.calls[-1], REVOKE_URL)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_missing_refresh_or_extra_scope_revokes_before_store(self):
        self.payload.pop("refresh_token")
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revoked"])
        self.assertEqual(self.saved, [])

    def test_ssh_secret_only_stdin_and_safe_target(self):
        self.flow.begin(CLIENT_ID, SECRET)
        self.flow.complete(self.flow.state, "fixture-code")
        with patch("google_enroll.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            store_on_pi(self.saved[0], "raspi4")
            args, kwargs = run.call_args
            self.assertEqual(kwargs["input"], self.saved[0].serialized())
            self.assertNotIn(SECRET, repr(args))
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            with self.assertRaises(CredentialError): store_on_pi(self.saved[0], "-oProxyCommand=bad")
            self.assertEqual(run.call_count, 1)

    def sleep_flow(self, production=False):
        return OfflineEnrollment(account=ACCOUNT, project_id=PROJECT, ssh_target="raspi4", include_sleep=True,
            production=production, now=self.flow.now, post=self.flow.post, api=self.flow.api, store=self.saved.append)

    def test_production_requires_explicit_selection_and_new_consent(self):
        self.assertEqual(self.flow.authorization_mode, "testing")
        self.assertIn("最大7日", self.flow.page_home())
        flow = self.sleep_flow(production=True)
        self.assertIn("In Production", flow.page_home())
        self.assertNotIn("最大7日", flow.page_home())
        self.payload["scope"] = requested_scope(True)
        self.payload["expires_in"] = 3600
        flow.begin(CLIENT_ID, SECRET)
        result = flow.complete(flow.state, "fixture-code")
        self.assertTrue(result["success"])
        self.assertEqual(self.saved[0].authorization_mode, "production")
        self.assertIsNone(self.saved[0].expires_at)
        self.assertIn("有効期限の指定はありません", flow.page_result())
        self.assertIn("失効することがあります", flow.page_result())

    def test_production_preserves_server_refresh_expiration(self):
        self.payload["scope"] = requested_scope(True)
        self.payload["refresh_token_expires_in"] = 86400
        flow = self.sleep_flow(production=True)
        flow.begin(CLIENT_ID, SECRET)
        result = flow.complete(flow.state, "fixture-code")
        self.assertTrue(result["success"])
        self.assertEqual(self.saved[0].expires_at, "2026-11-07T00:00:00+00:00")
        self.assertIn("2026-11-07", flow.page_result())

    def test_production_steps_failure_does_not_revoke_existing_permission(self):
        flow = OfflineEnrollment(account=ACCOUNT, project_id=PROJECT, ssh_target="raspi4", production=True,
            now=self.flow.now, post=self.flow.post, api=self.flow.api,
            store=lambda *_: (_ for _ in ()).throw(RuntimeError(SECRET)))
        flow.begin(CLIENT_ID, SECRET)
        result = flow.complete(flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revocation_skipped"])
        self.assertNotIn(REVOKE_URL, self.calls)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_sleep_requires_explicit_selection_and_disclosure(self):
        self.assertNotIn("睡眠", self.flow.page_home())
        flow = self.sleep_flow()
        page = flow.page_home()
        self.assertIn("睡眠の読取り権限", page)
        self.assertIn("日別歩数と睡眠", page)
        parameters = parse_qs(urlsplit(flow.begin(CLIENT_ID, SECRET)).query)
        self.assertEqual(parameters["scope"], [requested_scope(True)])
        self.assertEqual(parameters["include_granted_scopes"], ["false"])
        self.payload["scope"] = SLEEP_SCOPE + " " + SCOPE
        result = flow.complete(flow.state, "fixture-code")
        self.assertTrue(result["success"])
        self.assertTrue(result["sleep_authorized"])
        self.assertEqual(self.saved[0].scope, requested_scope(True))
        self.assertNotIn(REVOKE_URL, self.calls)
        self.assertIn("睡眠の読取りも許可", flow.page_result())

    def test_partial_sleep_consent_preserves_stored_grant(self):
        flow = self.sleep_flow()
        flow.begin(CLIENT_ID, SECRET)
        result = flow.complete(flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertFalse(result["stored_encrypted"])
        self.assertTrue(result["revocation_skipped"])
        self.assertEqual(self.saved, [])
        self.assertNotIn(REVOKE_URL, self.calls)
        self.assertIn("保存済みの資格情報は置き換えていません", flow.page_result())
        self.assertIn("自動で取り消していません", flow.page_result())

    def test_sleep_failure_does_not_revoke_existing_steps_permission(self):
        self.payload["scope"] = requested_scope(True)
        flow = self.sleep_flow()
        flow.store = lambda *_: (_ for _ in ()).throw(RuntimeError(SECRET))
        flow.begin(CLIENT_ID, SECRET)
        result = flow.complete(flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revocation_skipped"])
        self.assertNotIn(REVOKE_URL, self.calls)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_declining_sleep_does_not_replace_or_revoke(self):
        flow = self.sleep_flow()
        flow.begin(CLIENT_ID, SECRET)
        result = flow.complete(flow.state, None, error="access_denied")
        self.assertFalse(result["success"])
        self.assertEqual(self.saved, [])
        self.assertEqual(self.calls, [])

    def test_unrequested_sleep_permission_is_not_saved_or_revoked(self):
        self.payload["scope"] = requested_scope(True)
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revocation_skipped"])
        self.assertEqual(self.saved, [])
        self.assertNotIn(REVOKE_URL, self.calls)

    def test_include_sleep_without_connect_does_not_read_config(self):
        with patch("sys.argv", ["google_enroll.py", "--include-sleep"]), \
             patch("google_enroll.Path.open", side_effect=AssertionError("ファイルを読んではいけません")), \
             patch("builtins.print"):
            self.assertEqual(main(), 2)

    def test_production_without_connect_does_not_read_config(self):
        with patch("sys.argv", ["google_enroll.py", "--production"]), \
             patch("google_enroll.Path.open", side_effect=AssertionError("ファイルを読んではいけません")), \
             patch("builtins.print"):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    unittest.main()
