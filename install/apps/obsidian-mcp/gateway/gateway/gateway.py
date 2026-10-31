"""Obsidian MCP 用 GitHub OAuth gateway。

現行の MCP サーバー（127.0.0.1:8765/mcp）の前に立ち、GitHub OAuth で
認証した上で、特定の GitHub user ID のみがツールを扱えるようにする。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.server import create_proxy
from fastmcp.server.middleware import AuthMiddleware
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from .authz import require_github_user
from .diagnostics import ToolDiagnostics, configure, DiagnosticGitHubProvider as GitHubProvider
from .config import load_config, read_credential

# 現行 MCP サーバーへの接続先は固定。外部からの変更を受け付けない。
UPSTREAM_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_STORE_DIR = Path.home() / ".local" / "share" / "obsidian-mcp-gateway" / "store"


def build_encrypted_storage(
    storage_dir: Path, encryption_key: str
) -> FernetEncryptionWrapper:
    """暗号化されたファイル永続ストアを構築する。"""
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_store = FileTreeStore(
        data_directory=storage_dir,
        key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(storage_dir),
        collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(
            storage_dir
        ),
    )
    return FernetEncryptionWrapper(
        key_value=file_store,
        fernet=Fernet(key=encryption_key.encode("utf-8")),
    )


def build_gateway(
    config_path: Path,
    *,
    storage_dir: Path | None = None,
) -> FastMCP:
    """config / credentials から gateway サーバーを組み立てる。"""
    cfg = load_config(config_path)
    base_url: str = cfg["base_url"]
    github_client_id: str = cfg["github_client_id"]
    github_user_id: int = cfg["github_user_id"]

    # 秘密値は systemd CREDENTIALS_DIRECTORY からのみ読み出し、ログに絶対に出さない
    github_client_secret = read_credential("github-client-secret")
    jwt_signing_key = read_credential("jwt-signing-key")
    storage_encryption_key = read_credential("storage-encryption-key")

    if storage_dir is None:
        storage_dir = DEFAULT_STORE_DIR

    encrypted_storage = build_encrypted_storage(
        storage_dir=storage_dir,
        encryption_key=storage_encryption_key,
    )

    auth = GitHubProvider(
        client_id=github_client_id,
        client_secret=github_client_secret,
        base_url=base_url,
        redirect_path="/auth/callback",
        required_scopes=["read:user"],
        jwt_signing_key=jwt_signing_key,
        client_storage=encrypted_storage,
    )

    gateway = FastMCP("obsidian-mcp-gateway", auth=auth)
    gateway.add_middleware(ToolDiagnostics())
    gateway.add_middleware(
        AuthMiddleware(auth=require_github_user(github_user_id))
    )

    # 固定 upstream への proxy のみをマウント
    backend = create_proxy(UPSTREAM_URL)
    gateway.mount(backend)

    return gateway


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="公開設定を含む TOML ファイルのパス",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8766,
        help="gateway の待ち受けポート（デフォルト: 8766）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="gateway の待ち受けアドレス（デフォルト: 127.0.0.1）",
    )
    args = parser.parse_args()
    configure()

    gateway = build_gateway(args.config)
    # OAuth callback の code を journal に残さないためアクセスログを無効化
    gateway.run(
        transport="http",
        host=args.host,
        port=args.port,
        show_banner=False,
        uvicorn_config={"access_log": False},
    )


if __name__ == "__main__":
    main()
