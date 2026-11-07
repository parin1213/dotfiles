"""Firefoxで使う1回限りのGoogle Health読取り。資格情報はメモリだけで扱う。"""
import argparse
import base64
import hashlib
import hmac
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
from pathlib import Path
import re
import secrets
import time
import tomllib
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from google_steps import BASE, SCOPE, GoogleSteps, NoRedirect, StepsError, parse_day, request_json

ORIGIN = "http://127.0.0.1:8791"
CALLBACK = ORIGIN + "/oauth/callback"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


class AuthError(Exception):
    pass


def post_form(url, fields):
    if url not in {TOKEN_URL, REVOKE_URL}:
        raise AuthError("許可されていない接続先です")
    request = Request(url, data=urlencode(fields).encode(), method="POST", headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise AuthError("認証サーバーの応答が大きすぎます")
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        # 本文やエラー説明には資格情報が含まれ得るため出力しない。
        known = {"invalid_client", "invalid_grant", "redirect_uri_mismatch", "invalid_scope", "access_denied"}
        code = "oauth_request_failed"
        try:
            candidate = json.loads(error.read(8192)).get("error")
            if candidate in known:
                code = candidate
        except (ValueError, AttributeError, TypeError):
            pass
        raise AuthError("Googleの認証処理が失敗しました: " + code) from None
    except (URLError, OSError, ValueError):
        raise AuthError("Googleの認証サーバーへ接続できないか、応答が不正です") from None


class OneTimeRead:
    mode = "once"
    access_type = "online"
    def __init__(self, day, *, account, project_id, post=post_form, api=request_json, client_factory=GoogleSteps):
        parse_day(day)
        if not isinstance(account, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+", account) or not account.isascii():
            raise AuthError("対象アカウントの公開設定を確認してください")
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id):
            raise AuthError("専用プロジェクトの公開設定を確認してください")
        self.account, self.project_id = account, project_id
        self.day, self.post, self.api, self.client_factory = day, post, api, client_factory
        self.csrf = secrets.token_urlsafe(32)
        self.state = secrets.token_urlsafe(32)
        self.verifier = secrets.token_urlsafe(64)
        self.client_id = self.client_secret = None
        self.configured = False
        self.lock = Lock()
        self.phase = "ready"
        self.result = {"phase": "ready", "date": day}
        self.last_request = None

    @staticmethod
    def validate_client(client_id, client_secret):
        if not isinstance(client_id, str) or not isinstance(client_secret, str):
            raise AuthError("クライアント設定の形式を確認してください")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}\.apps\.googleusercontent\.com", client_id):
            raise AuthError("Client IDを確認してください")
        if not 8 <= len(client_secret) <= 512 or not client_secret.isascii() or any(c.isspace() for c in client_secret):
            raise AuthError("Client Secretを確認してください")

    def configure_from_file(self, path):
        # 本人指定のファイルをプログラムだけで処理する。中身・項目値は出力しない。
        try:
            with Path(path).open("r", encoding="utf-8-sig") as source:
                config = json.load(source)
            web = config["web"]
            if (web.get("project_id") != self.project_id
                    or CALLBACK not in web.get("redirect_uris", [])
                    or web.get("token_uri") != TOKEN_URL):
                raise AuthError("指定ファイルのプロジェクト・戻り先・Google接続先を確認できません")
            self.validate_client(web["client_id"], web["client_secret"])
            self.client_id, self.client_secret = web["client_id"], web["client_secret"]
            self.configured = True
            config.clear()
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise AuthError("指定されたクライアント設定を使用できません。中身は出力していません") from None

    def begin(self, client_id=None, client_secret=None):
        with self.lock:
            return self._begin(client_id, client_secret)

    def _begin(self, client_id=None, client_secret=None):
        if self.phase != "ready":
            raise AuthError("この画面は1回限りです。再試行する場合は起動し直してください")
        if self.configured:
            if client_id is not None or client_secret is not None:
                raise AuthError("指定ファイル以外のクライアント設定は使いません")
            client_id, client_secret = self.client_id, self.client_secret
        self.validate_client(client_id, client_secret)
        self.client_id, self.client_secret = client_id, client_secret
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()
        self.phase = "authorizing"
        self.result = {"phase": self.phase, "date": self.day}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": client_id, "redirect_uri": CALLBACK, "response_type": "code", "scope": SCOPE,
            "access_type": self.access_type, "include_granted_scopes": "false", "state": self.state,
            "code_challenge": challenge, "code_challenge_method": "S256",
            "login_hint": self.account, "prompt": "select_account consent"})

    def complete(self, state, code, error=None):
        with self.lock:
            if self.phase != "authorizing" or not isinstance(state, str) or not hmac.compare_digest(state, self.state):
                raise AuthError("認証のstateが一致しないか、この確認は処理済みです")
            self.phase = "processing"
            self.result = {"phase": "processing", "date": self.day}
        token, payload = None, None
        result = {"phase": "finished", "date": self.day, "success": False, "revoked": False}
        try:
            if error or not code or len(code) > 4096:
                raise AuthError("Googleで認証が拒否されたか、コードを受け取れませんでした")
            payload = self.post(TOKEN_URL, {"client_id": self.client_id, "client_secret": self.client_secret,
                "code": code, "code_verifier": self.verifier, "redirect_uri": CALLBACK, "grant_type": "authorization_code"})
            if not isinstance(payload, dict):
                raise AuthError("認証サーバーの応答が不正です")
            token = payload.get("access_token")
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                token = None
                raise AuthError("短期アクセストークンを受け取れませんでした")
            if payload.get("refresh_token"):
                raise AuthError("継続アクセス用トークンが含まれたため停止しました。歩数は読みません")
            if set(str(payload.get("scope", "")).split()) != {SCOPE} or str(payload.get("token_type", "")).lower() != "bearer":
                raise AuthError("許可されたスコープと一致しないため、歩数は読みません")
            identity = self.api("GET", BASE + "users/me/identity", None, token)
            identifier = identity.get("healthUserId") if isinstance(identity, dict) else None
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,63}", identifier):
                raise AuthError("Google Healthのプロフィール連携を確認できませんでした")
            snapshot = self.client_factory(token, identifier, transport=self.api).fetch_day(self.day)
            result.update(success=True, steps=snapshot.steps, missing_state=snapshot.missing_state,
                          source="google_health", fit_sync_verified=False, vault_written=False)
        except (AuthError, StepsError) as problem:
            result["error"] = str(problem)
        except Exception:
            result["error"] = "確認処理が失敗しました。資格情報を出力せず停止しました"
        finally:
            if token:
                try:
                    self.post(REVOKE_URL, {"token": token})
                    result["revoked"] = True
                except Exception:
                    result["cleanup_required"] = "許可の取消しを確認できません。Googleアカウントの接続アプリで確認してください"
            else:
                result["cleanup_required"] = "トークン未取得のため、Google側の許可状態は未確認です"
            if isinstance(payload, dict):
                payload.clear()
            token = None
            self.client_id = self.client_secret = self.verifier = None
            self.phase, self.result = "finished", result
        return result

    def retry(self):
        with self.lock:
            if self.phase != "authorizing" or not self.configured or self.client_secret is None:
                raise AuthError("処理中または完了後の認証はやり直しません")
            self.state = secrets.token_urlsafe(32)
            self.verifier = secrets.token_urlsafe(64)
            self.csrf = secrets.token_urlsafe(32)
            self.phase = "ready"
            return self._begin()


