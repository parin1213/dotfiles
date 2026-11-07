"""Offline consent preparation: fake credentials and transports only."""
from datetime import datetime, timezone
import json
import subprocess
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from google_enroll import OfflineEnrollment, store_on_pi
from google_once import REVOKE_URL
from google_steps import SCOPE
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


if __name__ == "__main__":
    unittest.main()
