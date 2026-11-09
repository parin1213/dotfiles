"""一時OAuthの安全条件を、架空の資格情報だけで確認する。"""
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import socket
import threading
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit
from google_once import CALLBACK, SCOPE, TOKEN_URL, REVOKE_URL, AuthError, OneTimeRead, make_server
from google_steps import civil
from health_scopes import SLEEP_SCOPE
from datetime import date

CLIENT_ID = "123-fixture.apps.googleusercontent.com"
SECRET = "fixture-secret-not-real"
TOKEN = "fixture-access-token"
ACCOUNT = "test@example.invalid"
PROJECT = "test-health-project"


def config():
    return {"web": {"project_id": PROJECT, "client_id": CLIENT_ID,
                    "client_secret": SECRET, "token_uri": TOKEN_URL, "redirect_uris": [CALLBACK]}}


class OneTimeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.token_extra = {}
        def post(url, fields):
            self.calls.append((url, dict(fields)))
            if url == REVOKE_URL: return {}
            return {"access_token": TOKEN, "token_type": "Bearer", "scope": SCOPE, **self.token_extra}
        def api(method, url, payload, token):
            self.calls.append((method, url))
            if method == "GET": return {"healthUserId": "fixture-user"}
            return {"rollupDataPoints": [{"civilStartTime": civil(date(2026, 11, 5)), "civilEndTime": civil(date(2026, 11, 6)), "steps": {"countSum": "0"}}]}
        self.flow = OneTimeRead("2026-11-05", account=ACCOUNT, project_id=PROJECT, post=post, api=api)

    def test_online_scope_pkce_and_account(self):
        url = self.flow.begin(CLIENT_ID, SECRET)
        parameters = parse_qs(urlsplit(url).query)
        self.assertEqual(parameters["scope"], [SCOPE])
        self.assertEqual(parameters["access_type"], ["online"])
        self.assertEqual(parameters["include_granted_scopes"], ["false"])
        self.assertEqual(parameters["login_hint"], [ACCOUNT])
        self.assertEqual(parameters["redirect_uri"], [CALLBACK])
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.assertNotIn(SECRET, url)
        self.assertNotIn(self.flow.verifier, url)

    def test_success_revoke_and_no_secrets_in_result(self):
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertTrue(result["success"])
        self.assertTrue(result["revoked"])
        self.assertEqual(result["steps"], 0)
        self.assertFalse(result["vault_written"])
        for secret in (SECRET, TOKEN, "fixture-code", "fixture-user"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIsNone(self.flow.client_secret)
        self.assertEqual(self.calls[-1], (REVOKE_URL, {"token": TOKEN}))
        with self.assertRaises(AuthError): self.flow.complete(self.flow.state, "fixture-code")

    def test_bad_state_never_exchanges_code(self):
        self.flow.begin(CLIENT_ID, SECRET)
        with self.assertRaises(AuthError): self.flow.complete("wrong", "fixture-code")
        self.assertEqual(self.calls, [])

    def test_retry_invalidates_old_state_and_cannot_repeat_finished_read(self):
        self.flow.client_id, self.flow.client_secret, self.flow.configured = CLIENT_ID, SECRET, True
        self.flow.begin()
        old_state = self.flow.state
        self.flow.retry()
        self.assertNotEqual(self.flow.state, old_state)
        with self.assertRaises(AuthError): self.flow.complete(old_state,"fixture-code")
        self.flow.complete(self.flow.state,"fixture-code")
        with self.assertRaises(AuthError): self.flow.retry()

    def test_refresh_token_stops_before_health_data(self):
        self.token_extra["refresh_token"] = "fixture-refresh-token"
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revoked"])
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("fixture-refresh-token", json.dumps(result))

    def test_extra_scope_stops_before_health_data(self):
        self.token_extra["scope"] = SCOPE + " unwanted-scope"
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revoked"])
        self.assertEqual(len(self.calls), 2)

    def test_sleep_scope_is_not_accepted_for_one_time_steps(self):
        self.token_extra["scope"] = SCOPE + " " + SLEEP_SCOPE
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertFalse(result["success"])
        self.assertTrue(result["revoked"])
        self.assertEqual(len(self.calls), 2)

    def test_revoke_failure_reported(self):
        real_post = self.flow.post
        def failing(url, fields):
            if url == REVOKE_URL: raise RuntimeError("private token must not appear")
            return real_post(url, fields)
        self.flow.post = failing
        self.flow.begin(CLIENT_ID, SECRET)
        result = self.flow.complete(self.flow.state, "fixture-code")
        self.assertTrue(result["success"])
        self.assertFalse(result["revoked"])
        self.assertIn("cleanup_required", result)
        self.assertNotIn("private token", json.dumps(result))

    def test_config_is_program_only_and_checks_destination(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(config()), encoding="utf-8")
            self.flow.configure_from_file(path)
            self.assertTrue(self.flow.configured)
            url = self.flow.begin()
            self.assertNotIn(SECRET, url)
            bad = config()
            bad["web"]["token_uri"] = "https://other.example/token"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(AuthError): OneTimeRead("2026-11-05",account=ACCOUNT,project_id=PROJECT).configure_from_file(path)

    def test_configured_http_never_exposes_credentials(self):
        self.flow.client_id, self.flow.client_secret, self.flow.configured = CLIENT_ID, SECRET, True
        server = make_server(self.flow, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None, headers=None):
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request(method, path, body, headers or {})
            response = conn.getresponse()
            status, raw, received = response.status, response.read(), dict(response.getheaders())
            conn.close()
            return status, raw, received
        try:
            # FirefoxがHTTPを送らず接続だけを先に開いても、他の要求を止めない。
            idle = socket.create_connection(("127.0.0.1", server.server_port), timeout=3)
            status, raw, headers = request("GET", "/")
            idle.close()
            self.assertEqual(status, 200)
            self.assertNotIn(SECRET.encode(), raw)
            self.assertNotIn(CLIENT_ID.encode(), raw)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["Referrer-Policy"], "same-origin")
            self.assertEqual(request("GET", "/", headers={"Host":"other.example"})[0], 403)
            form = urlencode({"csrf":self.flow.csrf})
            headers = {"Content-Type":"application/x-www-form-urlencoded", "Origin":f"http://127.0.0.1:{server.server_port}"}
            self.assertEqual(request("POST", "/authorize", form, headers | {"Origin":"https://other.example"})[0], 403)
            # no-referrerではフォームPOSTのOriginがnullになり、以前の画面では403になる。
            self.assertEqual(request("POST", "/authorize", form, headers | {"Origin":"null"})[0], 403)
            self.assertEqual(self.flow.last_request["origin_kind"], "null")
            self.assertEqual(request("POST", "/authorize", urlencode({"csrf":"wrong"}), headers)[0], 400)
            self.assertEqual(self.flow.last_request["outcome"], "csrf_rejected")
            headers |= {"Referer":f"http://127.0.0.1:{server.server_port}/", "Sec-Fetch-Site":"same-origin", "Sec-Fetch-Mode":"navigate"}
            status, raw, received = request("POST", "/authorize", form, headers)
            self.assertEqual(status, 303)
            self.assertNotIn(SECRET, received["Location"])
            self.assertEqual(urlsplit(received["Location"]).hostname, "accounts.google.com")
            self.assertEqual(parse_qs(urlsplit(received["Location"]).query)["access_type"], ["online"])
            self.assertEqual(self.flow.last_request["outcome"], "google_redirect_sent")
            self.assertTrue(self.flow.last_request["csrf_valid"])
            self.assertEqual(self.flow.last_request["referer_kind"], "same_origin")
            self.assertEqual(received["Referrer-Policy"], "no-referrer")
            status, pending, policy = request("GET", "/result")
            self.assertIn("Googleでの認証を待っています".encode(), pending)
            self.assertNotIn(b'"phase"', pending)
            self.assertEqual(policy["Referrer-Policy"], "same-origin")
            self.assertEqual(request("POST", "/retry", urlencode({"csrf":self.flow.csrf}), headers)[0],303)
            self.assertEqual(request("GET", "/oauth/callback?state=wrong&code=fixture-code")[0], 400)
            self.assertEqual(self.calls, [])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
