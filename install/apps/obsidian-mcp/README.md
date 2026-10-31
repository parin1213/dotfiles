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
ラズパイの定期Git同期は有効にしていません。
実vaultを配置する前に、個人ノートをprivate GitHubリポジトリへ送信する同期設定を本人が確認します。
アプリの導入対象は `.chezmoidata.toml` の `envs.raspi.apps` で管理します。
既存のHome Assistantは独立して稼働します。

接続先はラズパイ内の `http://127.0.0.1:8765/mcp` です。
外部からの接続は受け付けません。
SSHログインを閉じても動かすには `loginctl show-user "$USER" -p Linger` が `Linger=yes` であることを確認します。

## Web版ChatGPTへの接続

[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)を使い、ラズパイからOpenAIへ接続します。
Tailscaleはラズパイの管理に利用でき、Funnelでの公開は不要です。

1. 本人のOpenAI Platformでトンネルを作り、対象のChatGPTワークスペースと関連付ける。
2. 公式 `tunnel-client` に `tunnel_id`、実行用APIキー、上記MCP接続先を設定する。
3. Web版ChatGPTのプラグインでカスタムMCPを追加し、そのトンネルを選ぶ。
4. 「raspi4のメモを探して」で検索し、「この会話を新しいノートへ保存して」で作成先の実ファイルまで確認する。

APIキーはdotfilesへ書き込まず、本人の認証操作で設定します。
トンネル作成と使用の権限、ChatGPT側のカスタムMCP利用権限が必要です。

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

## 本人の操作が必要な箇所

- ラズパイへの実vault配置と同期認証。private GitHubリポジトリへの認証を設定し、clone後にvault側のAGENTS.mdを確認して同期する。
- OpenAIのトンネル作成、認証、Web版ChatGPTへの登録。
- OpenCode Goの接続。右側OpenCodeで `/connect` からGoを接続し、`/models` でGoのモデルを選ぶ。[Goの公式手順](https://opencode.ai/v2/docs/console/go)

Windowsで標準のOpenCodeコマンドが起動しない場合は、`powershell -NoProfile -File ~/.local/bin/opencode-personal.ps1` を使います。
miseで選択中の公式Windows実行ファイルを起動し、パッケージの内部ファイルは書き換えません。

## 既知の制約

- 検索は名前と本文の部分一致です。意味による検索と添付ファイルの解析は行いません。
- `.md` のみを扱い、隠しファイルとシンボリックリンクを拒否します。1ノートの上限は256KiBです。
- 保存先は既存フォルダです。同名ノートを上書きしません。
- 実vaultとの同期およびWeb版ChatGPTからの最終疎通は、本人の認証後に確認する必要があります。
- ラズパイの自動Git同期は未登録です。送信先と対象データの承認を得てから設定します。
