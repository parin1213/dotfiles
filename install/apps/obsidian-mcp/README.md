# Obsidianをチャットから使う

vault内のMarkdownを検索し、本文を取得して、会話の要点を新しいノートに保存するMCPです。
Obsidian本体の起動は不要です。
既存ノートの編集と削除は扱いません。

## ラズパイでの導入

Python 3.13、mise、systemdのユーザーサービスを使います。
依存は `uv.lock` で固定し、Takumi Guard、7日の公開待機期間、ビルド無効を設定しています。

```sh
cd ~/src/dotfiles
bash install/apps/obsidian-mcp.sh
systemctl --user status obsidian-mcp.service
```

配置先は `~/obsidian-vault` です。
そのディレクトリが存在しなければ、空のvaultを作らず登録を保留します。
別のvaultを指定する場合は `OBSIDIAN_VAULT=/absolute/path` を付けて実行します。
ラズパイでは、systemdユーザータイマーが5分ごとに `~/.local/bin/obsidian-vault-sync` を起動します。
同期先はprivateの `parin1213/obsidian-vault` です。
`vault_sync` が有効なLinuxでは、`chezmoi apply` で同期タイマーを登録します。
アプリの導入対象は `.chezmoidata.toml` の `envs.raspi.apps` で管理します。
既存のHome Assistantは独立して稼働します。

接続先はラズパイ内の `http://127.0.0.1:8765/mcp` です。
外部からの接続は受け付けません。
SSHログインを閉じても動かすには `loginctl show-user "$USER" -p Linger` が `Linger=yes` であることを確認します。

## Web版ChatGPTとClaudeへの接続

