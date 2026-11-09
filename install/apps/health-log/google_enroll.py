"""承認後だけ起動する継続同意とPiへの暗号化受渡し。通常起動では何もしない。"""
import argparse
from datetime import datetime, timezone
import hmac
import html
from pathlib import Path
import re
import shlex
import subprocess
import time
import tomllib
from google_once import AuthError, OneTimeRead, CALLBACK, TOKEN_URL, REVOKE_URL, make_server
from google_steps import BASE, SCOPE, StepsError
from health_scopes import requested_scope, scope_set
from sync_credentials import CredentialError, from_grant


def store_on_pi(bundle, ssh_target):
    if not isinstance(ssh_target, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", ssh_target):
        raise CredentialError("承認されたSSH接続先を確認してください")
    code = '''import json,pathlib,sys,tomllib
root=pathlib.Path.home()/"src/dotfiles"
sys.path.insert(0,str(root/"install/apps/health-log"))
from sync_credentials import Bundle,encrypt_bundle
settings=tomllib.loads((root/"home/.chezmoidata.toml").read_text())["health_steps_sync"]
bundle=Bundle(**json.load(sys.stdin)).validate()
if bundle.account!=settings["account"] or bundle.project_id!=settings["project_id"]: sys.exit(2)
encrypt_bundle(bundle,pathlib.Path.home()/".local/share/health-steps-sync/credentials/google-health.cred")
'''
    try:
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", ssh_target,
                                 "python3 -c " + shlex.quote(code)], input=bundle.serialized(),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        if result.returncode:
            raise CredentialError("Piへの暗号化受渡しが完了しませんでした")
    except (OSError, subprocess.TimeoutExpired):
        raise CredentialError("Piへの暗号化受渡しを確認できませんでした") from None


