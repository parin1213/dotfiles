"""継続同期用資格情報。実行時の復号ファイルだけを読み、内容を出力しない。"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from google_once import OneTimeRead
from google_steps import SCOPE


class CredentialError(Exception):
    pass


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise CredentialError("資格情報の有効期間を確認できません") from None


@dataclass(frozen=True, repr=False)
class Bundle:
    client_id: str
    client_secret: str
    refresh_token: str
    health_user_id: str
    authorized_at: str
    expires_at: str
    account: str
    project_id: str
    scope: str = SCOPE

    def validate(self):
        try:
            OneTimeRead.validate_client(self.client_id, self.client_secret)
        except Exception:
            raise CredentialError("クライアント資格情報が不正です") from None
        if (not isinstance(self.account, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+", self.account) or not self.account.isascii()
                or not isinstance(self.project_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", self.project_id)
                or self.scope != SCOPE
                or not isinstance(self.refresh_token, str) or not 8 <= len(self.refresh_token) <= 4096
                or not self.refresh_token.isascii() or any(c.isspace() for c in self.refresh_token)
                or not isinstance(self.health_user_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,63}", self.health_user_id)):
            raise CredentialError("本人・許可スコープ・資格情報を確認できません")
        start, end = timestamp(self.authorized_at), timestamp(self.expires_at)
        if not start < end <= start + timedelta(days=7):
            raise CredentialError("テスト中の7日以内の資格情報だけを使用します")
        return self

    def live(self, now):
        self.validate()
        if now.utcoffset() is None or not timestamp(self.authorized_at) <= now < timestamp(self.expires_at):
            raise CredentialError("資格情報は未有効または期限切れです")
        return self

    def serialized(self):
        # 呼出側の暗号化処理にだけ渡す。ログ・状態APIで使用しない。
        return json.dumps({"client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.refresh_token, "health_user_id": self.health_user_id,
            "authorized_at": self.authorized_at, "expires_at": self.expires_at,
            "account": self.account, "project_id": self.project_id, "scope": self.scope}, ensure_ascii=True).encode()


def from_grant(client_id, client_secret, payload, health_user_id, *, authorized_at, account, project_id):
    """承認後の接続処理が使う変換。ここではOAuthも保存も行わない。"""
    try:
        if set(payload["scope"].split()) != {SCOPE} or str(payload["token_type"]).lower() != "bearer":
            raise CredentialError("許可スコープが一致しません")
        duration = payload.get("refresh_token_expires_in", 7 * 24 * 60 * 60)
        if type(duration) is not int or not 0 < duration <= 7 * 24 * 60 * 60:
            raise CredentialError("継続資格情報の有効期間が不正です")
        end = authorized_at + timedelta(seconds=duration)
        return Bundle(client_id, client_secret, payload["refresh_token"], health_user_id,
                      authorized_at.isoformat(), end.isoformat(), account, project_id).validate()
    except (KeyError, ValueError, TypeError, AttributeError):
        raise CredentialError("継続資格情報を受け取れませんでした") from None


def load_runtime(directory):
    try:
        folder = Path(directory)
        target = folder / "google-health.json"
        if (not folder.is_absolute() or not folder.is_dir() or folder.is_symlink()
                or target.is_symlink() or target.stat().st_size > 16384):
            raise CredentialError("実行時資格情報の場所が不正です")
        if os.name == "posix" and (target.stat().st_uid != os.getuid() or target.stat().st_mode & 0o077):
            raise CredentialError("実行時資格情報の所有者または権限が不正です")
        with target.open(encoding="utf-8") as source:
            data = json.load(source)
        bundle = Bundle(**data).validate()
        data.clear()
        return bundle
    except (OSError, ValueError, TypeError):
        raise CredentialError("実行時資格情報を読み込めません。内容は出力しません") from None


def encrypt_bundle(bundle, destination):
    """承認後にだけ使う暗号化保存。秘密値は引数・stdout・stderrへ出さない。"""
    bundle.validate()
    target = Path(destination)
    if not target.is_absolute() or target.is_symlink():
        raise CredentialError("暗号化保存先が不正です")
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=".credential-", dir=target.parent) as temporary:
            encrypted = Path(temporary) / "google-health.cred"
            result = subprocess.run(["systemd-creds", "encrypt", "--user", "--with-key=host", "--name=google-health", "-", str(encrypted)],
                                    input=bundle.serialized(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if result.returncode or not encrypted.is_file():
                raise CredentialError("資格情報を暗号化できませんでした")
            encrypted.chmod(0o600)
            os.replace(encrypted, target)
    except (OSError, subprocess.TimeoutExpired):
        raise CredentialError("資格情報を安全に保存できませんでした") from None


def rotated(bundle, refresh_token):
    # 更新があっても本人の当初の同意期限を延ばさない。
    return replace(bundle, refresh_token=refresh_token).validate()
