#!/usr/bin/env bash
# GitHub認証を備えたHTTP入口を、既存MCPの前に常駐させる。
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$HOME/.config/obsidian-mcp/gateway.toml"
CREDENTIAL_DIR="$HOME/.local/share/obsidian-mcp/credentials"
if [[ ! -f "$CONFIG" || ! -s "$CREDENTIAL_DIR/github-client-secret.cred" ]]; then
  echo "==> Obsidian MCP: OAuth公開設定とClient Secretの入力後に認証入口を登録します"
  exit 0
fi
MISE="$(command -v mise || true)"
[[ -n "$MISE" ]] || MISE="$HOME/.local/bin/mise"
cd "$APP_DIR/gateway"
"$MISE" exec uv@0.11.8 -- uv sync --frozen --no-dev --no-build --python "$(command -v python3)"

# 鍵を初回だけ生成し、秘密値を標準出力や平文ファイルに残さない。
.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
import subprocess
from cryptography.fernet import Fernet
root = Path.home() / ".local/share/obsidian-mcp/credentials"
root.mkdir(mode=0o700, parents=True, exist_ok=True)
for name, generate in (
    ("jwt-signing-key", lambda: secrets.token_urlsafe(48).encode()),
    ("storage-encryption-key", Fernet.generate_key),
):
    target = root / (name + ".cred")
    if target.exists():
        if target.is_symlink() or target.stat().st_size == 0:
            raise SystemExit("既存の暗号化鍵ファイルを確認してください")
        continue
    temporary = target.with_suffix(".cred.tmp")
    subprocess.run(
        ["systemd-creds", "encrypt", "--user", "--with-key=host", "--name="+name, "-", str(temporary)],
        input=generate(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )
    temporary.chmod(0o600)
    temporary.replace(target)
print("==> Obsidian MCP: 暗号化鍵の準備完了")
PY

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
unit_temp="$(mktemp --suffix=.service)"
trap 'rm -f "$unit_temp"' EXIT
cat > "$unit_temp" <<EOF
[Unit]
Description=Obsidian MCP GitHub OAuth
After=network.target obsidian-mcp.service
Requires=obsidian-mcp.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR/gateway
ExecStart="$APP_DIR/gateway/.venv/bin/python" "$APP_DIR/credential_exec.py" -m gateway.gateway --config "$CONFIG"
RuntimeDirectory=obsidian-mcp-gateway
RuntimeDirectoryMode=0700
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes
UMask=0077

[Install]
WantedBy=default.target
EOF
systemd-analyze --user verify "$unit_temp"
if ! cmp -s "$unit_temp" "$UNIT_DIR/obsidian-mcp-gateway.service"; then
  install -m 600 "$unit_temp" "$UNIT_DIR/obsidian-mcp-gateway.service"
  systemctl --user daemon-reload
fi
systemctl --user enable obsidian-mcp-gateway.service
systemctl --user restart obsidian-mcp-gateway.service
systemctl --user is-active --quiet obsidian-mcp-gateway.service
echo "==> Obsidian MCP: 認証入口をlocalhost:8766へ登録しました"
