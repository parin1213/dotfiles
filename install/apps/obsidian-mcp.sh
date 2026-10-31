#!/usr/bin/env bash
# 既存vaultのMarkdownを、ローカル専用MCPとして常駐させる。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/obsidian-mcp" && pwd)"
VAULT="${OBSIDIAN_VAULT:-$HOME/obsidian-vault}"
if [[ ! -d "$VAULT" ]]; then
  echo "==> Obsidian MCP: vaultが未配置のため常駐登録を保留: $VAULT"
  exit 0
fi
VAULT="$(cd "$VAULT" && pwd -P)"
for value in "$APP_DIR" "$VAULT"; do
  if [[ "$value" == *'"'* || "$value" == *'%'* || "$value" == *$'\n'* || "$value" == *'\'* ]]; then
    echo "パスに二重引用符、%、改行、バックスラッシュは使えません" >&2
    exit 1
  fi
done

MISE="$(command -v mise || true)"
[[ -n "$MISE" ]] || MISE="$HOME/.local/bin/mise"
if [[ ! -x "$MISE" ]]; then
  echo "miseが必要です。先にbootstrapで導入してください" >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)'; then
  echo "Python 3.13が必要です。実行するpython3のバージョンを確認してください" >&2
  exit 1
fi
cd "$APP_DIR"
echo "==> Obsidian MCP: lockfileで固定した依存を導入"
"$MISE" exec uv@0.11.8 -- uv sync --frozen --no-dev --no-build --python "$(command -v python3)"

UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/obsidian-mcp.service"
mkdir -p "$UNIT_DIR"
unit_temp="$(mktemp --suffix=.service)"
trap 'rm -f "$unit_temp"' EXIT
cat > "$unit_temp" <<EOF
[Unit]
Description=Obsidian MCP
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart="$APP_DIR/.venv/bin/python" "$APP_DIR/server.py" --vault "$VAULT" --transport streamable-http
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
UMask=0077

[Install]
WantedBy=default.target
EOF
systemd-analyze --user verify "$unit_temp"
changed=0
if ! cmp -s "$unit_temp" "$UNIT"; then
  install -m 600 "$unit_temp" "$UNIT"
  systemctl --user daemon-reload
  changed=1
fi
systemctl --user enable obsidian-mcp.service
if [[ "$changed" == 1 ]]; then
  systemctl --user restart obsidian-mcp.service
else
  systemctl --user start obsidian-mcp.service
fi
systemctl --user is-active --quiet obsidian-mcp.service
echo "==> Obsidian MCP: 常駐登録済み。接続先はこのホスト内の http://127.0.0.1:8765/mcp"
bash "$APP_DIR/install-gateway.sh"
