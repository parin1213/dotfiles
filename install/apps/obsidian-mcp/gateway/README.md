# Obsidian MCP Gateway

Obsidian MCP サーバー（`127.0.0.1:8765/mcp`）の前に置く GitHub OAuth gateway です。Web 版 ChatGPT / Claude から同じ標準 HTTP MCP エンドポイントに接続でき、GitHub user ID が設定値と一致する本人だけがノートを扱えます。

## 起動

```sh
python -m gateway.gateway --config /path/to/config.toml
```

`--host`（デフォルト `127.0.0.1`）、`--port`（デフォルト `8766`）を変更できます。

## 設定

### 公開値（chezmoiで生成するTOML）

`--config` で渡す TOML は以下の公開値のみを含みます。

```toml
base_url = "https://raspi4.tailee8e63.ts.net"
github_client_id = "Ov23li..."
github_user_id = 1243997
```

### 秘密値（systemd CREDENTIALS_DIRECTORY）

秘密値は `CREDENTIALS_DIRECTORY` 環境変数で示されるディレクトリ内のファイルから読み込みます。ファイル名は以下の通りです。

| ファイル名 | 内容 |
|---|---|
| `github-client-secret` | GitHub OAuth App の Client Secret |
| `jwt-signing-key` | 導入スクリプトが `secrets.token_urlsafe(48)` で生成する署名鍵 |
| `storage-encryption-key` | Fernet 鍵（`cryptography.fernet.Fernet.generate_key()` の出力、32 bytes URL-safe base64） |

これらの値はログや例外メッセージに出力しません。

## 動作

- OAuthの登録情報とトークンは `~/.local/share/obsidian-mcp-gateway/store` のFernet暗号化FileTreeStoreで保持します。署名鍵と暗号化鍵は `~/.local/share/obsidian-mcp/credentials/` に暗号化保存し、再起動後も同じ鍵を使います。
- バックエンド MCP サーバーへの転送先は `http://127.0.0.1:8765/mcp` に固定です。外部からの URL 指定は受け付けません。
- Funnel はこの gateway の `8766` だけを公開してください。バックエンドの `8765` は直接公開しないでください。
- 未認証の HTTP リクエストは拒否されます。GitHub ログインだけでなく、検証済みトークンの GitHub user ID が `github_user_id` と一致する場合のみ、`tools/list` と tool call の両方が許可されます。

## テスト

```sh
cd install/apps/obsidian-mcp/gateway
pytest
```

テストはダミー資格情報のみ使用します。
