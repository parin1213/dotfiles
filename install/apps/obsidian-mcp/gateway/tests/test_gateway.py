"""Obsidian MCP gateway の認可・永続化・HTTP 発見エンドポイント検証。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AccessToken, AuthContext
from starlette.testclient import TestClient

from gateway.authz import require_github_user
from gateway.gateway import UPSTREAM_URL, build_encrypted_storage, build_gateway


GITHUB_USER_ID = 1243997
OTHER_USER_ID = 583231  # GitHub の octocat
BASE_URL = "https://raspi4.tailee8e63.ts.net"


def _dummy_credentials(tmp_path: Path) -> Path:
    """ダミー資格情報を CREDENTIALS_DIRECTORY 形式で配置する。"""
    cred_dir = tmp_path / "credentials"
    cred_dir.mkdir()
    (cred_dir / "github-client-secret").write_text("dummy-github-secret", encoding="utf-8")
    (cred_dir / "jwt-signing-key").write_text(
        "dummy-jwt-signing-key-32bytes-long", encoding="utf-8"
    )
    (cred_dir / "storage-encryption-key").write_text(
        Fernet.generate_key().decode(), encoding="utf-8"
    )
    return cred_dir


def _dummy_config(tmp_path: Path) -> Path:
    """ダミー公開設定 TOML を書く。"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'base_url = "{BASE_URL}"\n'
        f'github_client_id = "Ov23liDummy"\n'
        f'github_user_id = {GITHUB_USER_ID}\n',
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def dummy_env(tmp_path: Path):
    """一時的な config / credentials / store ディレクトリを用意する。"""
    config_path = _dummy_config(tmp_path)
    cred_dir = _dummy_credentials(tmp_path)
    store_dir = tmp_path / "store"
    old_cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    os.environ["CREDENTIALS_DIRECTORY"] = str(cred_dir)
    yield {"config_path": config_path, "cred_dir": cred_dir, "store_dir": store_dir}
    if old_cred_dir is None:
        os.environ.pop("CREDENTIALS_DIRECTORY", None)
    else:
        os.environ["CREDENTIALS_DIRECTORY"] = old_cred_dir


def test_require_github_user_allows_owner():
    """AccessToken.subject が設定値と一致する場合のみ許可される。"""
    check = require_github_user(GITHUB_USER_ID)
    token = AccessToken(
        token="dummy-token",
        client_id="test-client",
        scopes=["read:user"],
        subject=str(GITHUB_USER_ID),
        claims={"sub": str(GITHUB_USER_ID)},
    )
    ctx = AuthContext(token=token, component=MagicMock())
    assert check(ctx) is True


def test_require_github_user_denies_other():
    """別人の subject では AuthorizationError を返す。"""
    check = require_github_user(GITHUB_USER_ID)
    token = AccessToken(
        token="dummy-token",
        client_id="test-client",
        scopes=["read:user"],
        subject=str(OTHER_USER_ID),
        claims={"sub": str(OTHER_USER_ID)},
    )
    ctx = AuthContext(token=token, component=MagicMock())
    with pytest.raises(AuthorizationError):
        check(ctx)


def test_require_github_user_rejects_missing_token():
    """トークンがない場合は認可を拒否する。"""
    check = require_github_user(GITHUB_USER_ID)
    ctx = AuthContext(token=None, component=MagicMock())
    assert check(ctx) is False


def test_build_encrypted_storage_persists_and_encrypts(tmp_path: Path):
    """同じ鍵・ディレクトリなら再起動後も復元でき、平文はファイルに残らない。"""
    store_dir = tmp_path / "store"
    key = Fernet.generate_key().decode()
    value = {"secret": "secret-note-content"}
    collection = "test-collection"
    item_key = "note-1"

    store_a = build_encrypted_storage(store_dir, key)

    async def save():
        await store_a.put(collection=collection, key=item_key, value=value)

    asyncio.run(save())

    for file_path in store_dir.rglob("*"):
        if file_path.is_file():
            content = file_path.read_bytes()
            assert value["secret"].encode() not in content

    store_b = build_encrypted_storage(store_dir, key)

    async def load():
        return await store_b.get(collection=collection, key=item_key)

    restored = asyncio.run(load())
    assert restored == value


def test_http_unauthenticated_mcp_rejected(dummy_env: dict):
    """未認証で MCP エンドポイントにアクセスすると 401 になる。"""
    gateway = build_gateway(
        dummy_env["config_path"],
        storage_dir=dummy_env["store_dir"],
    )
    app = gateway.http_app()
    with TestClient(app) as client:
        response = client.get("/mcp")
        assert response.status_code == 401


def test_http_oauth_metadata_endpoints(dummy_env: dict):
    """OAuth 発見エンドポイントは未認証でも 200 を返す。"""
    gateway = build_gateway(
        dummy_env["config_path"],
        storage_dir=dummy_env["store_dir"],
    )
    app = gateway.http_app()
    with TestClient(app) as client:
        auth_server_meta = client.get("/.well-known/oauth-authorization-server")
        assert auth_server_meta.status_code == 200
        data = auth_server_meta.json()
        assert "issuer" in data
        assert data["issuer"].rstrip("/") == BASE_URL

        protected_resource_meta = client.get("/.well-known/oauth-protected-resource/mcp")
        assert protected_resource_meta.status_code == 200
        resource_data = protected_resource_meta.json()
        assert "resource" in resource_data


def test_upstream_url_is_fixed():
    """proxy 接続先は固定値である。"""
    assert UPSTREAM_URL == "http://127.0.0.1:8765/mcp"