class OfflineEnrollment(OneTimeRead):
    mode = "offline"
    access_type = "offline"

    def __init__(self, *, account, project_id, ssh_target, include_sleep=False, production=False,
                 store=None, now=None, **kwargs):
        if type(production) is not bool:
            raise AuthError("公開モードを確認してください")
        self.now = now or (lambda: datetime.now(timezone.utc))
        super().__init__(str(self.now().date()), account=account, project_id=project_id, **kwargs)
        self.requested_scope = requested_scope(include_sleep)
        self.include_sleep = include_sleep
        self.authorization_mode = "production" if production else "testing"
        self.ssh_target = ssh_target
        self.store = store or (lambda bundle: store_on_pi(bundle, ssh_target))

    def complete(self, state, code, error=None):
        with self.lock:
            if self.phase != "authorizing" or not isinstance(state, str) or not hmac.compare_digest(state, self.state):
                raise AuthError("認証が一致しないか処理済みです")
            self.phase = "processing"
            self.result = {"phase": "processing", "mode": "offline_enrollment"}
        result = {"phase": "finished", "mode": "offline_enrollment", "success": False,
                  "stored_encrypted": False, "revoked": False, "scheduler_enabled": False}
        token, response, stored = None, None, False
        revoke_safe = not self.include_sleep and self.authorization_mode == "testing"
        try:
            if error or not code or len(code) > 4096:
                raise AuthError("Googleの継続同意を完了できませんでした")
            response = self.post(TOKEN_URL, {"client_id": self.client_id, "client_secret": self.client_secret,
                "code": code, "code_verifier": self.verifier, "redirect_uri": CALLBACK, "grant_type": "authorization_code"})
            if not isinstance(response, dict): raise AuthError("認証応答が不正です")
            # 範囲が広い許可の取消しは、稼働中の歩数同期も止める可能性がある。
            revoke_safe = revoke_safe and response.get("scope") == SCOPE
            token = response.get("access_token")
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                token = None
                raise AuthError("一時アクセストークンが不正です")
            try:
                if scope_set(response.get("scope")) != scope_set(self.requested_scope):
                    raise ValueError()
            except ValueError:
                raise AuthError("要求した読取り権限がすべて許可されていないか、範囲が一致しません。保存済みの資格情報は置き換えていません") from None
            identity = self.api("GET", BASE + "users/me/identity", None, token)
            subject = identity.get("healthUserId") if isinstance(identity, dict) else None
            bundle = from_grant(self.client_id, self.client_secret, response, subject,
                                authorized_at=self.now(), account=self.account, project_id=self.project_id,
                                expected_scope=self.requested_scope, authorization_mode=self.authorization_mode)
            self.store(bundle)
            stored = True
            result.update(success=True, stored_encrypted=True, expires_at=bundle.expires_at,
                          sleep_authorized=self.include_sleep, authorization_mode=bundle.authorization_mode)
        except (AuthError, StepsError, CredentialError) as problem:
            result["error"] = str(problem)
        except Exception:
            result["error"] = "継続同意または受渡しが失敗しました。秘密値は出力しません"
        finally:
            if token and not stored and revoke_safe:
                try:
                    self.post(REVOKE_URL, {"token": token})
                    result["revoked"] = True
                except Exception:
                    result["cleanup_required"] = "Google側の許可取消しを確認してください"
            elif token and not stored:
                result["revocation_skipped"] = True
                result["cleanup_required"] = "歩数同期への影響を避けるため許可は自動で取り消していません。Google側の権限と保存状態を確認してください"
            if isinstance(response, dict): response.clear()
            token = None
            self.client_id = self.client_secret = self.verifier = None
            self.phase, self.result = "finished", result
        return result

    def page_home(self):
        permissions = "活動・フィットネスと睡眠の読取り権限" if self.include_sleep else "活動・フィットネスの読取り権限"
        records = "日別歩数と睡眠" if self.include_sleep else "日別歩数"
        lifetime = ("Google Cloudの公開ステータスを「In Production」に変更済みの場合だけ、新しく同意を取得します。"
                    "Googleから有効期限が返された場合はその期限を保存します。固定期限がなくても、取消しや長期未使用などで失効します。"
                    if self.authorization_mode == "production" else "テスト中のため有効期間は最大7日です。")
        return f"""<!doctype html><html lang='ja'><meta charset='utf-8'><title>継続同期の接続</title>
<h1>継続アクセスとPiへの暗号化保存</h1><p>対象アカウント: {html.escape(self.account)}</p>
<p>{permissions}とrefresh tokenを取得し、{html.escape(self.ssh_target)}へSSHで送り、暗号化保存します。Client Secret・Health user IDも専用状態に含めます。</p>
<p>{lifetime}タイマー、課金、公開モードはこの画面では変更しません。今後の今日・昨日の{records}同期のための接続です。</p>
<p>明示的に承認済みの場合だけ進めてください。指定JSONの中身や秘密値は表示しません。</p>
<form action='/authorize' method='post'><input type='hidden' name='csrf' value='{self.csrf}'><button>Firefoxで継続アクセスの同意へ進む</button></form></html>"""

    def page_result(self):
        if self.phase in {"authorizing", "processing"}:
            text = "Googleの同意または暗号化受渡しが完了していません。取得成功とは扱いません。"
        elif self.result.get("success"):
            text = "継続資格情報をPiへ暗号化保存しました。タイマーは有効化していません。"
            text += ("期限: " + self.result["expires_at"] if self.result["expires_at"] is not None else
                     "Googleから有効期限の指定はありません。取消し等で失効することがあります。")
            text += " 睡眠の読取りも許可されています。" if self.result.get("sleep_authorized") else " 歩数の読取りだけが許可されています。"
        else:
            text = self.result.get("error", "継続アクセスの接続は未開始です")
            text += " 許可取消し確認済み。" if self.result.get("revoked") else " Google側の許可状態は未確認です。"
            if self.result.get("cleanup_required"):
                text += " " + self.result["cleanup_required"]
        return "<!doctype html><html lang='ja'><meta charset='utf-8'><title>接続状態</title><h1>継続接続の状態</h1><p>" + html.escape(text) + "</p></html>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect", action="store_true", help="継続アクセスとPiへの保存が明示承認された後にだけ使用")
    parser.add_argument("--include-sleep", action="store_true", help="睡眠の継続読取りも承認された場合だけ追加。--connectが必要")
    parser.add_argument("--production", action="store_true", help="In Productionへの変更を確認した後、新しく同意を取得する。--connectが必要")
    parser.add_argument("--client-config", type=Path)
    parser.add_argument("--settings", type=Path, default=Path(__file__).resolve().parents[3]/"home/.chezmoidata.toml")
    args = parser.parse_args()
    if not args.connect:
        print("継続アクセスとPiへの暗号化保存の承認が必要です。認証やファイル読取りは開始していません。")
        return 2
    try:
        with args.settings.open("rb") as source: settings = tomllib.load(source)["health_steps_sync"]
        flow = OfflineEnrollment(account=settings["account"], project_id=settings["project_id"], ssh_target=settings["ssh_target"],
                                 include_sleep=args.include_sleep, production=args.production)
        flow.configure_from_file(args.client_config)
        server = make_server(flow)
    except Exception:
        print("公開設定または承認済みクライアント設定を使用できません。内容は出力しません。")
        return 1
    server.timeout = 1
    print("承認済みの場合だけ、ご自身のFirefoxで http://127.0.0.1:8791 を開いてください。",flush=True)
    deadline = time.monotonic()+20*60
    try:
        while time.monotonic()<deadline: server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        flow.client_id=flow.client_secret=flow.verifier=None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