共通の接続先は `https://raspi4.tailee8e63.ts.net/mcp` です。
GitHub OAuthでログインし、設定したGitHub user IDに一致する本人だけがツールを使えます。
[FastMCPのGitHubProvider](https://gofastmcp.com/integrations/github)がOAuthを扱い、
[Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel)が認証入口の8766番ポートをHTTPSで公開します。
8765番ポートはラズパイ内のMCP接続専用です。

1. GitHubのOAuth Appを登録する。Homepageは `https://raspi4.tailee8e63.ts.net`、callbackは `https://raspi4.tailee8e63.ts.net/auth/callback` にする。
2. 公開値を `home/.chezmoidata.toml` の `obsidian_mcp` に設定し、ラズパイで `chezmoi apply` する。
3. Windowsで `powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME/.local/bin/obsidian-mcp-oauth.ps1"` を実行し、Client Secretを入力する。
4. ラズパイで `bash ~/src/dotfiles/install/apps/obsidian-mcp.sh` を実行する。署名鍵と保存用の暗号化鍵は初回だけ生成する。
5. 認証なしのMCPリクエストが拒否されることを確認してから `tailscale funnel --bg 8766` を実行する。
6. ChatGPTとClaudeのカスタムMCPに共通URLを登録し、GitHubで本人ログインする。
7. 各チャットで検索と新規保存を行い、Obsidian側の実ファイルまで確認する。

Client SecretはSSHの標準入力で送り、ラズパイの `~/.local/share/obsidian-mcp/credentials/` に `systemd-creds` で暗号化保存します。
systemdのユーザーサービスが起動時にユーザー専用の実行時ディレクトリへ復号し、終了時に破棄します。
OAuthの登録情報とトークンは暗号化した永続ストアへ保存します。
暗号化鍵を削除・再生成すると保存済みの認証情報を使えなくなるため、既存の鍵は維持します。

### チャット側の登録

共通の入力値は、名前「個人Obsidian」、URL `https://raspi4.tailee8e63.ts.net/mcp`、認証「OAuth」です。
OAuthクライアントの方式を選べる場合は「自動登録（DCR）」を使います。
GitHub OAuth AppのClient IDとClient SecretはラズパイがGitHubと接続するためのもので、チャット側の入力欄には設定しません。

- [ChatGPT](https://developers.openai.com/api/docs/guides/custom-mcp-server): [Plugins](https://chatgpt.com/plugins) の＋から「Add custom MCP server」で登録し、作成したプラグインをインストールします。新しいチャットで `@個人Obsidian` を選びます。
- [Claude](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp): 「Customize → Connectors → ＋ Add → Add custom connector」で登録します。GitHubに接続し、チャットの＋からコネクターを有効にします。

前提: ラズパイのMCP・認証入口・同期タイマー・Funnelが稼働し、GitHubの `parin1213` でログインできること。

1. 各チャットで「ノートを『Obsidian』で検索して」と依頼する → 個人vaultの検索結果が返る。
2. 「Notes/チャット接続確認-YYYY-MM-DD.md に、この接続確認の要点を新規保存して」と依頼する → 作成した相対パスが返る。同名があれば別名にする。
3. ラズパイとObsidian端末の定期同期後、Obsidianで保存先を開く → 会話で保存した内容が表示される。ラズパイ側は5分間隔で、端末側の同期待ち時間も加わる。

検索や保存が失敗した場合は、どのチャットのどの操作で止まったかと、画面のエラー文で切り分けます。

## 検証

```sh
cd ~/src/dotfiles/install/apps/obsidian-mcp
~/.local/bin/mise exec uv@0.11.8 -- uv run --frozen --python /usr/bin/python3 --no-build verify.py
~/.local/bin/mise exec uv@0.11.8 -- uv run --frozen --python /usr/bin/python3 --no-build verify_http.py
```

検証は一時ディレクトリへラズパイの実測を記したノートを作り、終了時に破棄します。
実vaultのノートは使いません。
`verify.py` はstdioで検索、保存、取得、入力制限を確認します。
`verify_http.py` はサーバーを起動してHTTPから同じ操作を確認します。

認証入口の検証は別の仮想環境で実行します。

```sh
cd ~/src/dotfiles/install/apps/obsidian-mcp/gateway
~/.local/bin/mise exec uv@0.11.8 -- uv sync --frozen --no-build --python /usr/bin/python3
.venv/bin/python -m pytest -q
.venv/bin/python ../verify_gateway_http.py
```

`verify_gateway_http.py` は8765番の既存MCPへ、実際のHTTP経路で接続します。
GitHub APIだけを公開プロフィール由来のfixtureに置き換え、本人の検索成功、別人の一覧非表示・実行拒否、未認証・無効トークンの拒否を確認します。
検索語は検証専用で、ノートを作成・変更しません。
GitHubの実際のログインとChatGPT・Claudeからの疎通は、本人操作で別途確認します。

## 接続に使う認証

- ラズパイのGit同期には、このリポジトリだけに書き込めるdeploy keyを使います。秘密鍵はラズパイ内の `~/.local/share/obsidian-vault/id_ed25519` に置き、他端末へコピーしません。GitHubのホスト鍵は公式APIの公開鍵で照合します。
- GitHub OAuth Appの本人登録と、ChatGPT・Claudeでの本人ログイン。
- OpenCode Goの接続。右側OpenCodeで `/connect` からGoを接続し、`/models` でGoのモデルを選ぶ。[Goの公式手順](https://opencode.ai/v2/docs/console/go)

Windowsで標準のOpenCodeコマンドが起動しない場合は、`powershell -NoProfile -File ~/.local/bin/opencode-personal.ps1` を使います。
miseで選択中の公式Windows実行ファイルを起動し、パッケージの内部ファイルは書き換えません。

## 既知の制約

- 検索は名前と本文の部分一致です。意味による検索と添付ファイルの解析は行いません。
- `.md` のみを扱い、隠しファイルとシンボリックリンクを拒否します。1ノートの上限は256KiBです。
- 保存先は既存フォルダです。同名ノートを上書きしません。
- Web版ChatGPT・ClaudeでカスタムMCPを使える契約と権限が必要です。
- Gitの競合は自動解決せず、`~/.local/state/obsidian-vault-sync.log` に記録します。