def make_server(flow, port=8791):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_):
            pass

        def send(self, status, body="", *, location=None, json_type=False, referrer_policy="no-referrer"):
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8" if json_type else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", referrer_policy)
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://accounts.google.com; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            return self.headers.get_all("Host") == [f"127.0.0.1:{self.server.server_port}"]

        def diagnose(self, outcome, csrf_valid=None):
            expected = f"http://127.0.0.1:{self.server.server_port}"
            origins = self.headers.get_all("Origin")
            kind = "absent" if not origins else "null" if origins == ["null"] else "same_origin" if origins == [expected] else "other_or_duplicate"
            referer = self.headers.get("Referer")
            try:
                parsed = urlsplit(referer) if referer else None
                same_referer = parsed is not None and parsed.scheme + "://" + parsed.netloc == expected
            except ValueError:
                same_referer = False
            site = self.headers.get("Sec-Fetch-Site")
            flow.last_request = {"method": self.command, "host_match": self.allowed(), "origin_kind": kind,
                "referer_kind": "absent" if not referer else "same_origin" if same_referer else "other",
                "fetch_site": site if site in {"same-origin", "same-site", "cross-site", "none"} else "absent_or_other",
                "csrf_valid": csrf_valid, "outcome": outcome}

        def do_GET(self):
            if not self.allowed():
                self.diagnose("host_rejected")
                return self.send(403, "ローカル画面のHost検査で拒否しました。127.0.0.1:8791を使用してください。")
            url = urlsplit(self.path)
            if url.path == "/status":
                return self.send(200, json.dumps({**flow.result, "last_request": flow.last_request}, ensure_ascii=False), json_type=True)
            if url.path == "/oauth/callback":
                parameters = parse_qs(url.query)
                try:
                    if any(len(v) != 1 for v in parameters.values()): raise AuthError("認証応答が不正です")
                    flow.complete(parameters.get("state", [None])[0], parameters.get("code", [None])[0], parameters.get("error", [None])[0])
                except AuthError:
                    return self.send(400, "認証応答を受け付けませんでした。資格情報は出力していません。")
                return self.send(303, location="/result")
            if url.path == "/result":
                if flow.mode == "offline":
                    return self.send(200, flow.page_result(), referrer_policy="same-origin" if flow.phase == "authorizing" else "no-referrer")
                import html
                retry_form = ""
                if flow.phase == "ready":
                    content = "<h1>まだ認証を開始していません</h1><p><a href='/'>開始画面を開く</a></p>"
                elif flow.phase == "authorizing":
                    content = "<h1>Googleでの認証を待っています</h1><p>これは取得完了の結果ではありません。Googleのタブでアカウントと権限を確認してください。</p>"
                    if flow.configured:
                        retry_form = f"<p>Google側のエラーを解決してから、必要な場合だけやり直してください。</p><form action='/retry' method='post'><input type='hidden' name='csrf' value='{flow.csrf}'><button>認証を最初からやり直す</button></form>"
                elif flow.phase == "processing":
                    content = "<h1>歩数を確認しています</h1><p>取得と許可の取消しが終わるまでお待ちください。</p>"
                elif flow.result.get("success"):
                    steps = flow.result.get("steps")
                    value = "歩数は未記録です" if steps is None else str(steps) + "歩"
                    content = f"<h1>{flow.day}: {value}</h1><p>Google Healthから一時的に取得しました。Google Fitの同じ日の表示と比較してください。Vaultへは保存していません。</p>"
                else:
                    content = "<h1>歩数を取得できませんでした</h1><p>" + html.escape(flow.result.get("error", "確認処理が完了していません")) + "</p>"
                if flow.phase == "finished":
                    content += "<p>Googleへの許可取消しを確認しました。</p>" if flow.result.get("revoked") else "<p>Google側の許可状態は確認が必要です。<a href='https://myaccount.google.com/connections'>Googleアカウントの接続アプリ</a>で確認してください。</p>"
                return self.send(200, "<!doctype html><html lang='ja'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>歩数確認</title><style>body{max-width:680px;margin:40px auto;padding:20px;font:17px/1.8 system-ui}button{padding:12px;font:inherit}</style>" + content + retry_form + "</html>", referrer_policy="same-origin" if retry_form else "no-referrer")
            if url.path != "/" or url.query: return self.send(404)
            if flow.phase != "ready": return self.send(303, location="/result")
            if flow.mode == "offline":
                return self.send(200, flow.page_home(), referrer_policy="same-origin")
            client_fields = "<p>本人が指定した設定ファイルをプログラムが直接使用します。項目の値やファイル内容は表示しません。</p>" if flow.configured else "<label>Client ID<input name='client_id' required maxlength='250' autocomplete='off'></label><label>Client Secret<input type='password' name='client_secret' required maxlength='512' autocomplete='off'></label>"
            return self.send(200, f"""<!doctype html><html lang='ja'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Google Health 一時歩数確認</title>
<style>body{{max-width:680px;margin:40px auto;padding:20px;font:17px/1.8 system-ui;background:#f5f1ec;color:#303941}}input{{display:block;box-sizing:border-box;width:100%;padding:12px;margin:6px 0 20px;font:inherit}}button{{padding:12px;font:inherit}}</style>
<h1>Google Health 一時歩数確認</h1><p>対象: {flow.account} / {flow.day} の1日分</p><p>ご自身のFirefoxで使ってください。Googleの画面でも、このアカウントを選んだことを確認してください。</p>
<p>Client IDとClient SecretはこのPCのメモリ内だけで使います。チャット・ファイル・Vaultへ保存しません。短期アクセスだけを要求し、確認後は専用プロジェクトへのOAuth許可を取り消します。</p>
<form action='/authorize' method='post' autocomplete='off'><input type='hidden' name='csrf' value='{flow.csrf}'>
{client_fields}
<button>FirefoxでGoogleの一時読取り認証へ進む</button></form><p>要求する権限は活動・フィットネスの読取りだけです。Google側への書込み・継続同期・refresh tokenは要求しません。</p></html>""", referrer_policy="same-origin")

        def do_POST(self):
            if not self.allowed():
                self.diagnose("host_rejected")
                return self.send(403, "ローカル開始処理のHost検査で拒否しました。開始画面を開き直してください。")
            if self.headers.get_all("Origin") != [f"http://127.0.0.1:{self.server.server_port}"]:
                self.diagnose("origin_rejected")
                return self.send(403, "ローカル開始処理のOrigin検査で拒否しました。開始画面を再読み込みしてから開始してください。")
            if self.path not in {"/authorize", "/retry"}: return self.send(404)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096 or self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                    raise AuthError("入力形式を確認してください")
                fields = parse_qs(self.rfile.read(size).decode("utf-8"), strict_parsing=True)
                expected_fields = {"csrf"} if flow.configured or self.path == "/retry" else {"csrf", "client_id", "client_secret"}
                if set(fields) != expected_fields or any(len(v) != 1 for v in fields.values()):
                    raise AuthError("入力形式を確認してください")
                if not hmac.compare_digest(fields["csrf"][0], flow.csrf):
                    self.diagnose("csrf_rejected", False)
                    raise AuthError("入力元を確認できません")
                location = flow.retry() if self.path == "/retry" else flow.begin() if flow.configured else flow.begin(fields["client_id"][0], fields["client_secret"][0])
                fields.clear()
                self.diagnose("google_retry_redirect_sent" if self.path == "/retry" else "google_redirect_sent", True)
                return self.send(303, location=location)
            except (AuthError, ValueError, UnicodeError):
                return self.send(400, "入力を確認してください。入力値は出力していません。")

    class Server(ThreadingHTTPServer):
        # 終了時も処理中のトークン取消しを待ち、途中でプロセスを捨てない。
        daemon_threads = False

    return Server(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--client-config", type=Path, required=True, help="本人がプログラム使用を許可したGoogleのJSON。中身は出力しない")
    parser.add_argument("--settings", type=Path, default=Path(__file__).resolve().parents[3] / "home/.chezmoidata.toml", help="対象アカウントと専用プロジェクトを記した公開設定")
    args = parser.parse_args()
    try:
        with args.settings.open("rb") as source:
            settings = tomllib.load(source)["health_steps_sync"]
        flow = OneTimeRead(args.date, account=settings["account"], project_id=settings["project_id"])
        flow.configure_from_file(args.client_config)
    except AuthError as problem:
        print(str(problem), flush=True)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, TypeError):
        print("公開設定が不足または不正です。資格情報は出力しません。", flush=True)
        raise SystemExit(1) from None
    server = make_server(flow)
    server.timeout = 1
    print("Firefoxで http://127.0.0.1:8791 を開いてください。資格情報はチャットへ送らないでください。", flush=True)
    deadline = time.monotonic() + 20 * 60
    try:
        while time.monotonic() < deadline:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        flow.client_id = flow.client_secret = flow.verifier = None
