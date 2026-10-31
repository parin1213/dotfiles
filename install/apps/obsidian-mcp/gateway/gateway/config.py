"""設定読み込み。公開値は TOML、秘密値は systemd CREDENTIALS_DIRECTORY から取得。"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """設定または資格情報が不足している。"""


def load_config(path: Path) -> dict[str, Any]:
    """--config で渡された TOML から公開値を読む。"""
    if not path.is_file():
        raise ConfigError(f"設定ファイルが見つかりません: {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    required = ("base_url", "github_client_id", "github_user_id")
    missing = [key for key in required if key not in data]
    if missing:
        raise ConfigError(f"必須設定が不足しています: {', '.join(missing)}")

    try:
        data["github_user_id"] = int(data["github_user_id"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("github_user_id は整数である必要があります") from exc

    return data


def read_credential(name: str) -> str:
    """systemd CREDENTIALS_DIRECTORY から名前付き資格情報を読む。"""
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not cred_dir:
        raise ConfigError(
            "CREDENTIALS_DIRECTORY が設定されていません。資格情報を読み出せません"
        )
    path = Path(cred_dir) / name
    if not path.is_file():
        raise ConfigError(f"資格情報が見つかりません: {path}")
    value = path.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise ConfigError(f"資格情報が空です: {name}")
    return value
